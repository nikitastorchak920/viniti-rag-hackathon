"""Domain 1 entities from slides 4–5."""
from typing import Annotated, Literal

from pydantic import Field

from domains.base_schema import (
    ContractModel, Identifier, ProvenanceSchema, PublicationSchema, RecordStatusSchema,
    ValidationIssueSchema,
)


Count = Annotated[int, Field(ge=0)]


class ThinFilmMaterialSchema(ContractModel):
    material_id: Identifier
    material_name_raw: str | None = None
    formula_normalized: str | None = None
    material_class: str | None = None
    dimensionality: str | None = None
    additives: str | None = None
    bandgap_value: float | None = None
    bandgap_unit: str | None = None
    bandgap_method: str | None = None


class ThinFilmDeviceSchema(ContractModel):
    device_id: Identifier
    device_label: str | None = None
    device_role: Literal["control", "target", "record"] | None = None
    device_type: str | None = None
    architecture: Literal["n-i-p", "p-i-n", "substrate", "superstrate"] | None = None
    substrate_type: str | None = None
    active_area: float | None = None
    area_unit: str | None = None
    area_definition: str | None = None
    encapsulation: str | None = None


class ThinFilmLayerSchema(ContractModel):
    layer_id: Identifier
    device_id: Identifier | None = None
    layer_order: Count | None = None
    layer_function: str | None = None
    layer_material: str | None = None
    layer_thickness: float | None = None
    thickness_unit: str | None = None
    deposition_method: str | None = None
    annealing_temperature: str | None = None
    annealing_time: str | None = None
    atmosphere: str | None = None


class ThinFilmMeasurementSchema(ContractModel):
    measurement_id: Identifier
    measurement_type: str | None = None
    spectrum: str | None = None
    light_intensity: str | None = None
    scan_direction: str | None = None
    scan_rate: str | None = None
    mask_used: bool | None = None
    certified: bool | None = None
    temperature: str | None = None
    stability_protocol: str | None = None
    stress_conditions: str | None = None


class ThinFilmMetricResultSchema(ProvenanceSchema, RecordStatusSchema):
    result_id: Identifier
    device_id: Identifier | None = None
    measurement_id: Identifier | None = None
    material_id: Identifier | None = None
    metric_name: Identifier
    metric_value: float | None = None
    metric_unit: str | None = None
    aggregation: Literal["champion", "mean", "median"] | None = None
    spread_value: float | None = None
    n_devices: Count | None = None
    time_point: float | None = None
    time_unit: str | None = None


class ThinFilmExtractionSchema(ContractModel):
    publication: PublicationSchema
    materials: list[ThinFilmMaterialSchema]
    devices: list[ThinFilmDeviceSchema]
    layers: list[ThinFilmLayerSchema]
    measurements: list[ThinFilmMeasurementSchema]
    results: list[ThinFilmMetricResultSchema]
    issues: list[ValidationIssueSchema]
