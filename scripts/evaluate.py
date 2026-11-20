#!/usr/bin/env python3
"""Compare a result folder (e.g. out_dev) with dev_gold (stdlib only).
  python scripts/evaluate.py out_dev dev_gold [--only D001 D002]
Only publications present in the result folder are scored."""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

csv.field_size_limit(2**31 - 1)
TABLES = ["publications", "configurations", "datasets", "tasks", "experiments", "results", "issues"]


def read(folder: pathlib.Path, table: str) -> list[dict]:
    p = folder / f"{table}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def n(s: str) -> str:
    return re.sub(r"[^\w.@]+", " ", (s or "").lower()).strip()


def num(s: str) -> str:
    try:
        return format(Decimal(s).normalize(), "f")
    except (InvalidOperation, ValueError):
        return ""


def keys(folder: pathlib.Path, pubs: set[str]) -> dict[str, Counter]:
    cfg = {(r["publication_id"], r["config_id"]): r for r in read(folder, "configurations")}
    ds = {(r["publication_id"], r["dataset_id"]): r for r in read(folder, "datasets")}
    out = {"dataset": Counter(), "model": Counter(), "value": Counter(), "value_loose": Counter()}
    for (pid, _), c in cfg.items():
        if pid in pubs:
            out["model"][(pid, n(c["rag_variant"]), n(c["generator_model"]))] += 1
    for (pid, _), d in ds.items():
        if pid in pubs:
            out["dataset"][(pid, n(d["dataset_name"]))] += 1
    for r in read(folder, "results"):
        pid = r["publication_id"]
        if pid not in pubs or r["extraction_status"] != "extracted" or r["duplicate_of"]:
            continue
        v = num(r["metric_value"])
        if not v:
            continue
        c = cfg.get((pid, r["config_id"]), {})
        d = ds.get((pid, r["dataset_id"]), {})
        out["value"][(pid, n(d.get("dataset_name", "")), n(c.get("rag_variant", "")), n(c.get("generator_model", "")),
                      n(r["metric_name"]), r["metric_k"], v)] += 1
        out["value_loose"][(pid, n(r["metric_name"]), v)] += 1
    return out


def prf(pred: Counter, gold: Counter) -> tuple[float, float, float, int, int, int]:
    tp = sum((pred & gold).values())
    p_n, g_n = sum(pred.values()), sum(gold.values())
    p = tp / p_n if p_n else 0.0
    r = tp / g_n if g_n else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f, tp, p_n, g_n


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("result", type=pathlib.Path)
    ap.add_argument("gold", type=pathlib.Path, nargs="?", default=pathlib.Path("dev_gold"))
    ap.add_argument("--only", nargs="+")
    a = ap.parse_args()

    pr = {r["publication_id"]: r for r in read(a.result, "publications")}
    gd = {r["publication_id"]: r for r in read(a.gold, "publications")}
    if not pr:
        print(f"ERROR: no publications in {a.result}")
        return 1
    pubs = set(pr) & set(gd)
    if a.only:
        pubs &= {x.upper() for x in a.only}
    print(f"Scored publications: {len(pubs)} ({', '.join(sorted(pubs))})")
    for pid in sorted(set(pr) - set(gd)):
        print(f"  note: {pid} not in gold, skipped")

    print("\n== publications.csv: scope decision")
    ok = sum(1 for p in pubs if pr[p]["in_scope"] == gd[p]["in_scope"])
    print(f"in_scope agreement: {ok}/{len(pubs)} = {ok / max(1, len(pubs)):.1%}")
    inc_g = {p for p in pubs if gd[p]["in_scope"] == "true"}
    inc_p = {p for p in pubs if pr[p]["in_scope"] == "true"}
    print(f"included: pred {len(inc_p)} vs gold {len(inc_g)}; wrong: {', '.join(sorted(inc_p ^ inc_g)) or '-'}")

    print("\n== row counts (result vs gold, scored pubs only)")
    for t in TABLES:
        cp = sum(1 for r in read(a.result, t) if r["publication_id"] in pubs)
        cg = sum(1 for r in read(a.gold, t) if r["publication_id"] in pubs)
        print(f"{t:15} {cp:7} vs {cg:7}  ({cp - cg:+d})")

    kp, kg = keys(a.result, pubs), keys(a.gold, pubs)
    print("\n== Precision / Recall / F1")
    for name, label in (("dataset", "datasets (by name)"), ("model", "models (rag_variant+generator)"),
                        ("value", "metric values (strict: dataset+model+metric+k+value)"),
                        ("value_loose", "metric values (loose: metric name+value)")):
        p, r, f, tp, pn, gn = prf(kp[name], kg[name])
        print(f"{label:58} P={p:.3f} R={r:.3f} F1={f:.3f}  (tp={tp}, pred={pn}, gold={gn})")

    print("\n== per publication (strict value F1)")
    rows = []
    for pid in sorted(pubs):
        sp = Counter({k: v for k, v in kp["value"].items() if k[0] == pid})
        sg = Counter({k: v for k, v in kg["value"].items() if k[0] == pid})
        p, r, f, tp, pn, gn = prf(sp, sg)
        rows.append((f, pid, p, r, pn, gn))
        print(f"{pid}: F1={f:.3f} P={p:.3f} R={r:.3f} pred={pn} gold={gn}")

    print("\n== top-5 discrepancies (worst publications; sample missing / extra values)")
    for f, pid, *_ in sorted(rows)[:5]:
        miss = (Counter({k: v for k, v in kg["value"].items() if k[0] == pid}) -
                Counter({k: v for k, v in kp["value"].items() if k[0] == pid}))
        extra = (Counter({k: v for k, v in kp["value"].items() if k[0] == pid}) -
                 Counter({k: v for k, v in kg["value"].items() if k[0] == pid}))
        print(f"{pid} (F1={f:.3f}) missing={sum(miss.values())} extra={sum(extra.values())}")
        for k in list(miss)[:1]:
            print("   missing:", k[1:])
        for k in list(extra)[:1]:
            print("   extra:  ", k[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
