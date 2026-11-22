"""Domain 2 entities from slides 8–9."""
from typing import Literal

from domains.base_schema import (
    ContractModel, CountText, DecimalText, Identifier, ProvenanceSchema, RecordStatusSchema,
)


MetricDirection = Literal["higher_is_better", "lower_is_better", "target"]


class RagDatasetTaskSchema(ContractModel):
    dataset_id: Identifier | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    task_id: Identifier | None = None
    task_type: str | None = None
    language: str | None = None
    data_split: str | None = None
    scientific_domain: str | None = None


class RagConfigSchema(ContractModel):
    config_id: Identifier
    rag_variant: str | None = None
    retrieval_method: str | None = None
    retriever_model: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    chunking_method: str | None = None
    chunk_size: CountText | None = None
    chunk_overlap: CountText | None = None
    chunk_unit: str | None = None
    index_type: str | None = None
    vector_store: str | None = None
    top_k: CountText | None = None
    reranker_model: str | None = None


class RagGenerationSchema(ContractModel):
    generator_model: str | None = None
    generator_version: str | None = None
    prompt_strategy: str | None = None
    context_strategy: str | None = None


class RagExperimentSchema(ContractModel):
    experiment_id: Identifier
    evaluation_protocol: str | None = None
    baseline_name: str | None = None
    hardware: str | None = None
    latency_ms: DecimalText | None = None
    tokens_per_query: DecimalText | None = None
    sample_size: CountText | None = None


class RagMetricResultSchema(ProvenanceSchema, RecordStatusSchema):
    result_id: Identifier
    experiment_id: Identifier | None = None
    config_id: Identifier | None = None
    dataset_id: Identifier | None = None
    task_id: Identifier | None = None
    metric_group: str | None = None
    metric_name: Identifier
    metric_variant: str | None = None
    metric_direction: MetricDirection | None = None
    metric_k: CountText | None = None
    metric_value: DecimalText | None = None
    metric_unit: str | None = None
    baseline_value: DecimalText | None = None
    aggregation: str | None = None
    sample_size: CountText | None = None
