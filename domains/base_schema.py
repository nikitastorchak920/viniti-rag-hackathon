"""Domain contracts derived from the VINITI–SFedU data specification."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


Identifier = Annotated[str, StringConstraints(min_length=1)]
PageNumber = Annotated[int, Field(gt=0)]
DecimalText = Annotated[str, StringConstraints(pattern=r"^-?[0-9]+(?:\.[0-9]+)?$")]
CountText = Annotated[str, StringConstraints(pattern=r"^[0-9]+$")]
Year = Annotated[int, Field(ge=1000, le=9999)]
ResultOrigin = Literal["primary", "cited"]
ExtractionStatus = Literal["extracted", "present_not_extractable", "absent"]


class ContractModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class PublicationSchema(ContractModel):
    publication_id: Identifier
    title: str | None = None
    year: Year | None = None
    DOI: str | None = None
    authors: str | None = None


class ProvenanceSchema(ContractModel):
    publication_id: Identifier
    result_origin: ResultOrigin
    cited_publication_id: str | None = None
    source_page: PageNumber | None = None
    source_section: str | None = None
    source_table: str | None = None
    source_figure: str | None = None
    source_fragment: str | None = None


class RecordStatusSchema(ContractModel):
    raw_value: str | None = None
    raw_unit: str | None = None
    normalized_value: DecimalText | None = None
    normalized_unit: str | None = None
    extraction_status: ExtractionStatus


class ValidationIssueSchema(ContractModel):
    issue_id: Identifier
    rule_code: Identifier
    severity: Literal["info", "warning", "error"]
    record_id: str | None = None
    source_page: PageNumber | None = None
    source_table: str | None = None
    source_fragment: str | None = None
    message: str
