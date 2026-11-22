import functools
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from scripts.serve_ui import Handler, TABLES


def test_csv_routes_keep_domains_separate(tmp_path):
    bundles = {}
    for domain, tables in TABLES.items():
        folder = bundles[domain] = tmp_path / domain
        folder.mkdir()
        for table in tables:
            (folder / f"{table}.csv").write_text(f"publication_id,title\nD001,{domain}\n", encoding="utf-8")
    (bundles["rag"] / "validation.json").write_text("{}", encoding="utf-8")
    handler = functools.partial(Handler, directory=str(tmp_path), bundles=bundles)
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            def read(path):
                with urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=3) as response:
                    return response.read()

            manifest = json.loads(read("/api/domains.json"))
            assert manifest["rag"]["validation"]
            assert not manifest["solar"]["validation"]
            for domain, tables in TABLES.items():
                assert manifest[domain]["tables"] == list(tables)
                for table in tables:
                    assert read(f"/data/{domain}/{table}.csv").splitlines()[-1] == f"D001,{domain}".encode()
            assert read("/data/results.csv") == read("/data/rag/results.csv")
            for path in ("/data/solar/tasks.csv", "/data/rag/devices.csv", "/data/rag/../solar/publications.csv"):
                with pytest.raises(HTTPError, match="404"):
                    read(path)
        finally:
            server.shutdown()
            thread.join()
