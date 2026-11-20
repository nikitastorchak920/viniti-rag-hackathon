"""Pydantic models for LLM structured output. Every field is required (no defaults, which
Gemini response schemas handle poorly); "" means "not stated in the paper"."""
from __future__ import annotations

from pydantic import BaseModel


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


class Window(BaseModel):
    results: list[Result]
