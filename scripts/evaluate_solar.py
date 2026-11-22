#!/usr/bin/env python3
"""Evaluate Domain 1 (Thin-film solar cells) CSV export against oblast_1/dev_gold (stdlib only).

Usage:
  python scripts/evaluate_solar.py out_solar_dev область_1/dev_gold [--only D001 D006] [--show-diffs 20]
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys
from collections import Counter, defaultdict, deque
from decimal import Decimal, InvalidOperation
from itertools import combinations

csv.field_size_limit(2**31 - 1)
TABLES = ["publications", "materials", "devices", "layers", "measurements", "results", "issues"]
CANONICAL_METRICS = {
    "pce", "voc", "jsc", "ff", "rs", "rsh", "hi", "jsc_eqe", "stabilized_pce", "t80", "retained_pce",
}
CONTEXT_FIELDS = ("device_label", "scan_direction", "aggregation", "result_origin")


def read(folder: pathlib.Path, table: str) -> list[dict]:
    p = folder / f"{table}.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def n(s: str) -> str:
    return re.sub(r"[^\w.+]+", " ", (s or "").lower()).strip()


def num_key(s: str, decimals: int = 3) -> str:
    try:
        d = Decimal((s or "").strip())
        if not d.is_finite():
            return ""
        q = d.quantize(Decimal(10) ** -decimals)
        res = format(q.normalize(), "f")
        return "0" if res == "-0" else res
    except (InvalidOperation, ValueError):
        return ""


def keys(folder: pathlib.Path, pubs: set[str]) -> dict[str, Counter]:
    mats = {(r["publication_id"], r["material_id"]): r for r in read(folder, "materials")}
    devs = {(r["publication_id"], r["device_id"]): r for r in read(folder, "devices")}
    meass = {(r["publication_id"], r["measurement_id"]): r for r in read(folder, "measurements")}

    out = {
        "material": Counter(),
        "device": Counter(),
        "value_strict": Counter(),
        "value_schema_strict": Counter(),
        "value_medium": Counter(),
        "value_loose": Counter(),
    }
    for (pid, _), m in mats.items():
        if pid in pubs:
            out["material"][(pid, n(m.get("material_class", "")), n(m.get("formula_normalized", "") or m.get("material_name_raw", "")))] += 1
    for (pid, _), d in devs.items():
        if pid in pubs:
            out["device"][(pid, n(d.get("device_label", "")), n(d.get("architecture", "")))] += 1

    for r in read(folder, "results"):
        pid = r["publication_id"]
        if pid not in pubs or r.get("extraction_status") != "extracted" or r.get("duplicate_of"):
            continue
        mname = n(r.get("metric_name", "")).replace(" ", "_")
        if mname not in CANONICAL_METRICS:
            continue
        v = num_key(r.get("metric_value", "") or r.get("normalized_value", ""), decimals=3)
        if not v:
            continue
        d = devs.get((pid, r.get("device_id", "")), {})
        m = mats.get((pid, r.get("material_id", "") or d.get("absorber_material_id", "")), {})
        ms = meass.get((pid, r.get("measurement_id", "")), {})
        dlabel = n(d.get("device_label", ""))
        mclass = n(m.get("material_class", ""))
        sdir = n(ms.get("scan_direction", ""))
        agg = n(r.get("aggregation", ""))
        orig = n(r.get("result_origin", "") or "primary")

        out["value_strict"][(pid, dlabel, sdir, agg, orig, mname, v)] += 1
        out["value_schema_strict"][(pid, mclass, sdir, agg, orig, mname, v)] += 1
        out["value_medium"][(pid, agg, orig, mname, v)] += 1
        out["value_loose"][(pid, mname, v)] += 1
    return out


def prf(pred: Counter, gold: Counter) -> tuple[float, float, float, int, int, int]:
    tp = sum((pred & gold).values())
    p_n, g_n = sum(pred.values()), sum(gold.values())
    p = tp / p_n if p_n else 0.0
    r = tp / g_n if g_n else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f, tp, p_n, g_n


def loose_diffs(pred: Counter, gold: Counter):
    def group(rows: Counter) -> dict[tuple, Counter]:
        grouped = defaultdict(Counter)
        for (pid, dlabel, sdir, agg, orig, mname, v), cnt in rows.items():
            grouped[(pid, mname, v)][(dlabel, sdir, agg, orig)] += cnt
        return grouped

    extra, missing = group(pred - gold), group(gold - pred)
    for loose_key in sorted(extra.keys() & missing.keys()):
        predicted, expected = extra[loose_key], missing[loose_key]
        for shared in range(len(CONTEXT_FIELDS) - 1, -1, -1):
            for idxs in combinations(range(len(CONTEXT_FIELDS)), shared):
                if not predicted or not expected:
                    break
                cands = defaultdict(deque)
                for row in sorted(expected.elements()):
                    cands[tuple(row[i] for i in idxs)].append(row)
                for row in sorted(predicted.elements()):
                    ms = cands.get(tuple(row[i] for i in idxs))
                    if ms:
                        match = ms.popleft()
                        predicted[row] -= 1
                        expected[match] -= 1
                        if not predicted[row]:
                            del predicted[row]
                        if not expected[match]:
                            del expected[match]
                        yield loose_key, row, match


def show_loose_diffs(pred: Counter, gold: Counter, limit: int) -> None:
    print("\n== loose matches that fail strict matching")
    counts = Counter()
    total = 0
    for (pid, metric, value), actual, expected in loose_diffs(pred, gold):
        diffs = [(field, a, e) for field, a, e in zip(CONTEXT_FIELDS, actual, expected) if a != e]
        counts.update(field for field, _, _ in diffs)
        total += 1
        if total <= limit:
            detail = ", ".join(f"{field} pred={a!r} gold={e!r}" for field, a, e in diffs)
            print(f"  {pid} {metric}={value}: {detail}")
    print(f"Paired rows: {total}; shown: {min(total, limit)}")
    print("Field mismatches: " + ", ".join(f"{field}={counts[field]}" for field in CONTEXT_FIELDS))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("result", type=pathlib.Path)
    ap.add_argument("gold", type=pathlib.Path)
    ap.add_argument("--only", nargs="+")
    ap.add_argument("--show-diffs", type=int, default=20, metavar="N")
    a = ap.parse_args(argv)

    pr = {r["publication_id"]: r for r in read(a.result, "publications")}
    gd = {r["publication_id"]: r for r in read(a.gold, "publications")}
    if not pr:
        print(f"ERROR: no publications in {a.result}")
        return 1
    pubs = set(gd)
    if a.only:
        pubs &= {x.upper() for x in a.only}
    missing = sorted(pubs - set(pr))
    print(f"Scored publications: {len(pubs)} ({', '.join(sorted(pubs))})")
    print(f"MISSING from result (recall=0): {len(missing)} {', '.join(missing) or '-'}")

    print("\n== publications.csv: scope decision")
    unresolved = {p for p in pubs & pr.keys() if pr[p].get("exclusion_reason") == "Unprocessed: no scope decision"}
    ok = sum(1 for p in pubs - unresolved if p in pr and pr[p]["in_scope"] == gd[p]["in_scope"])
    print(f"in_scope agreement: {ok}/{len(pubs)} = {ok / max(1, len(pubs)):.1%}")
    inc_g = {p for p in pubs if gd[p]["in_scope"] == "true"}
    inc_p = {p for p in pubs if p in pr and pr[p]["in_scope"] == "true"}
    print(f"included: pred {len(inc_p)} vs gold {len(inc_g)}; wrong: {', '.join(sorted(inc_p ^ inc_g)) or '-'}")

    print("\n== row counts (result vs gold, scored pubs only)")
    for t in TABLES:
        cp = sum(1 for r in read(a.result, t) if r["publication_id"] in pubs)
        cg = sum(1 for r in read(a.gold, t) if r["publication_id"] in pubs)
        print(f"{t:15} {cp:7} vs {cg:7}  ({cp - cg:+d})")

    kp, kg = keys(a.result, pubs), keys(a.gold, pubs)
    print("\n== Precision / Recall / F1 (11 canonical solar metrics)")
    for name, label in (
        ("material", "materials (class + formula/name)"),
        ("device", "devices (label + architecture)"),
        ("value_strict", "metric values (strict+label: dev_label+scan+agg+orig+m+val)"),
        ("value_schema_strict", "metric values (schema-strict: mat_class+scan+agg+orig+m+val)"),
        ("value_medium", "metric values (medium: agg+origin+metric+val)"),
        ("value_loose", "metric values (loose: metric+value)"),
    ):
        p, r, f, tp, pn, gn = prf(kp[name], kg[name])
        print(f"{label:60} P={p:.3f} R={r:.3f} F1={f:.3f}  (tp={tp}, pred={pn}, gold={gn})")
    show_loose_diffs(kp["value_strict"], kg["value_strict"], a.show_diffs)

    print("\n== per publication (loose / strict value F1)")
    rows = []
    for pid in sorted(pubs):
        sp_s = Counter({k: v for k, v in kp["value_strict"].items() if k[0] == pid})
        sg_s = Counter({k: v for k, v in kg["value_strict"].items() if k[0] == pid})
        sp_l = Counter({k: v for k, v in kp["value_loose"].items() if k[0] == pid})
        sg_l = Counter({k: v for k, v in kg["value_loose"].items() if k[0] == pid})
        ps, rs, fs, tps, pns, gns = prf(sp_s, sg_s)
        pl, rl, fl, tpl, pnl, gnl = prf(sp_l, sg_l)
        rows.append((fl, fs, pid, pns, gns))
        print(f"{pid}: Strict F1={fs:.3f} (P={ps:.3f} R={rs:.3f} tp={tps}) | Loose F1={fl:.3f} (P={pl:.3f} R={rl:.3f} tp={tpl}) pred={pns} gold={gns}")

    print("\n== top-5 discrepancies (lowest Loose F1)")
    for fl, fs, pid, pns, gns in sorted(rows)[:5]:
        miss = Counter({k: v for k, v in kg["value_loose"].items() if k[0] == pid}) - Counter({k: v for k, v in kp["value_loose"].items() if k[0] == pid})
        extra = Counter({k: v for k, v in kp["value_loose"].items() if k[0] == pid}) - Counter({k: v for k, v in kg["value_loose"].items() if k[0] == pid})
        print(f"{pid} (Loose F1={fl:.3f}, Strict F1={fs:.3f}) missing={sum(miss.values())} extra={sum(extra.values())}")
        for k in list(miss)[:2]:
            print("   missing:", k[1:])
        for k in list(extra)[:2]:
            print("   extra:  ", k[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
