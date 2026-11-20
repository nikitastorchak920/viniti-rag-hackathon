#!/usr/bin/env python3
"""Merge a teammate's JSON files (LLM caches and/or OCR-JSON) into the local cache, rebuild the CSVs
and run tools/check_submission.py.
  python scripts/merge_cache.py INCOMING(dir|.zip) --input dev --output out_dev [--cache cache]
Priority per document: complete LLM cache (text/pdf) > ocr_json > local > incomplete. Equal rank: the one
with more raw result rows. Existing files are replaced atomically only when the incoming one ranks higher/equal."""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
RANK = {"text": 3, "pdf": 3, "ocr_json": 2, "local": 1}


def rank(c: dict) -> tuple[int, int]:
    if not c or not c.get("complete"):
        return (0, 0)
    n = sum(len(w.get("results", [])) for w in c.get("windows", {}).values())
    return (RANK.get(c.get("mode"), 1), n)


def validate_llm_cache(doc: dict, stem: str, pdf_dir: pathlib.Path) -> str | None:
    from core.llm_client import SAFE_ID

    if not SAFE_ID.match(stem):
        return "unsafe id"
    if doc.get("version") != 2:
        return f"version {doc.get('version')!r} != 2"
    if not isinstance((doc.get("meta") or {}).get("publication"), dict):
        return "meta.publication missing"
    if not isinstance(doc.get("windows"), dict):
        return "windows missing"
    pdf = pdf_dir / f"{stem}.pdf"
    if pdf.exists():
        try:
            import pymupdf

            with pymupdf.open(pdf) as d:
                n = len(d)
        except Exception:  # noqa: BLE001
            n = None
        if n is not None and doc.get("n_pages") != n:
            return f"n_pages {doc.get('n_pages')} != PDF pages {n}"
    return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("incoming", type=pathlib.Path)
    ap.add_argument("--input", type=pathlib.Path, required=True, help="PDF folder (dev or test)")
    ap.add_argument("--output", type=pathlib.Path, required=True)
    ap.add_argument("--cache", type=pathlib.Path, default=pathlib.Path("cache"))
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args()

    from core.llm_client import load_cache, save_cache
    from plugins.rag.ocr_adapter import ingest_file

    tmp = None
    src = a.incoming
    if src.suffix.lower() == ".zip":
        tmp = tempfile.TemporaryDirectory(prefix="merge_")
        with zipfile.ZipFile(src) as z:
            for m in z.namelist():  # zip-slip guard
                if m.endswith(".json") and ".." not in pathlib.PurePosixPath(m).parts and not m.startswith("/"):
                    z.extract(m, tmp.name)
        src = pathlib.Path(tmp.name)
    files = sorted(src.rglob("*.json")) if src.is_dir() else [src]
    if not files:
        print(f"ERROR: no JSON files in {a.incoming}")
        return 1
    stats = {"merged": 0, "kept": 0, "ocr": 0, "bad": 0}
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"BAD  {f.name}: {exc}")
            stats["bad"] += 1
            continue
        if isinstance(doc, dict) and "pages" in doc and "meta" not in doc:
            ok, msg = ingest_file(f, a.cache, a.input, force=False)
            print(f"{'OCR ' if ok else 'BAD '} {f.stem}: {msg}")
            stats["ocr" if ok else "bad"] += 1
            continue
        if not (isinstance(doc, dict) and "meta" in doc and "windows" in doc and f.stem.replace("_", "").isalnum()):
            print(f"BAD  {f.name}: neither LLM cache nor OCR-JSON")
            stats["bad"] += 1
            continue
        err = validate_llm_cache(doc, f.stem, a.input)
        if err:
            print(f"BAD  {f.name}: {err}")
            stats["bad"] += 1
            continue
        old = load_cache(a.cache, f.stem)
        if rank(doc) >= rank(old) and rank(doc)[0] > 0:
            save_cache(a.cache, f.stem, doc)
            print(f"NEW  {f.stem}: {rank(doc)} replaces {rank(old)}")
            stats["merged"] += 1
        else:
            print(f"KEEP {f.stem}: local {rank(old)} >= incoming {rank(doc)}")
            stats["kept"] += 1
    if tmp:
        tmp.cleanup()
    print(f"merge: {stats}")

    import main as pipeline

    rc = pipeline.main(["--input", str(a.input), "--output", str(a.output), "--cache", str(a.cache), "--rebuild-csv-only"])
    if a.no_check or not (a.output / "publications.csv").exists():
        return rc
    chk = subprocess.run([sys.executable, str(ROOT / "tools" / "check_submission.py"), str(a.output), str(a.input)])
    print(f"check_submission exit code: {chk.returncode} (0 ok, 1 errors, 2 needs review)")
    return rc or (1 if chk.returncode == 1 else 0)


if __name__ == "__main__":
    sys.exit(main())
