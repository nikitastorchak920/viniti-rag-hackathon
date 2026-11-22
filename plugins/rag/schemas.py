"""Project the domain contract onto the LLM wire format and cache v2."""
from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, create_model, field_validator

from domains.base_schema import ContractModel, ExtractionStatus, ResultOrigin
from domains.rag.schema import MetricDirection
from domains.rag.submission import SUBMISSION_MODELS


class WireModel(ContractModel):
    # Preserve the legacy input coercion for standard metadata and positional numbers.
    model_config = ConfigDict(strict=False)


def wire_fields(table, *, omit=(), rename=None, types=None):
    """Use submission/domain names while allowing unnormalized evidence as text."""
    return {(rename or {}).get(key, key): ((types or {}).get(key, str), ...)
            for key in SUBMISSION_MODELS[table].model_fields if key not in omit}


def to_text(v) -> str:
    """Models sometimes return int/float/list/None for string fields: coerce instead of failing."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple, set)):
        return "; ".join(to_text(x) for x in v if x is not None)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {to_text(x)}" for k, x in v.items())
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def to_page_int(v) -> int:
    if isinstance(v, (list, tuple)):
        v = v[0] if v else 0
    m = re.search(r"\d+", str(v if v is not None else ""))
    return int(m.group()) if m else 0


Publication = create_model("Publication", __base__=WireModel, **wire_fields(
    "publications", omit=("publication_id",), rename={"DOI": "doi"}, types={"in_scope": bool}))
Config = create_model("Config", __base__=WireModel, **wire_fields("configurations", omit=("publication_id",)))
Dataset = create_model("Dataset", __base__=WireModel, **wire_fields("datasets", omit=("publication_id",)))
Task = create_model("Task", __base__=WireModel, **wire_fields("tasks", omit=("publication_id",)))
Experiment = create_model("Experiment", __base__=WireModel, **wire_fields("experiments", omit=("publication_id",)))
MetaIssue = create_model("MetaIssue", __base__=WireModel, **wire_fields(
    "issues", omit=("publication_id", "issue_id", "record_ids"), types={"source_page": int}))


class Meta(WireModel):
    publication: Publication
    configurations: list[Config]
    datasets: list[Dataset]
    tasks: list[Task]
    experiments: list[Experiment]
    issues: list[MetaIssue]


class MetricCutoff(WireModel):
    metric_name: str
    metric_k: str
    source_fragment: str

    @field_validator("metric_name", "metric_k", "source_fragment", mode="before")
    @classmethod
    def _text(cls, value):
        return to_text(value)


class TableScope(WireModel):
    source_page: int
    source_table: str
    dataset_ids: list[str]
    config_ids: list[str]
    metric_cutoffs: list[MetricCutoff]

    @field_validator("source_page", mode="before")
    @classmethod
    def _page(cls, value):
        return to_page_int(value)


class Passport(Meta):
    table_scopes: list[TableScope]


PASSPORT_ENTITIES = {
    "configurations": (Config, ("config_id", "rag_variant", "generator_model")),
    "datasets": (Dataset, ("dataset_id", "dataset_name")),
    "tasks": (Task, ("task_id", "task_type")),
    "experiments": (Experiment, ("experiment_id", "evaluation_protocol")),
    "issues": (MetaIssue, ("check_name", "description")),
}


def passport_fields(model, first):
    return (*first, *(field for field in model.model_fields if field not in first))


def passport_rows(key):
    model, first = PASSPORT_ENTITIES[key]
    row = Annotated[list[str | int | float | None], Field(min_length=len(first), max_length=len(model.model_fields))]
    return list[row]


class CompactPassport(WireModel):
    publication: Publication
    configurations: passport_rows("configurations")
    datasets: passport_rows("datasets")
    tasks: passport_rows("tasks")
    experiments: passport_rows("experiments")
    issues: passport_rows("issues")
    table_scopes: list[TableScope]

    def expanded(self) -> dict:
        output = self.model_dump()
        for key, (model, first) in PASSPORT_ENTITIES.items():
            fields = passport_fields(model, first)
            items = []
            for row in output[key]:
                values = dict.fromkeys(fields, "")
                if model is MetaIssue:
                    values["source_page"] = 0
                values.update((field, to_page_int(value) if field == "source_page" else to_text(value))
                              for field, value in zip(fields, row))
                items.append(values)
            output[key] = items
        return Passport.model_validate(output).model_dump()


result_fields = wire_fields(
    "results", omit=("publication_id", "result_id", "metric_value", "metric_unit",
                     "normalized_value", "normalized_unit", "duplicate_of"),
    rename={"cited_publication_id": "cited_ref"},
    types={"source_page": int, "result_origin": ResultOrigin | Literal[""],
           "extraction_status": ExtractionStatus | Literal[""], "metric_direction": MetricDirection | Literal[""]},
)
Result = create_model(
    "Result", __base__=WireModel,
    __validators__={
        "text_values": field_validator(*(key for key in result_fields if key != "source_page"), mode="before")(to_text),
        "page_value": field_validator("source_page", mode="before")(to_page_int),
    },
    **result_fields,
)


class Window(WireModel):
    results: list[Result]


# Dataset and configuration IDs reference the names already present in Meta.
COMPACT_FIELDS = (
    "dataset_id", "config_id", "metric_name", "metric_k", "raw_value",
    "source_fragment", "source_page", "raw_unit", "experiment_id", "task_id",
    "source_table", "source_section", "source_figure", "result_origin", "cited_ref",
    "metric_group", "metric_variant", "metric_direction", "baseline_value",
    "aggregation", "sample_size", "extraction_status", "note",
)
COMPACT_REQUIRED = 7


class CompactWindow(WireModel):
    results: list[list[str | int | float | None]]

    @field_validator("results", mode="before")
    @classmethod
    def _lengths(cls, rows):
        if not isinstance(rows, list) or any(
            not isinstance(row, list) or not COMPACT_REQUIRED <= len(row) <= len(COMPACT_FIELDS)
            for row in rows
        ):
            raise ValueError(f"results must be positional rows of {COMPACT_REQUIRED} to {len(COMPACT_FIELDS)} cells")
        return rows

    def expanded(self) -> dict:
        rows = []
        for row in self.results:
            fields = dict.fromkeys(COMPACT_FIELDS, "")
            fields.update(zip(COMPACT_FIELDS, row))
            rows.append(fields)
        return Window.model_validate({"results": rows}).model_dump()
