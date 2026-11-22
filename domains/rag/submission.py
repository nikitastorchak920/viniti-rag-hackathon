"""Model-backed projection onto the seven-column layouts of the RAG submission."""
from copy import copy
from typing import Literal

from pydantic import create_model

from domains.base_schema import ContractModel, ProvenanceSchema, PublicationSchema, RecordStatusSchema, ValidationIssueSchema
from domains.rag.schema import RagConfigSchema, RagDatasetTaskSchema, RagExperimentSchema, RagGenerationSchema, RagMetricResultSchema


def project(*models, only=None, omit=(), rename=None):
    """Keep the source field types and constraints in a selected column order."""
    fields = {key: field for model in models for key, field in model.model_fields.items()}
    names = fields if only is None else only
    return {(rename or {}).get(key, key): (fields[key].annotation, copy(fields[key]))
            for key in names if key not in omit}


publication_key = project(PublicationSchema, only=("publication_id",))
note = {"note": (str, "")}
result_details = (key for key in RagMetricResultSchema.model_fields
                  if key not in ProvenanceSchema.model_fields and key not in RecordStatusSchema.model_fields)

SUBMISSION_MODELS = {
    "publications": create_model("SubmissionPublication", __base__=ContractModel,
                                 **project(PublicationSchema), in_scope=(Literal["true", "false"], ...),
                                 exclusion_reason=(str, "")),
    "configurations": create_model("SubmissionConfiguration", __base__=ContractModel,
                                   **publication_key, **project(RagConfigSchema, RagGenerationSchema), **note),
    "datasets": create_model("SubmissionDataset", __base__=ContractModel, **publication_key,
                             **project(RagDatasetTaskSchema, omit=("task_id", "task_type")), **note),
    "tasks": create_model("SubmissionTask", __base__=ContractModel, **publication_key,
                          **project(RagDatasetTaskSchema, only=("task_id", "task_type")), **note),
    "experiments": create_model("SubmissionExperiment", __base__=ContractModel,
                                **publication_key, **project(RagExperimentSchema), **note),
    "results": create_model("SubmissionResult", __base__=ContractModel, **publication_key,
                            **project(RagMetricResultSchema, only=result_details),
                            **project(RecordStatusSchema, omit=("extraction_status",)),
                            **project(ProvenanceSchema, omit=("publication_id",)),
                            **project(RecordStatusSchema, only=("extraction_status",)),
                            duplicate_of=(str, ""), **note),
    "issues": create_model("SubmissionIssue", __base__=ContractModel, **publication_key,
                           **project(ValidationIssueSchema,
                                     only=("issue_id", "record_id", "rule_code", "message", "source_page", "source_fragment"),
                                     rename={"record_id": "record_ids", "rule_code": "check_name", "message": "description"})),
}


def submission_row(table: str, row: dict[str, str]) -> dict[str, str]:
    """Validate normalized values and keep their exact representations in the CSV."""
    model = SUBMISSION_MODELS[table]
    # Empty CSV cells represent absent optional values. Required text may be empty.
    values = {key: value for key, value in row.items()
              if value != "" or key not in model.model_fields or model.model_fields[key].is_required()}
    validated = model.model_validate_strings(values)
    return {key: row.get(key, "") if value is not None else ""
            for key, value in validated.model_dump().items()}
