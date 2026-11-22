"""Domain 2 checks that report findings without changing numeric results."""
from decimal import Decimal
import re


RULE_SCALE_BOUNDS = "RULE_SCALE_BOUNDS"
RULE_AT_K_CONSISTENCY = "RULE_AT_K_CONSISTENCY"
RULE_UNIT_AMBIGUITY = "RULE_UNIT_AMBIGUITY"
RULE_PROVENANCE_COMPLETE = "RULE_PROVENANCE_COMPLETE"
PARTIAL_EXTRACTION = "partial_extraction"


def finding(row, rule: str, description: str) -> dict:
    return {
        "check_name": rule, "record_ids": row.get("result_id", ""), "description": description,
        "source_page": row.get("source_page", ""), "source_fragment": row.get("source_fragment", ""),
    }


def check_result(row, *, printed_cutoffs, explicit_k, top_k, bounded, difference, provenance, baseline_conflict) -> list[dict]:
    findings = [finding(row, RULE_PROVENANCE_COMPLETE, message) for message in provenance]

    def report(rule: str, message: str) -> None:
        findings.append(finding(row, rule, message))

    name, unit, value = row["metric_name"], row["metric_unit"], row["metric_value"]
    k = row["metric_k"]
    if explicit_k and not re.fullmatch(r"[0-9]+", explicit_k):
        report(RULE_AT_K_CONSISTENCY, f"{name}: reported metric_k {explicit_k!r} is not an integer.")
    if len(printed_cutoffs) > 1 or (k and any(int(k) != int(x) for x in printed_cutoffs)):
        report(RULE_AT_K_CONSISTENCY, f"{name}: metric_k conflicts with the reported cutoffs {', '.join(sorted(printed_cutoffs))}.")
    elif not k and re.search(r"@\s*k\b", name, re.I):
        report(RULE_AT_K_CONSISTENCY, f"{name}: integer metric_k is missing.")
    if top_k and k and int(k) > int(top_k) and row["extraction_status"] == "extracted":
        report(RULE_AT_K_CONSISTENCY, f"{name}: metric_k={k} exceeds configuration top_k={top_k}; check the retrieval stage.")
    if baseline_conflict:
        report(RULE_UNIT_AMBIGUITY, f"{name}: explicit percent baseline does not match the result's unit. Baseline retained in note.")
    if value:
        number = Decimal(value)
        limit = {"fraction": 1, "ratio": 1, "%": 100}.get(unit.casefold())
        if not difference and limit is not None and not 0 <= number <= limit:
            report(RULE_SCALE_BOUNDS, f"{name}={value} {unit} is outside [0, {limit}].")
        if not difference and number <= 0 and re.search(r"\blatenc\w*\b", name, re.I):
            report(RULE_SCALE_BOUNDS, f"{name}={value}: latency must be positive.")
        if (bounded and not row["raw_unit"] and "%" not in row["raw_value"]) or (difference and unit == "%"):
            report(RULE_UNIT_AMBIGUITY, f"{name}={value}: the source does not establish a unique scale. Value retained.")
    return findings
