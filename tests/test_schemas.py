import csv
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from domains.base_schema import PublicationSchema
from domains.rag.schema import RagMetricResultSchema
from domains.rag.submission import SUBMISSION_MODELS
from domains.thin_films.pipeline import extract, write_csv
from domains.thin_films.schema import ThinFilmExtractionSchema
from plugins.rag import exporter, pipeline
from plugins.rag.schemas import COMPACT_FIELDS, CompactWindow, Result


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def test_publication_defaults_and_strict_types():
    assert PublicationSchema(publication_id="P1").model_dump() == {
        "publication_id": "P1", "title": None, "year": None, "DOI": None, "authors": None,
    }
    with pytest.raises(ValidationError):
        PublicationSchema.model_validate({"publication_id": "P1", "year": "2025"})
    with pytest.raises(ValidationError):
        PublicationSchema.model_validate({"publication_id": "P1", "doi": "10.1000/x"})


def test_rag_result_json_and_submission_preserve_fields(tmp_path):
    result = RagMetricResultSchema.model_validate({
        "publication_id": "P1", "result_id": "R1", "experiment_id": "E1",
        "config_id": "C1", "dataset_id": "D1", "task_id": "T1", "metric_group": "retrieval",
        "metric_name": "Recall", "metric_variant": "macro", "metric_direction": "higher_is_better",
        "metric_k": "5", "metric_value": "0.70", "metric_unit": "fraction",
        "baseline_value": "0.50", "aggregation": "mean", "sample_size": "25",
        "raw_value": ".70", "raw_unit": "fraction", "normalized_value": "0.70",
        "normalized_unit": "fraction", "extraction_status": "extracted", "result_origin": "cited",
        "cited_publication_id": "[3]", "source_page": 2, "source_section": "3.1",
        "source_table": "Table 2", "source_figure": "Figure 1", "source_fragment": "Recall@5 .70",
    })
    assert RagMetricResultSchema.model_validate_json(result.model_dump_json()) == result
    with pytest.raises(ValidationError):
        RagMetricResultSchema.model_validate(dict(result.model_dump(), result_origin="external"))
    with pytest.raises(ValidationError):
        RagMetricResultSchema.model_validate(dict(result.model_dump(), metric_k="2.5"))
    row = {key: str(value) for key, value in result.model_dump().items()}
    row.update(note="source checked", duplicate_of="")
    writer = exporter.TableWriter(tmp_path)
    writer.write_doc({"results": [row]})
    writer.close(True)
    official = json.loads((Path(__file__).resolve().parents[1] / "submission_template/schema.json").read_text(
        encoding="utf-8"))["tables"]
    assert exporter.columns() == official
    for table, model in SUBMISSION_MODELS.items():
        header, rows = csv_rows(tmp_path / f"{table}.csv")
        assert header == list(model.model_fields)
        assert rows == ([row] if table == "results" else [])


def test_rag_prompt_and_reply_use_the_projected_contract():
    assert set(COMPACT_FIELDS) == set(Result.model_fields)

    class Client:
        def generate_json(self, contents, system, schema, tag):
            assert schema is CompactWindow
            assert ", ".join(COMPACT_FIELDS) in system
            return {"results": [["D1", "C1", "Recall", "5", ".70", "Recall@5 .70", 2]]}

    output = pipeline._gen(Client(), ["source"], CompactWindow, "P1")
    assert output["results"][0]["source_page"] == 2
    with pytest.raises(ValidationError):
        Result.model_validate(dict(output["results"][0], extraction_status="unknown"))


def test_rag_retries_invalid_compact_results_as_named_rows():
    from plugins.rag.schemas import Window

    invalid = dict.fromkeys(COMPACT_FIELDS, "")
    invalid.update(raw_value=".70", source_page=2, extraction_status="unknown")
    valid = dict(invalid, extraction_status="extracted")
    attempts = []

    class Client:
        def generate_json(self, contents, system, schema, tag):
            attempts.append(schema)
            return {"results": [list(invalid.values()) if schema is CompactWindow else valid]}

    output = pipeline._gen(Client(), ["source"], CompactWindow, "P1")
    assert attempts == [CompactWindow, CompactWindow, CompactWindow, Window]
    assert output["results"] == [valid]


def test_thin_films_extract_normalize_and_round_trip(tmp_path):
    result = {
        "publication_id": "P1", "result_id": "R1", "device_id": "D1", "measurement_id": "M1",
        "material_id": "MAT1", "metric_name": "Voc", "aggregation": "mean",
        "spread_value": 0.05, "n_devices": 3, "time_point": 10.0, "time_unit": "h",
        "raw_value": "750", "raw_unit": "mV", "extraction_status": "extracted",
        "result_origin": "cited", "cited_publication_id": "[3]", "source_page": 2,
        "source_section": "3.1", "source_table": "Table 2", "source_figure": "Figure 1",
        "source_fragment": "Voc 750 mV",
    }
    payload = {
        "publication": {"publication_id": "P1", "title": "Thin films", "year": 2025, "DOI": "10.1000/x", "authors": "A B"},
        "materials": [{"material_id": "MAT1", "bandgap_value": 1.6, "bandgap_method": "Tauc"}],
        "devices": [{"device_id": "D1", "device_role": "target", "active_area": 0.12}],
        "layers": [{"layer_id": "L1", "device_id": "D1", "layer_order": 1}],
        "measurements": [{"measurement_id": "M1", "mask_used": False, "certified": True}],
        "results": [result, dict(result, result_id="R2", raw_value="700–800")],
        "issues": [{"issue_id": "I01", "rule_code": "range", "severity": "warning", "record_id": "R2",
                    "source_page": 2, "source_table": "Table 2", "source_fragment": "700–800",
                    "message": "Reported as a range"}],
    }

    class Client:
        def generate_json(self, contents, system, schema, tag):
            assert tag == "P1"
            assert '"bandgap_method"' in system
            assert schema is ThinFilmExtractionSchema
            return payload

    paper = extract(Client(), "P1", "--- PAGE 2 ---\nVoc 750 mV")
    assert paper.results[0].normalized_value == "0.750"
    assert paper.results[0].metric_value == 0.75
    assert paper.results[0].metric_unit == "V"
    assert paper.results[1].raw_value == "700–800"
    assert paper.results[1].normalized_value is None
    assert paper.issues[0].record_id == paper.results[1].result_id
    assert ThinFilmExtractionSchema.model_validate_json(paper.model_dump_json()) == paper
    with pytest.raises(ValidationError):
        ThinFilmExtractionSchema.model_validate(dict(payload, measurements=[{"measurement_id": "M1", "certified": "yes"}]))
    write_csv(paper, tmp_path)
    for table, records in paper:
        name, models = ("publications", [records]) if table == "publication" else (table, records)
        header, rows = csv_rows(tmp_path / f"{name}.csv")
        assert header == list(type(models[0]).model_fields)
        reloaded = [type(model).model_validate_strings({key: val for key, val in row.items() if val != ""})
                    for model, row in zip(models, rows, strict=True)]
        assert reloaded == models
