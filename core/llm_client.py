"""Gemini wrapper: structured JSON output, bounded retries, per-document cache."""
from __future__ import annotations

import http.client
import json
import os
import pathlib
import random
import re
import ssl
import sys
import time
import urllib.error
from typing import Any

DEFAULT_MODEL = "gemini-3.8-flash"
RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}


def log(msg: str) -> None:
    print(msg, flush=True)


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(encoding="utf-8")
    except ImportError:  # python-dotenv optional at runtime
        pass


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


class LLMError(RuntimeError):
    """Raised when a call fails permanently (non-retryable or retries exhausted)."""


class TruncatedResponseError(LLMError):
    """Model output hit the token limit; retrying the same request is pointless."""


SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def _status_code(exc: Exception) -> int | None:
    for attr in ("code", "status_code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    m = re.match(r"\s*(\d{3})\b", str(exc))
    return int(m.group(1)) if m else None


def is_transient(exc: Exception) -> bool:
    code = _status_code(exc)
    if code is not None:
        return code in RETRYABLE_CODES
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    markers = ("timeout", "timed out", "connection", "unavailable", "resource_exhausted",
               "reset by peer", "remote protocol", "temporarily", "overloaded", "readerror",
               "eof", "ssl", "incomplete", "remotedisconnected", "broken pipe")
    # network-level failures (TLS EOF, dropped TCP, truncated body): always retryable
    return isinstance(exc, (urllib.error.URLError, ssl.SSLError, http.client.HTTPException, OSError)) or any(
        k in name or k in text for k in markers)


class GeminiClient:
    def __init__(self) -> None:
        load_env()
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
        from google import genai
        from google.genai import types

        self.types = types
        self.model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
        self.max_retries = int(_f("GEMINI_MAX_RETRIES", 6))
        self.base = _f("GEMINI_BACKOFF_BASE", 2)
        self.cap = _f("GEMINI_BACKOFF_MAX", 60)
        self.max_out = int(_f("GEMINI_MAX_OUTPUT_TOKENS", 65536))
        self.temperature = _f("GEMINI_TEMPERATURE", 0)
        timeout_ms = int(_f("GEMINI_TIMEOUT_S", 300) * 1000)
        self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=timeout_ms))

    def preflight(self) -> None:
        """Cheap availability check of the chosen model; clear error on 404/401/403."""
        try:
            self.client.models.get(model=self.model)
        except Exception as exc:  # noqa: BLE001
            code = _status_code(exc)
            if code in (400, 401, 403, 404):
                raise LLMError(f"Gemini model '{self.model}' unavailable (HTTP {code}): check GEMINI_MODEL / GEMINI_API_KEY") from exc
            log(f"  WARN: preflight skipped ({type(exc).__name__}: {str(exc)[:120]})")

    def _sleep(self, attempt: int, tag: str, reason: str) -> None:
        delay = min(self.cap, self.base * (2 ** attempt)) * random.uniform(0.5, 1.5)
        log(f"  [{tag}] retry {attempt + 1}/{self.max_retries} in {delay:.1f}s: {reason}")
        time.sleep(delay)

    def generate_json(self, contents: list[Any], system: str, schema: Any, tag: str = "") -> dict:
        """Return parsed JSON dict. Retries transient API errors and truncated/invalid JSON."""
        cfg = self.types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=self.temperature,
            max_output_tokens=self.max_out,
        )
        last = "unknown"
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.client.models.generate_content(
                    model=self.model, contents=contents, config=cfg)
                try:
                    fr = getattr(resp.candidates[0].finish_reason, "name", str(resp.candidates[0].finish_reason))
                except (TypeError, IndexError, AttributeError):
                    fr = ""
                if fr == "MAX_TOKENS":
                    raise TruncatedResponseError("output truncated (finish_reason=MAX_TOKENS): window will be split")
                text = (resp.text or "").strip()
                if not text:
                    raise ValueError("empty response (blocked or no candidates)")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("response is not a JSON object")
                return data
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001
                last = f"{type(exc).__name__}: {str(exc)[:300]}"
                retry = is_transient(exc) or isinstance(exc, (ValueError, json.JSONDecodeError))
                if not retry:
                    raise LLMError(last) from exc
                if attempt >= self.max_retries:
                    break
                self._sleep(attempt, tag, last)
        raise LLMError(f"retries exhausted ({self.max_retries}); last error: {last}")

    # ---- Files API (scanned PDFs) ----
    def upload_pdf(self, path: pathlib.Path, tag: str = "") -> Any:
        last = "unknown"
        for attempt in range(self.max_retries + 1):
            try:
                f = self.client.files.upload(file=str(path), config={"mime_type": "application/pdf"})
                for _ in range(60):  # wait until ACTIVE
                    state = getattr(getattr(f, "state", None), "name", str(getattr(f, "state", "")))
                    if state in ("ACTIVE", "None", ""):
                        return f
                    if state == "FAILED":
                        raise ValueError("file processing FAILED")
                    time.sleep(2)
                    f = self.client.files.get(name=f.name)
                raise TimeoutError("file stayed in PROCESSING state")
            except Exception as exc:  # noqa: BLE001
                last = f"{type(exc).__name__}: {str(exc)[:300]}"
                if not is_transient(exc) or attempt >= self.max_retries:
                    if not is_transient(exc):
                        raise LLMError(last) from exc
                    break
                self._sleep(attempt, tag, last)
        raise LLMError(f"upload failed after retries; last error: {last}")

    def delete_file(self, f: Any) -> None:
        try:
            self.client.files.delete(name=f.name)
        except Exception as exc:  # noqa: BLE001
            log(f"  WARN: could not delete uploaded file {getattr(f, 'name', '?')}: {exc}")


# ---- cache: cache/<doc_id>.json (only successful responses are ever written) ----
def cache_path(cache_dir: pathlib.Path, doc_id: str) -> pathlib.Path:
    if not SAFE_ID.match(str(doc_id)):
        raise ValueError(f"unsafe document id: {doc_id!r}")
    return pathlib.Path(cache_dir) / f"{doc_id}.json"


def load_cache(cache_dir: pathlib.Path, doc_id: str) -> dict:
    p = cache_path(cache_dir, doc_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"WARN: unreadable cache {p}, ignoring", file=sys.stderr)
        return {}


def save_cache(cache_dir: pathlib.Path, doc_id: str, data: dict) -> None:
    cache_dir = pathlib.Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_path(cache_dir, doc_id)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


# ---- DeepSeek (OpenAI-compatible chat API, stdlib urllib only; text-only) ----
class DeepSeekClient:
    text_only = True
    BASE_URL = "https://api.deepseek.com"

    def __init__(self) -> None:
        load_env()
        self.key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not self.key:
            raise LLMError("DEEPSEEK_API_KEY is not set (see .env.example)")
        self.base_url = (os.environ.get("DEEPSEEK_BASE_URL", "").strip() or self.BASE_URL).rstrip("/")
        self.URL = self.base_url + "/chat/completions"
        self.model = os.environ.get("DEEPSEEK_MODEL", "").strip() or "deepseek-flash"
        self.max_retries = int(_f("DEEPSEEK_MAX_RETRIES", 6))
        self.base = _f("GEMINI_BACKOFF_BASE", 2)
        self.cap = _f("GEMINI_BACKOFF_MAX", 60)
        self.timeout = _f("DEEPSEEK_TIMEOUT_S", 300)
        self.max_out = int(_f("DEEPSEEK_MAX_TOKENS", 8192))
        self.temperature = _f("DEEPSEEK_TEMPERATURE", 0)
        self.freq_penalty = _f("DEEPSEEK_FREQUENCY_PENALTY", 0)
        self.tokens_in = 0
        self.tokens_out = 0

    def preflight(self) -> None:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(self.base_url + "/models", headers={"Authorization": f"Bearer {self.key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                ids = [m.get("id") for m in json.loads(r.read().decode("utf-8")).get("data", [])]
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                raise LLMError(f"DeepSeek preflight failed (HTTP {exc.code}): check DEEPSEEK_API_KEY") from exc
            log(f"  WARN: preflight skipped (HTTP {exc.code})")
            return
        except Exception as exc:  # noqa: BLE001
            log(f"  WARN: preflight skipped ({type(exc).__name__}: {str(exc)[:120]})")
            return
        if ids and self.model not in ids:
            raise LLMError(f"DeepSeek model '{self.model}' not found (HTTP 404); available: {', '.join(map(str, ids))}")

    def _post(self, payload: dict) -> dict:
        import urllib.request

        req = urllib.request.Request(
            self.URL, data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def generate_json(self, contents: list[Any], system: str, schema: Any, tag: str = "") -> dict:
        import urllib.error

        try:
            shape = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        except Exception:  # noqa: BLE001
            shape = ""
        sys_msg = system + "\n\nReturn ONLY a valid json object that matches this JSON Schema (all fields required):\n" + shape
        payload = {
            "model": self.model, "temperature": self.temperature, "max_tokens": self.max_out,
            "frequency_penalty": self.freq_penalty,
            "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": sys_msg},
                         {"role": "user", "content": "\n\n".join(str(c) for c in contents)}]}
        last = "unknown"
        for attempt in range(self.max_retries + 1):
            wait = None
            try:
                resp = self._post(payload)
                u = resp.get("usage") or {}
                self.tokens_in += u.get("prompt_tokens", 0)
                self.tokens_out += u.get("completion_tokens", 0)
                log(f"  [{tag}] tokens in={u.get('prompt_tokens', 0)} out={u.get('completion_tokens', 0)} "
                    f"(total in={self.tokens_in} out={self.tokens_out})")
                ch = (resp.get("choices") or [{}])[0]
                if ch.get("finish_reason") == "length":
                    raise TruncatedResponseError("output truncated (finish_reason=length): window will be split")
                text = ((ch.get("message") or {}).get("content") or "").strip()
                if not text:
                    raise ValueError("empty response")
                m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S | re.I)
                data = json.loads(m.group(1) if m else text)
                if not isinstance(data, dict):
                    raise ValueError("response is not a JSON object")
                return data
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001
                last = f"{type(exc).__name__}: {str(exc)[:300]}"
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        last += " " + exc.read().decode("utf-8", "replace")[:200]
                    except Exception:  # noqa: BLE001
                        pass
                    ra = exc.headers.get("Retry-After") if exc.headers else None
                    if exc.code == 429 and ra and ra.replace(".", "", 1).isdigit():
                        wait = min(self.cap, float(ra))
                if not (is_transient(exc) or isinstance(exc, (ValueError, json.JSONDecodeError))):
                    raise LLMError(last) from exc
                if attempt >= self.max_retries:
                    break
                if wait is None:
                    delay = min(self.cap, self.base * (2 ** attempt)) * random.uniform(0.5, 1.5)
                else:
                    delay = wait + random.uniform(0, 1)
                log(f"  [{tag}] retry {attempt + 1}/{self.max_retries} in {delay:.1f}s: {last}")
                time.sleep(delay)
        raise LLMError(f"retries exhausted ({self.max_retries}); last error: {last}")

    def upload_pdf(self, *a: Any, **k: Any) -> Any:
        raise LLMError("DeepSeek is text-only: scanned PDFs are not supported")

    def delete_file(self, f: Any) -> None:
        pass
