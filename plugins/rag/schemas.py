"""Pydantic models for LLM structured output. Every field is required (no defaults, which
Gemini response schemas handle poorly); "" means "not stated in the paper"."""
from __future__ import annotations

import re

from pydantic import BaseModel

try:  # pydantic v2
    from pydantic import field_validator

    def _coerce(*fields):
        return field_validator(*fields, mode="before")
except ImportError:  # pydantic v1
    from pydantic import validator

    def _coerce(*fields):
        return validator(*fields, pre=True, allow_reuse=True)


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


class Publication(BaseModel):
    title: str
    year: str
    doi: str
    authors: str  # "A B; C D"
    in_scope: bool
    exclusion_reason: str


class Config(BaseModel):
    config_id: str
    rag_variant: str
    retrieval_method: str
    retriever_model: str
    embedding_model: str
    embedding_version: str
    chunking_method: str
    chunk_size: str
    chunk_overlap: str
    chunk_unit: str
    index_type: str
    vector_store: str
    top_k: str
    reranker_model: str
    generator_model: str
    generator_version: str
    prompt_strategy: str
    context_strategy: str
    note: str


class Dataset(BaseModel):
    dataset_id: str
    dataset_name: str
    dataset_version: str
    language: str
    data_split: str
    scientific_domain: str
    note: str


class Task(BaseModel):
    task_id: str
    task_type: str
    note: str


class Experiment(BaseModel):
    experiment_id: str
    evaluation_protocol: str
    baseline_name: str
    hardware: str
    latency_ms: str
    tokens_per_query: str
    sample_size: str
    note: str


class MetaIssue(BaseModel):
    check_name: str
    description: str
    source_page: int
    source_fragment: str


class Meta(BaseModel):
    publication: Publication
    configurations: list[Config]
    datasets: list[Dataset]
    tasks: list[Task]
    experiments: list[Experiment]
    issues: list[MetaIssue]


class Result(BaseModel):
    experiment_id: str
    config_id: str
    dataset_id: str
    task_id: str
    metric_group: str
    metric_name: str
    metric_variant: str
    metric_direction: str
    metric_k: str
    raw_value: str
    raw_unit: str
    baseline_value: str
    aggregation: str
    sample_size: str
    result_origin: str  # primary | cited
    cited_ref: str
    source_page: int
    source_section: str
    source_table: str
    source_figure: str
    source_fragment: str
    extraction_status: str  # extracted | present_not_extractable | absent
    note: str

    @_coerce("experiment_id", "config_id", "dataset_id", "task_id", "metric_group", "metric_name", "metric_variant", "metric_direction", "metric_k", "raw_value", "raw_unit", "baseline_value", "aggregation", "sample_size", "result_origin", "cited_ref", "source_section", "source_table", "source_figure", "source_fragment", "extraction_status", "note")
    @classmethod
    def _text(cls, v):
        return to_text(v)

    @_coerce("source_page")
    @classmethod
    def _page(cls, v):
        return to_page_int(v)


class Window(BaseModel):
    results: list[Result]
