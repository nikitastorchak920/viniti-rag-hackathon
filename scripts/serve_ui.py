#!/usr/bin/env python3
"""Serve app/ and a CSV folder over http.server (stdlib).  python scripts/serve_ui.py out_dev [--port 8000]"""
from __future__ import annotations

import argparse
import functools
import http.server
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CSV_FILES = tuple(f"{table}.csv" for table in (
    "publications", "configurations", "datasets", "tasks", "experiments", "results", "issues",
))


class Handler(http.server.SimpleHTTPRequestHandler):
    data_dir: pathlib.Path

    def translate_path(self, path: str) -> str:
        p = path.split("?", 1)[0]
        name = p.removeprefix("/data/")
        if p != name and name in CSV_FILES:
            return str(self.data_dir / name)
        return super().translate_path(path)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data", type=pathlib.Path, help="folder with the 7 CSV files (e.g. out_dev)")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    Handler.data_dir = a.data.resolve()
    missing = [name for name in CSV_FILES if not (Handler.data_dir / name).is_file()]
    if missing:
        ap.error(f"missing CSV files in {Handler.data_dir}: {', '.join(missing)}")
    h = functools.partial(Handler, directory=str(ROOT / "app"))
    with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), h) as srv:
        print(f"UI: http://127.0.0.1:{a.port}/  (data: {Handler.data_dir}) - Ctrl+C to stop")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
