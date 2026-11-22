"""Contract-backed extraction from page-marked text and CSV export for Domain 1."""
import csv
import json
import math
import re
from decimal import Decimal
from pathlib import Path
from typing import get_args

from domains.thin_films.schema import ThinFilmExtractionSchema


_UNIT_CONVERSIONS = {
    ("pce", "fraction"): ("%", 100),
    ("ff", "fraction"): ("%", 100),
    ("voc", "mV"): ("V", Decimal("0.001")),
    ("jsc", "A/cm2"): ("mA/cm²", 1000),
    ("jsc_eqe", "A/cm2"): ("mA/cm²", 1000),
}


def _normalize_results(data: dict) -> dict:
    """Set derived result fields from explicit raw numbers and units."""
    rows = []
    for raw in data["results"]:
        row = dict(raw, metric_value=None, metric_unit=None, normalized_value=None, normalized_unit=None)
        printed = (raw.get("raw_value") or "").strip().replace("−", "-")
        match = re.fullmatch(r"([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))\s*(%)?", printed)
        unit = (raw.get("raw_unit") or "").strip()
        if raw["extraction_status"] == "extracted" and match and (not match[2] or unit in ("", "%")):
            unit = unit or (match[2] or "")
            converted_unit, factor = _UNIT_CONVERSIONS.get(
                (raw["metric_name"].casefold(), unit.replace("²", "2")), (unit, 1)
            )
            value = Decimal(match[1]) * factor
            numeric = float(value)
            if math.isfinite(numeric):
                row.update(metric_value=numeric, metric_unit=converted_unit or None,
                           normalized_value=format(value, "f") if unit else None,
                           normalized_unit=converted_unit or None)
        rows.append(row)
    return dict(data, results=rows)


def extract(client, publication_id: str, page_text: str) -> ThinFilmExtractionSchema:
    """Read one paper through the same JSON client used by the RAG plugin."""
    schema = ThinFilmExtractionSchema
    system = (
        "Extract evidence about experimental single-junction thin-film photovoltaic devices. "
        "Use only the supplied paper. Omit unknown optional fields or set them to null. "
        "Keep raw values and quotes verbatim, use physical PDF page numbers, and distinguish "
        "measurements made in the paper from measurements cited from earlier work. "
        "Leave the derived fields metric_value, metric_unit, normalized_value, and normalized_unit unset. "
        "Record contradictions as issues and keep the corresponding results. "
        "Return JSON matching this schema:\n"
        + json.dumps(schema.model_json_schema(), ensure_ascii=False, separators=(",", ":"))
    )
    data = client.generate_json(
        [f"Use publication_id {json.dumps(publication_id)} for the paper and its result rows.", page_text],
        system, schema, tag=publication_id,
    )
    paper = schema.model_validate(data)
    if paper.publication.publication_id != publication_id or any(
        row.publication_id != publication_id for row in paper.results
    ):
        raise ValueError("Response uses a different source publication ID")
    return schema.model_validate(_normalize_results(paper.model_dump()))


def write_csv(paper: ThinFilmExtractionSchema, out_dir: Path) -> None:
    """Write all contract fields, including issue severity and tables."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, field in ThinFilmExtractionSchema.model_fields.items():
        rows = getattr(paper, table)
        if table == "publication":
            table, model, rows = "publications", field.annotation, [rows]
        else:
            model, = get_args(field.annotation)
        with (out_dir / f"{table}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(model.model_fields), lineterminator="\n")
            writer.writeheader()
            writer.writerows(row.model_dump(mode="json") for row in rows)
