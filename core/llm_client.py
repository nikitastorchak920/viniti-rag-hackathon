"""Gemini wrapper: structured JSON output, bounded retries, per-document cache."""
from __future__ import annotations

import json
import os
import pathlib
import random
import re
import sys
import time
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
               "reset by peer", "remote protocol", "temporarily", "overloaded", "readerror")
    return isinstance(exc, (TimeoutError, ConnectionError)) or any(
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
                text = (resp.text or "").strip()
                if not text:
                    raise ValueError("empty response (blocked or no candidates)")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("response is not a JSON object")
                return data
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
