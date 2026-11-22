"""Domain 1 (Thin-film solar cells) extraction prompts."""
from __future__ import annotations

import json

from plugins.solar.schemas import COMPACT_FIELDS, COMPACT_REQUIRED, META_COMPACT_SPEC


SYSTEM = """You are a scientific data-extraction expert for Domain 1: Single-junction Thin-Film Solar Cells (photovoltaics).
Extract ONLY facts explicitly stated in the supplied paper. NEVER guess, invent, or calculate values not written in the text.
Use empty string "" for any unknown/unreported field (NEVER write "None", "null", "N/A", "unknown", or "-").
Join multiple values in a single field with "; ".

=== SCOPE RULE (in_scope) ===
- in_scope = true ONLY if the paper fabricates AND experimentally measures at least one single-junction thin-film solar cell/minimodule/module using one of these absorber classes:
  perovskite, CIGS, CdTe, kesterite (CZTS/CZTSe/CZTSSe), Sb2Se3, thin-film Si (a-Si:H, uc-Si:H), or other single-junction thin-film PV absorber.
- in_scope = false if:
  * purely computational / theoretical / simulation work with NO newly fabricated and experimentally measured solar cell (e.g., DFT, ab initio, SCAPS-1D, SILVACO, MATLAB, Maple, numerical modeling only);
  * multi-junction / tandem solar cells (2-terminal, 4-terminal, perovskite/Si, perovskite/CIGS, all-perovskite tandem);
  * pure material/film study, photodetector, LED, or review paper without experimental PV device performance.
- If in_scope = false: set exclusion_reason concisely (1 sentence explaining why), and return EMPTY lists [] for materials, devices, layers, measurements, issues.

=== STRICT VOCABULARY ===
- material_class: perovskite | CIGS | CdTe | kesterite | Sb2Se3 | thin-film Si | other
- dimensionality: 3D | 2D | 2D-3D | ""
- bandgap_method: Tauc | EQE | PL | cited | ""
- device_role: control | target | record | ""
- device_type: cell | minimodule | module | ""
- architecture: n-i-p | p-i-n | substrate | superstrate | ""  (put "planar", "mesoporous", "inverted", "regular" in note)
- substrate_type: rigid | flexible | ""
- area_definition: designated illumination | aperture | total | ""
- layer_function: front_contact | ETL | absorber | passivation | HTL | interlayer | recombination | back_contact
- measurement_type: J-V | MPP tracking | EQE | stability
- scan_direction: reverse | forward | average | ""
- stability_protocol: ISOS-D | ISOS-L | ISOS-T | other | ""
- mask_used, certified: true | false | ""
- aggregation: champion | mean | median | ""  (NEVER guess aggregation if the paper does not state best/champion/average/mean/median!)
- result_origin: primary | cited
- extraction_status: extracted | present_not_extractable | absent

=== CRITICAL DOMAIN RULES ===
1. MATERIALS (IDs: M1, M2, ...):
   - Extract absorber materials (and distinct modified/doped absorber compositions).
   - formula_normalized: expand common perovskite shorthands to A-B-X form (e.g. MAPbI3 -> CH3NH3PbI3; FAPbI3 -> CH(NH2)2PbI3; CsFAMA -> explicit printed stoichiometry if given). If the paper only lists precursor weights/molarities without giving a final chemical formula, leave formula_normalized="" and put the raw description in material_name_raw.
   - bandgap_value: ONLY the optical/electronic bandgap of the ABSORBER material (in eV). NEVER put the bandgap of ETL, HTL, HTM, or buffer layers into absorber bandgap_value! If a range is given, leave bandgap_value="" and record the range in note.
2. DEVICES (IDs: D1, D2, ...):
   - Create ONE Device per distinct experimentally fabricated device condition/variant reported in the paper (e.g. "Pristine", "Control", "Target", "0.01 M SrCl2", "200 C").
   - CRITICAL: Do NOT create extra devices for "champion"/"best"/"average" or for "reverse"/"forward"/"FB-SC"/"SC-FB" scans of the same device! Reuse the SAME device_id: scan direction goes in measurements.scan_direction, and champion vs mean goes in results.aggregation!
   - Link absorber_material_id to a valid M# ID.
   - device_label: exact concise condition label from the paper's tables/text WITHOUT words like "champion", "best", "reverse scan", "FB-SC", "SC-FB".
   - architecture: strictly one of n-i-p, p-i-n, substrate, superstrate; put planar/mesoporous/inverted details in note.
   - active_area: single numeric value (convert mm2 to cm2 if convenient or keep exact number + area_unit="mm2" or "cm2"). Never put ranges or text in active_area.
3. LAYERS (IDs: L1, L2, ...):
   - For each device (or shared stack per device_id), list physical functional layers in order from substrate (layer_order = "1", "2", "3", ...).
   - Do NOT include the glass/PEN/PET/foil substrate itself as a layer; layer 1 is usually front_contact (e.g., FTO, ITO, Mo for substrate config).
   - Map buffer layers (e.g., CdS, Zn(O,S)) -> ETL; metal grids -> front_contact; anti-reflective/seed/blocking/buffer interface layers -> interlayer; keep original printed name in note.
   - layer_thickness: single numeric value + thickness_unit (nm or um). If range, leave layer_thickness="" and write range in note.
4. MEASUREMENTS (IDs: MS1, MS2, ...):
   - List distinct measurement protocols (J-V, EQE, MPP tracking, stability).
   - Reverse scan (FB-SC / reverse) and forward scan (SC-FB / forward) MUST be SEPARATE measurement_id records!
   - List all device_id values measured under that protocol separated by "; " (e.g. "D1; D2; D3").
   - For stability tests where no ISOS protocol is named explicitly, set stability_protocol="other" and describe conditions in stress_conditions.
   - For dark J-V, set measurement_type="J-V" and note "dark J-V" in note.
5. META ISSUES:
   - Record document-level issues in issues: contradictions between text/tables/figures (e.g. conflicting contact materials, layer thicknesses, substrates, or values), derived_values (relative gains/deltas like "improved Voc by 0.127 V" not extracted as results), non-standard illumination/spectrum, or device metrics reported only in Supporting Information (SI).
   - Every source_page must be the 1-based physical PDF page number (matching --- PAGE N ---). Every source_fragment must be a short VERBATIM quote from that page."""


META_USER = """Read the ENTIRE paper above and extract the complete metadata object:
- publication (title, year, DOI, authors, in_scope, exclusion_reason)
- materials (M1, M2, ...): all absorber materials with raw name, normalized formula, class, dimensionality, additives, absorber bandgap
- devices (D1, D2, ...): every experimentally fabricated & measured device/variant in the paper (control, target, concentration/annealing/treatment series, record/champion)
- layers (L1, L2, ...): layer stacks per device_id starting at layer_order="1" (exclude bare glass/foil substrate)
- measurements (MS1, MS2, ...): all J-V (separate IDs for reverse vs forward scan!), EQE, MPP tracking, and stability protocols with spectrum, light_intensity, intensity_unit, scan_direction, scan_rate, mask_used, certified, certification_lab, temperature, stability_protocol, stress_conditions
- issues: document-level inconsistencies, derived_values (deltas/gains), non-standard lighting, SI-only mentions

Be thorough with devices and measurements so that EVERY numeric photovoltaic result in the paper's tables and text has a matching device_id, measurement_id, and material_id."""


RESULT_SYSTEM = """You are a scientific data-extraction expert for Domain 1: Single-junction Thin-Film Solar Cells.
Extract EVERY photovoltaic performance metric reported on the target PDF pages (tables AND prose AND abstract).
Return ONLY JSON matching the requested schema. NEVER guess or compute missing numbers.

=== CANONICAL METRIC NAMES (use these exact names) ===
1. PCE             - Power conversion efficiency (%)
2. Voc             - Open-circuit voltage (V or mV)
3. Jsc             - Short-circuit current density from J-V (mA/cm2 or A/m2)
4. FF              - Fill factor (% or fraction 0..1)
5. Rs              - Series resistance (Ohm*cm2 or kOhm*cm2)
6. Rsh             - Shunt resistance (Ohm*cm2 or kOhm*cm2)
7. HI              - Hysteresis index (% or fraction)
8. Jsc_EQE         - Integrated Jsc from EQE / IPCE spectrum (mA/cm2)
9. stabilized_PCE  - Stabilized / steady-state / SPO / MPP-tracked PCE (%)
10. T80            - Time to retain 80% of initial PCE (h, min, days)
11. retained_PCE   - Retained PCE after stability aging (% of initial or absolute %, record time_point and time_unit!)

=== EXTRACTION RULES ===
- Extract ALL values from every table row and text mention: champion (best/hero/max), mean (average), median, AND unspecified (aggregation="").
- NEVER guess aggregation! Set aggregation="champion" only if explicitly called champion/best/highest/maximum/hero; "mean" only if explicitly called mean/average/avg (or given with ± std dev for N devices); "median" only if explicitly called median; otherwise "".
- If a cell prints "20.12 ± 0.45" or "20.12 (19.50 ± 0.45)":
  * For "mean ± std": emit ONE row with raw_value="20.12", spread_value="0.45", aggregation="mean".
  * For "champion (mean ± std)" or "best / avg": emit TWO separate rows (one champion, one mean with spread_value)!
- Separate scan directions: Reverse (FB-SC) and Forward (SC-FB) rows MUST link to the corresponding reverse vs forward measurement_id.
- Stability results (retained_PCE, T80): fill time_point (number, e.g. "1000") and time_unit (e.g. "h", "days", "min") whenever stated.
- Duplicate mentions: if the exact same metric is reported in Abstract/text AND in a Table, extract BOTH rows (the exporter handles duplicate_of linking).
- DO NOT extract relative deltas / gains ("increased by 1.2%", "improved Voc by 0.127 V", "+15% relative gain") into results! Skip deltas.
- Cited literature results: set result_origin="cited", cited_publication_id="[12]" (or author-year ref), and set device_id="", measurement_id="".
- Unextractable plot-only or SI-only mentions (e.g. "T80 is shown in Fig. 4b" without a number, or "Table S1"): set extraction_status="present_not_extractable", raw_value="", raw_unit="".
- source_page: 1-based physical PDF page number matching --- PAGE N ---.
- source_table: e.g. "Table 1" (or "" if prose/figure). source_figure: e.g. "Figure 3" (or "").
- source_fragment: SHORT VERBATIM substring from that exact PDF page containing the value (e.g. "Voc of 1.12 V" or for dense tables "Table 1, Target" or the verbatim table row snippet)."""


def compact_meta_format() -> str:
    lines = [
        "COMPACT META FORMAT: return a JSON object with keys publication (object), materials, devices, layers, measurements, issues (each a list of positional JSON arrays; trailing empty strings may be omitted):"
    ]
    for key, (_, fields, min_len) in META_COMPACT_SPEC.items():
        cols = ", ".join(f"{i}:{f}" for i, f in enumerate(fields))
        lines.append(f"- {key} (min {min_len} cells): [{cols}]")
    return "\n".join(lines)


def compact_result_format() -> str:
    cols = ", ".join(f"{i}:{name}" for i, name in enumerate(COMPACT_FIELDS))
    return (
        f"COMPACT FORMAT: return {{\"results\": [[...], ...]}} where each row is a positional JSON array of "
        f"{COMPACT_REQUIRED} to {len(COMPACT_FIELDS)} elements in this exact order:\n"
        f"[{cols}]\n"
        f"Indices 0..{COMPACT_REQUIRED - 1} are always required (use \"\" if empty, integer for source_page). "
        f"Trailing empty strings after index {COMPACT_REQUIRED - 1} may be omitted."
    )


def _meta_summary(meta: dict) -> str:
    slim = {
        "materials": [
            {k: m.get(k, "") for k in ("material_id", "material_name_raw", "formula_normalized", "material_class", "bandgap_value")}
            for m in meta.get("materials", [])
        ],
        "devices": [
            {k: d.get(k, "") for k in ("device_id", "absorber_material_id", "device_label", "device_role", "device_type", "architecture")}
            for d in meta.get("devices", [])
        ],
        "measurements": [
            {k: ms.get(k, "") for k in ("measurement_id", "device_id", "measurement_type", "scan_direction", "spectrum", "light_intensity", "stability_protocol")}
            for ms in meta.get("measurements", [])
        ],
    }
    return json.dumps(slim, ensure_ascii=False, indent=1)


def window_user(meta: dict, first: int, last: int, part: bool = False) -> str:
    scope = f"a slice of PDF page {first}" if part else (f"PDF page {first}" if first == last else f"PDF pages {first}..{last}")
    return (
        f"KNOWN ENTITIES FROM THIS PAPER (use ONLY these exact IDs; use \"\" if cited or truly absent):\n"
        f"{_meta_summary(meta)}\n\n"
        f"Extract EVERY photovoltaic metric result (PCE, Voc, Jsc, FF, Rs, Rsh, HI, Jsc_EQE, stabilized_PCE, T80, retained_PCE) "
        f"appearing in {scope}.\n"
        f"- Do NOT extract lines inside [TABLE HEADER CONTEXT ... END HEADER CONTEXT] as results; use them only for column headers.\n"
        f"- Extract BOTH champion and mean/average rows when tables report both.\n"
        f"- Match reverse vs forward scan rows to the exact reverse vs forward measurement_id.\n"
        f"- Skip relative deltas/gains (e.g. 'increased by 0.05 V').\n"
        f"- For every row, provide exact source_page (integer) and a short VERBATIM source_fragment from that page."
    )


def verify_user(meta: dict, page: int, existing: list[str]) -> str:
    return (
        f"KNOWN ENTITIES FROM THIS PAPER:\n{_meta_summary(meta)}\n\n"
        f"ALREADY EXTRACTED ON PDF PAGE {page} (device_id|measurement_id|metric_name|raw_value|aggregation|origin):\n"
        + ("\n".join(existing) if existing else "(none)")
        + f"\n\nCarefully audit PDF page {page} (especially tables, mean±std columns, reverse/forward scan rows, EQE Jsc, "
          f"Rs/Rsh, HI, stabilized PCE, and stability T80/retained_PCE). Return ONLY MISSING results not already listed above. "
          f"If nothing is missing, return {{\"results\": []}}."
    )
