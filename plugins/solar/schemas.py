"""Pydantic v2 wire schemas for Domain 1 (Thin-film solar cells) extraction."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


def to_text(v) -> str:
    """Coerce int/float/list/bool/None to a clean string instead of failing schema validation."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple, set)):
        return "; ".join(to_text(x) for x in v if x is not None and to_text(x) != "")
    if isinstance(v, dict):
        return "; ".join(f"{k}: {to_text(x)}" for k, x in v.items())
    if isinstance(v, bool):
        return "true" if v else "false"
    s = str(v).strip()
    if s.lower() in {"none", "null", "nan", "n/a", "na", "unknown", "nil"}:
        return ""
    return s


def to_page_int(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, (list, tuple)):
        v = v[0] if v else 0
    m = re.search(r"\d+", str(v if v is not None else ""))
    return int(m.group()) if m else 0


def to_bool_val(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    return str(v or "").strip().lower() in {"true", "1", "yes", "y"}


class SolarWireModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)


class Publication(SolarWireModel):
    title: str
    year: str
    DOI: str
    authors: str
    in_scope: bool
    exclusion_reason: str

    @field_validator("title", "year", "DOI", "authors", "exclusion_reason", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)

    @field_validator("in_scope", mode="before")
    @classmethod
    def _bool(cls, v):
        return to_bool_val(v)


class Material(SolarWireModel):
    material_id: str
    material_name_raw: str
    formula_normalized: str
    material_class: str
    dimensionality: str
    additives: str
    bandgap_value: str
    bandgap_unit: str
    bandgap_method: str
    note: str

    @field_validator("*", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)


class Device(SolarWireModel):
    device_id: str
    absorber_material_id: str
    device_label: str
    device_role: str
    device_type: str
    architecture: str
    substrate_type: str
    active_area: str
    area_unit: str
    area_definition: str
    encapsulation: str
    note: str

    @field_validator("*", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)


class Layer(SolarWireModel):
    layer_id: str
    device_id: str
    layer_order: str
    layer_function: str
    layer_material: str
    layer_thickness: str
    thickness_unit: str
    deposition_method: str
    annealing_temperature: str
    annealing_time: str
    atmosphere: str
    note: str

    @field_validator("*", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)


class Measurement(SolarWireModel):
    measurement_id: str
    device_id: str
    measurement_type: str
    spectrum: str
    light_intensity: str
    intensity_unit: str
    scan_direction: str
    scan_rate: str
    mask_used: str
    certified: str
    certification_lab: str
    temperature: str
    stability_protocol: str
    stress_conditions: str
    note: str

    @field_validator("*", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)


class MetaIssue(SolarWireModel):
    check_name: str
    description: str
    source_page: int
    source_fragment: str

    @field_validator("check_name", "description", "source_fragment", mode="before")
    @classmethod
    def _txt(cls, v):
        return to_text(v)

    @field_validator("source_page", mode="before")
    @classmethod
    def _pg(cls, v):
        return to_page_int(v)


class Meta(SolarWireModel):
    publication: Publication
    materials: list[Material]
    devices: list[Device]
    layers: list[Layer]
    measurements: list[Measurement]
    issues: list[MetaIssue]


META_COMPACT_SPEC: dict[str, tuple[type[SolarWireModel], tuple[str, ...], int]] = {
    "materials": (Material, tuple(Material.model_fields), 4),
    "devices": (Device, tuple(Device.model_fields), 4),
    "layers": (Layer, tuple(Layer.model_fields), 5),
    "measurements": (Measurement, tuple(Measurement.model_fields), 4),
    "issues": (MetaIssue, tuple(MetaIssue.model_fields), 2),
}


class CompactMeta(SolarWireModel):
    publication: Publication
    materials: list[list[str | int | float | None] | dict]
    devices: list[list[str | int | float | None] | dict]
    layers: list[list[str | int | float | None] | dict]
    measurements: list[list[str | int | float | None] | dict]
    issues: list[list[str | int | float | None] | dict]

    def expanded(self) -> dict:
        out = {"publication": self.publication.model_dump()}
        for key, (model, fields, min_len) in META_COMPACT_SPEC.items():
            items = []
            for row in getattr(self, key):
                vals: dict = dict.fromkeys(fields, "")
                if model is MetaIssue:
                    vals["source_page"] = 0
                if isinstance(row, dict):
                    for fname in fields:
                        if fname in row:
                            vals[fname] = to_page_int(row[fname]) if fname == "source_page" else to_text(row[fname])
                elif isinstance(row, list):
                    if len(row) < 1:
                        continue
                    for fname, val in zip(fields, row[:len(fields)]):
                        vals[fname] = to_page_int(val) if fname == "source_page" else to_text(val)
                else:
                    continue
                items.append(vals)
            out[key] = items
        return Meta.model_validate(out).model_dump()


class Result(SolarWireModel):
    device_id: str
    measurement_id: str
    material_id: str
    metric_name: str
    aggregation: str
    spread_value: str
    n_devices: str
    time_point: str
    time_unit: str
    raw_value: str
    raw_unit: str
    result_origin: Literal["primary", "cited", ""]
    cited_publication_id: str
    source_page: int
    source_section: str
    source_table: str
    source_figure: str
    source_fragment: str
    extraction_status: Literal["extracted", "present_not_extractable", "absent", ""]
    note: str

    @field_validator(
        "device_id", "measurement_id", "material_id", "metric_name", "aggregation",
        "spread_value", "n_devices", "time_point", "time_unit", "raw_value", "raw_unit",
        "cited_publication_id", "source_section", "source_table", "source_figure",
        "source_fragment", "note",
        mode="before",
    )
    @classmethod
    def _txt(cls, v):
        return to_text(v)

    @field_validator("result_origin", mode="before")
    @classmethod
    def _origin(cls, v):
        s = to_text(v).lower()
        return s if s in {"primary", "cited"} else ""

    @field_validator("extraction_status", mode="before")
    @classmethod
    def _status(cls, v):
        s = to_text(v).lower().replace("-", "_").replace(" ", "_")
        return s if s in {"extracted", "present_not_extractable", "absent"} else ""

    @field_validator("source_page", mode="before")
    @classmethod
    def _pg(cls, v):
        return to_page_int(v)


class Window(SolarWireModel):
    results: list[Result]


COMPACT_FIELDS = (
    "device_id", "measurement_id", "material_id", "metric_name",
    "raw_value", "raw_unit", "source_fragment", "source_page",
    "aggregation", "spread_value", "n_devices", "time_point", "time_unit",
    "result_origin", "cited_publication_id", "source_section",
    "source_table", "source_figure", "extraction_status", "note",
)
COMPACT_REQUIRED = 8


class CompactWindow(SolarWireModel):
    results: list[list[str | int | float | None] | dict]

    def expanded(self) -> dict:
        rows = []
        for row in self.results:
            fields = dict.fromkeys(COMPACT_FIELDS, "")
            fields["source_page"] = 0
            if isinstance(row, dict):
                for k in COMPACT_FIELDS:
                    if k in row:
                        fields[k] = row[k]
            elif isinstance(row, list) and len(row) >= 4:
                fields.update(zip(COMPACT_FIELDS, row[:len(COMPACT_FIELDS)]))
            else:
                continue
            rows.append(fields)
        return Window.model_validate({"results": rows}).model_dump()
