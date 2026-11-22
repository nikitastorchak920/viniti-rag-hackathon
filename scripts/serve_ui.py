#!/usr/bin/env python3
"""Serve RAG Atlas locally. Pass --solar and --rag with their CSV directories."""
from __future__ import annotations

import argparse
import functools
import http.server
import io
import json
import pathlib
from urllib.parse import urlsplit

ROOT = pathlib.Path(__file__).resolve().parents[1]
TABLES = {
    "solar": ("publications", "materials", "devices", "layers", "measurements", "results", "issues"),
    "rag": ("publications", "configurations", "datasets", "tasks", "experiments", "results", "issues"),
}
DEFAULTS = {"solar": "out_solar_dev", "rag": "out_jury_deepseek_v1/csv"}
DATA_FILES = {domain: {f"{table}.csv" for table in tables} | {"validation.json"} for domain, tables in TABLES.items()}


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, bundles, **kwargs):
        self.bundles = bundles
        super().__init__(*args, **kwargs)

    def send_head(self):
        path = urlsplit(self.path).path
        if path == "/api/domains.json":
            payload = json.dumps({
                domain: {"available": domain in self.bundles, "tables": tables,
                         "label": self.bundles[domain].name if domain in self.bundles else "",
                         "validation": domain in self.bundles and (self.bundles[domain] / "validation.json").is_file()}
                for domain, tables in TABLES.items()
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            return io.BytesIO(payload)
        if path.startswith("/data/") and self.data_path(path) is None:
            self.send_error(404, "Unknown data file")
            return None
        return super().send_head()

    def data_path(self, path: str) -> pathlib.Path | None:
        parts = path.removeprefix("/data/").split("/")
        if len(parts) == 1:
            domain, name = "rag" if "rag" in self.bundles else "solar", parts[0]
        elif len(parts) == 2:
            domain, name = parts
        else:
            return None
        folder = self.bundles.get(domain)
        if folder and name in DATA_FILES[domain]:
            file = folder / name
            if file.is_file():
                return file
        return None

    def translate_path(self, path: str) -> str:
        base = urlsplit(path).path
        if base.startswith("/data/") and (file := self.data_path(base)):
            return str(file)
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", nargs="?", type=pathlib.Path, help="legacy positional RAG CSV directory")
    for domain in TABLES:
        ap.add_argument(f"--{domain}", type=pathlib.Path, help=f"directory with the seven {domain} CSVs")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    bundles = {}
    for domain, tables in TABLES.items():
        explicit = getattr(a, domain) or (a.data if domain == "rag" else None)
        folder = (explicit or ROOT / DEFAULTS[domain]).resolve()
        missing = [f"{table}.csv" for table in tables if not (folder / f"{table}.csv").is_file()]
        if missing and explicit:
            ap.error(f"missing {domain} CSV files in {folder}: {', '.join(missing)}")
        if not missing:
            bundles[domain] = folder
    h = functools.partial(Handler, directory=str(ROOT / "app"), bundles=bundles)
    with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), h) as srv:
        print(f"UI: http://127.0.0.1:{a.port}/ - Ctrl+C to stop")
        for domain in TABLES:
            print(f"  {domain}: {bundles.get(domain, 'no CSV bundle')}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
