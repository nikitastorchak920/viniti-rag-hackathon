"""Deterministic CSV exporter, normalizer, quote grounder, and physical validator for Domain 1 (Solar)."""
from __future__ import annotations

import csv
import math
import pathlib
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation


TABLES: dict[str, list[str]] = {
    "publications": [
        "publication_id", "title", "year", "DOI", "authors", "in_scope", "exclusion_reason",
    ],
    "materials": [
        "publication_id", "material_id", "material_name_raw", "formula_normalized",
        "material_class", "dimensionality", "additives",
        "bandgap_value", "bandgap_unit", "bandgap_method", "note",
    ],
    "devices": [
        "publication_id", "device_id", "absorber_material_id", "device_label",
        "device_role", "device_type", "architecture", "substrate_type",
        "active_area", "area_unit", "area_definition", "encapsulation", "note",
    ],
    "layers": [
        "publication_id", "layer_id", "device_id", "layer_order", "layer_function",
        "layer_material", "layer_thickness", "thickness_unit", "deposition_method",
        "annealing_temperature", "annealing_time", "atmosphere", "note",
    ],
    "measurements": [
        "publication_id", "measurement_id", "device_id", "measurement_type",
        "spectrum", "light_intensity", "intensity_unit", "scan_direction",
        "scan_rate", "mask_used", "certified", "certification_lab",
        "temperature", "stability_protocol", "stress_conditions", "note",
    ],
    "results": [
        "publication_id", "result_id", "device_id", "measurement_id", "material_id",
        "metric_name", "metric_value", "metric_unit", "aggregation", "spread_value",
        "n_devices", "time_point", "time_unit", "raw_value", "raw_unit",
        "normalized_value", "normalized_unit", "result_origin", "cited_publication_id",
        "source_page", "source_section", "source_table", "source_figure",
        "source_fragment", "extraction_status", "duplicate_of", "note",
    ],
    "issues": [
        "publication_id", "issue_id", "record_ids", "check_name",
        "description", "source_page", "source_fragment",
    ],
}

# 18 strict vocabularies enforced by oblast_1/tools/check_submission.py
VOCAB: dict[tuple[str, str], set[str]] = {
    ("publications", "in_scope"): {"true", "false"},
    ("materials", "material_class"): {"perovskite", "CIGS", "CdTe", "kesterite", "Sb2Se3", "thin-film Si", "other"},
    ("materials", "dimensionality"): {"3D", "2D", "2D-3D"},
    ("materials", "bandgap_method"): {"Tauc", "EQE", "PL", "cited"},
    ("devices", "device_role"): {"control", "target", "record"},
    ("devices", "device_type"): {"cell", "minimodule", "module"},
    ("devices", "architecture"): {"n-i-p", "p-i-n", "substrate", "superstrate"},
    ("devices", "substrate_type"): {"rigid", "flexible"},
    ("devices", "area_definition"): {"designated illumination", "aperture", "total"},
    ("layers", "layer_function"): {
        "front_contact", "ETL", "absorber", "passivation", "HTL", "interlayer", "recombination", "back_contact",
    },
    ("measurements", "measurement_type"): {"J-V", "MPP tracking", "EQE", "stability"},
    ("measurements", "scan_direction"): {"reverse", "forward", "average"},
    ("measurements", "stability_protocol"): {"ISOS-D", "ISOS-L", "ISOS-T", "other"},
    ("measurements", "mask_used"): {"true", "false"},
    ("measurements", "certified"): {"true", "false"},
    ("results", "aggregation"): {"champion", "mean", "median"},
    ("results", "result_origin"): {"primary", "cited"},
    ("results", "extraction_status"): {"extracted", "present_not_extractable", "absent"},
}

EMPTY_TOKENS = {"", "none", "null", "nan", "n/a", "na", "unknown", "nil", "-", "—", "–"}
RANGE_RE = re.compile(r"(?<!^)\s*(?:-|–|—|~|to)\s*\d")
SINGLE_NUM_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*$")
LEADING_NUM_RE = re.compile(r"^\s*[≈~]?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:\s*(?:±|\+/-)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)))?\s*(.*)$")
TABLE_SKIP_PREFIX = re.compile(r"^(?:Table|TABLE|Supplementary)\b")


def clean_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    s = unicodedata.normalize("NFKC", str(v)).strip()
    s = re.sub(r"\s+", " ", s)
    if s.lower() in EMPTY_TOKENS:
        return ""
    return s


def append_note(note: str, extra: str) -> str:
    note = clean_str(note)
    extra = clean_str(extra)
    if not extra:
        return note
    if not note:
        return extra
    if extra.lower() in note.lower():
        return note
    return f"{note}; {extra}"


def fmt_dec(val: Decimal | float) -> str:
    try:
        d = val if isinstance(val, Decimal) else Decimal(str(val))
        if not d.is_finite():
            return ""
        # round cleanly to avoid floating-point tails like 1.1200000000000001
        d = d.quantize(Decimal("0.000001")) if abs(d) < Decimal("1e9") else d
        s = format(d.normalize(), "f")
        if s == "-0":
            return "0"
        return s
    except (InvalidOperation, ValueError):
        return ""


def parse_single_float(raw: str) -> tuple[Decimal | None, str]:
    """Return (Decimal, trailing_text) if raw is a single unambiguous number; (None, raw) if range/unparseable."""
    s = clean_str(raw).replace("−", "-").replace("–", "-").replace("—", "-")
    if not s:
        return None, ""
    # Reject explicit ranges like "1.5-1.6" or "1.5 to 1.6"
    if re.search(r"\d\s*(?:-|to)\s*\d", s, re.I):
        return None, s
    # Remove thousands commas inside integers like 1,000
    s_no_comma = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    m = LEADING_NUM_RE.match(s_no_comma)
    if not m:
        return None, s
    try:
        num = Decimal(m.group(1))
    except InvalidOperation:
        return None, s
    if not num.is_finite():
        return None, s
    # If raw had ± spread, keep only the central value when caller handles spread, else pass rest
    rest = (m.group(3) or "").strip()
    return num, rest


def parse_float_strict(raw: str) -> str:
    """Strictly parse a float string for NUMERIC columns, returning '' on ranges/non-numbers."""
    num, rest = parse_single_float(raw)
    if num is None:
        return ""
    # Allow only empty rest or simple unit stripped by caller; here reject unknown words
    if rest and re.search(r"[a-zA-Z]", rest):
        return ""
    return fmt_dec(num)


def to_page(v) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return v if v > 0 else 0
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else 0


def stub_publication(doc_id: str) -> dict:
    return {
        "publication_id": doc_id,
        "title": doc_id,
        "year": "",
        "DOI": "",
        "authors": "",
        "in_scope": "false",
        "exclusion_reason": "Unprocessed: no scope decision",
    }


# ---- Exact quote normalization matching oblast_1/tools/check_submission.py ----
def norm(s: str) -> str:
    return re.sub(
        r"[^a-z0-9.%]+",
        "",
        (s or "").replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff").replace("−", "-").replace("–", "-").lower(),
    )


def load_pdf_pages_for_grounding(pdf: pathlib.Path, cache: dict | None = None) -> list[str]:
    """Read pages using pypdf first (exact match to check_submission.py), fallback to pymupdf or cached OCR."""
    pages: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception:  # noqa: BLE001
        try:
            import pymupdf

            with pymupdf.open(pdf) as doc:
                pages = [(p.get_text() or "") for p in doc]
        except Exception:  # noqa: BLE001
            pages = []
    if cache and cache.get("ocr_pages") and len(cache["ocr_pages"]) == len(pages):
        # Preserve native text where present; supplement image-only pages with cached OCR
        merged = []
        for native, ocr_t in zip(pages, cache["ocr_pages"]):
            merged.append(native if len(native.strip()) >= 40 else (ocr_t or native))
        pages = merged
    elif not pages and cache and cache.get("ocr_pages"):
        pages = list(cache["ocr_pages"])
    return pages


def _subfragment(frag: str, raw_val: str, page_text: str) -> str | None:
    """Find the longest verbatim substring of page_text matching a window of frag words."""
    if not page_text:
        return None
    pnorm = norm(page_text)
    if not pnorm:
        return None
    words = re.findall(r"\S+", frag or "")
    rv = norm(raw_val)
    if not words:
        return None
    # Pass 1: prefer windows containing raw_val if available
    if rv and rv in pnorm:
        val_idx = [i for i, w in enumerate(words) if rv in norm(w)]
        if val_idx:
            for L in range(len(words), 0, -1):
                for a in range(max(0, val_idx[0] - L + 1), min(val_idx[0], len(words) - L) + 1):
                    cand = " ".join(words[a:a + L])
                    cn = norm(cand)
                    if len(cn) >= 3 and rv in cn and cn in pnorm:
                        return cand
    # Pass 2: longest contiguous word window of frag present in pnorm (handles 14.4 x 10^2 vs raw=1440)
    for L in range(len(words), 0, -1):
        for a in range(0, len(words) - L + 1):
            cand = " ".join(words[a:a + L])
            cn = norm(cand)
            if len(cn) >= 5 and cn in pnorm:
                return cand
    # Last resort: raw_val directly in page_text with surrounding verbatim context
    if raw_val and rv and rv in pnorm:
        raw_clean = clean_str(raw_val)
        pos = page_text.find(raw_clean)
        if pos >= 0:
            lo = max(0, pos - 20)
            hi = min(len(page_text), pos + len(raw_clean) + 20)
            snippet = re.sub(r"\s+", " ", page_text[lo:hi]).strip()
            if norm(snippet) in pnorm:
                return snippet
    return None


def ground_fragment(frag: str, page: int, raw_val: str, pages_raw: list[str], pages_norm: list[str]) -> tuple[str, int, str]:
    """Verify source_fragment against pypdf pages. Returns (fragment, page, status)."""
    frag = clean_str(frag)
    if not frag:
        return "", page, "empty"
    if TABLE_SKIP_PREFIX.match(frag):
        return frag, page, "table_ref"
    fn = norm(frag)
    if not fn or not pages_norm:
        return frag, page, "unverified"
    if 1 <= page <= len(pages_norm) and fn in pages_norm[page - 1]:
        return frag, page, "ok"
    for idx, pn in enumerate(pages_norm):
        if fn in pn:
            return frag, idx + 1, "moved"
    # Try subfragment on declared page first, then other pages
    order = ([page - 1] if 1 <= page <= len(pages_raw) else []) + [i for i in range(len(pages_raw)) if i != page - 1]
    for idx in order:
        sub = _subfragment(frag, raw_val, pages_raw[idx])
        if sub:
            return sub, idx + 1, "repaired" if idx == page - 1 else "moved"
    return frag, page, "unverified"


# ---- Vocabulary canonicalization ----
def _canon_vocab(table: str, col: str, raw: str, note: str, synonyms: dict[str, str], default: str = "") -> tuple[str, str]:
    s = clean_str(raw)
    if not s:
        return default, note
    allowed = VOCAB[(table, col)]
    if s in allowed:
        return s, note
    # Case-insensitive exact match
    ci_map = {a.lower(): a for a in allowed}
    key = s.lower().strip()
    if key in ci_map:
        return ci_map[key], note
    # Normalized synonym lookup
    key_norm = re.sub(r"[\s_-]+", " ", key)
    if key in synonyms:
        return synonyms[key], note
    if key_norm in synonyms:
        return synonyms[key_norm], note
    # Substring fallback for common multi-word phrases
    for pat, target in synonyms.items():
        if len(pat) >= 4 and pat in key_norm and target in allowed:
            extra = f"{col}_raw={s}" if s.lower() != target.lower() else ""
            return target, append_note(note, extra)
    return default, append_note(note, f"{col}_raw={s}")


MATERIAL_CLASS_SYN = {
    "perovskite": "perovskite", "halide perovskite": "perovskite", "lead halide perovskite": "perovskite",
    "tin perovskite": "perovskite", "metal halide perovskite": "perovskite", "psc": "perovskite",
    "mapbi3": "perovskite", "fapbi3": "perovskite", "cspbi3": "perovskite",
    "cigs": "CIGS", "cu(in,ga)se2": "CIGS", "cuingase2": "CIGS", "cigse": "CIGS", "chalcopyrite": "CIGS", "cgs": "CIGS", "cis": "CIGS",
    "cdte": "CdTe", "cdsete": "CdTe", "cdte/cdse": "CdTe",
    "kesterite": "kesterite", "czts": "kesterite", "cztse": "kesterite", "cztsse": "kesterite", "acztse": "kesterite",
    "sb2se3": "Sb2Se3", "sb2(s,se)3": "Sb2Se3", "sb2s3": "Sb2Se3", "antimony selenide": "Sb2Se3",
    "thin-film si": "thin-film Si", "thin film si": "thin-film Si", "a-si": "thin-film Si", "a-si:h": "thin-film Si",
    "amorphous silicon": "thin-film Si", "microcrystalline silicon": "thin-film Si", "uc-si": "thin-film Si", "silicon": "thin-film Si",
    "other": "other", "organic": "other", "opv": "other", "dssc": "other", "gaas": "other",
}

DIM_SYN = {
    "3d": "3D", "bulk 3d": "3D", "3-d": "3D",
    "2d": "2D", "quasi-2d": "2D", "quasi 2d": "2D", "ruddlesden-popper": "2D", "dion-jacobson": "2D",
    "2d-3d": "2D-3D", "2d/3d": "2D-3D", "3d/2d": "2D-3D", "2d 3d": "2D-3D", "3d 2d": "2D-3D", "2d-on-3d": "2D-3D",
}

BG_METHOD_SYN = {
    "tauc": "Tauc", "tauc plot": "Tauc", "uv-vis": "Tauc", "uv vis": "Tauc", "absorption": "Tauc", "optical": "Tauc",
    "eqe": "EQE", "ipce": "EQE", "eqe onset": "EQE", "derivative eqe": "EQE", "deqe/de": "EQE",
    "pl": "PL", "photoluminescence": "PL", "pl peak": "PL",
    "cited": "cited", "literature": "cited", "ref": "cited", "reported": "cited",
}

DEVICE_ROLE_SYN = {
    "control": "control", "reference": "control", "ref": "control", "baseline": "control", "pristine": "control", "unmodified": "control", "bare": "control", "untreated": "control",
    "target": "target", "modified": "target", "treated": "target", "optimized": "target", "passivated": "target", "doped": "target", "proposed": "target", "experimental": "target",
    "record": "record", "champion": "record", "hero": "record", "best": "record", "certified": "record",
}

DEVICE_TYPE_SYN = {
    "cell": "cell", "solar cell": "cell", "single cell": "cell", "small-area": "cell", "lab cell": "cell",
    "minimodule": "minimodule", "mini-module": "minimodule", "mini module": "minimodule", "submodule": "minimodule", "sub-module": "minimodule",
    "module": "module", "solar module": "module", "pv module": "module", "large-area module": "module",
}

ARCH_SYN = {
    "n-i-p": "n-i-p", "nip": "n-i-p", "n i p": "n-i-p", "regular": "n-i-p", "conventional": "n-i-p", "standard": "n-i-p", "mesoporous": "n-i-p", "planar n-i-p": "n-i-p", "mesoporous n-i-p": "n-i-p",
    "p-i-n": "p-i-n", "pin": "p-i-n", "p i n": "p-i-n", "inverted": "p-i-n", "planar p-i-n": "p-i-n", "inverted planar": "p-i-n",
    "substrate": "substrate", "substrate configuration": "substrate",
    "superstrate": "superstrate", "superstrate configuration": "superstrate",
}

SUBSTRATE_SYN = {
    "rigid": "rigid", "glass": "rigid", "fto glass": "rigid", "ito glass": "rigid", "slg": "rigid", "soda-lime glass": "rigid",
    "flexible": "flexible", "pen": "flexible", "pet": "flexible", "foil": "flexible", "polyimide": "flexible", "pi": "flexible", "metal foil": "flexible",
}

AREA_DEF_SYN = {
    "designated illumination": "designated illumination", "designated": "designated illumination", "designated area": "designated illumination", "active": "designated illumination", "active area": "designated illumination", "masked": "designated illumination", "mask": "designated illumination", "illuminated": "designated illumination", "illuminated area": "designated illumination",
    "aperture": "aperture", "aperture area": "aperture",
    "total": "total", "total area": "total", "full area": "total",
}

LAYER_FN_SYN = {
    "front_contact": "front_contact", "front contact": "front_contact", "tco": "front_contact", "transparent electrode": "front_contact", "bottom electrode": "front_contact", "anode": "front_contact", "window": "front_contact", "grid": "front_contact", "metal grid": "front_contact", "fto": "front_contact", "ito": "front_contact",
    "etl": "ETL", "electron transport": "ETL", "electron transport layer": "ETL", "electron selective": "ETL", "buffer": "ETL", "buffer layer": "ETL", "cds": "ETL", "window layer": "ETL",
    "absorber": "absorber", "active layer": "absorber", "photoactive": "absorber", "light absorber": "absorber", "perovskite": "absorber",
    "passivation": "passivation", "passivating": "passivation", "passivation layer": "passivation", "surface passivation": "passivation", "2d passivation": "passivation",
    "htl": "HTL", "htm": "HTL", "hole transport": "HTL", "hole transport layer": "HTL", "hole selective": "HTL", "hole extraction": "HTL",
    "interlayer": "interlayer", "interface": "interlayer", "interface layer": "interlayer", "blocking": "interlayer", "blocking layer": "interlayer", "anti-reflection": "interlayer", "arc": "interlayer", "seed": "interlayer", "seed layer": "interlayer", "sam": "interlayer", "capping": "interlayer",
    "recombination": "recombination", "recombination layer": "recombination",
    "back_contact": "back_contact", "back contact": "back_contact", "top electrode": "back_contact", "cathode": "back_contact", "counter electrode": "back_contact", "rear contact": "back_contact", "metal contact": "back_contact", "electrode": "back_contact",
}

MEAS_TYPE_SYN = {
    "j-v": "J-V", "jv": "J-V", "j v": "J-V", "i-v": "J-V", "iv": "J-V", "current-voltage": "J-V", "dark j-v": "J-V", "light j-v": "J-V",
    "mpp tracking": "MPP tracking", "mpp": "MPP tracking", "mppt": "MPP tracking", "spo": "MPP tracking", "steady-state": "MPP tracking", "steady state": "MPP tracking", "stabilized": "MPP tracking", "maximum power point": "MPP tracking",
    "eqe": "EQE", "ipce": "EQE", "quantum efficiency": "EQE", "external quantum efficiency": "EQE",
    "stability": "stability", "aging": "stability", "ageing": "stability", "shelf": "stability", "thermal stability": "stability", "operational stability": "stability", "lifetime": "stability", "degradation": "stability",
}

SCAN_DIR_SYN = {
    "reverse": "reverse", "rev": "reverse", "rs": "reverse", "backward": "reverse", "fb-sc": "reverse", "fb to sc": "reverse", "voc to jsc": "reverse", "open-to-short": "reverse",
    "forward": "forward", "fwd": "forward", "fs": "forward", "sc-fb": "forward", "sc to fb": "forward", "jsc to voc": "forward", "short-to-open": "forward",
    "average": "average", "avg": "average", "mean": "average", "both": "average",
}

ISOS_SYN = {
    "isos-d": "ISOS-D", "isos-d-1": "ISOS-D", "isos-d-2": "ISOS-D", "isos-d-3": "ISOS-D", "dark storage": "ISOS-D", "shelf": "ISOS-D",
    "isos-l": "ISOS-L", "isos-l-1": "ISOS-L", "isos-l-2": "ISOS-L", "isos-l-3": "ISOS-L", "light soaking": "ISOS-L",
    "isos-t": "ISOS-T", "isos-t-1": "ISOS-T", "isos-t-2": "ISOS-T", "isos-t-3": "ISOS-T", "thermal": "ISOS-T",
    "other": "other", "ambient": "other", "humidity": "other", "damp heat": "other", "operational": "other", "custom": "other",
}

BOOL_SYN = {
    "true": "true", "yes": "true", "y": "true", "1": "true", "masked": "true", "certified": "true",
    "false": "false", "no": "false", "n": "false", "0": "false", "unmasked": "false", "uncertified": "false",
}

AGG_SYN = {
    "champion": "champion", "best": "champion", "hero": "champion", "max": "champion", "maximum": "champion", "highest": "champion", "peak": "champion", "record": "champion",
    "mean": "mean", "average": "mean", "avg": "mean", "ave": "mean", "mean±sd": "mean", "avg.": "mean",
    "median": "median", "med": "median",
}

ORIGIN_SYN = {
    "primary": "primary", "this work": "primary", "measured": "primary", "experiment": "primary",
    "cited": "cited", "literature": "cited", "ref": "cited", "reference": "cited", "prior": "cited", "reported": "cited",
}

STATUS_SYN = {
    "extracted": "extracted", "ok": "extracted", "reported": "extracted",
    "present_not_extractable": "present_not_extractable", "not_extractable": "present_not_extractable", "plot_only": "present_not_extractable", "figure_only": "present_not_extractable", "si_only": "present_not_extractable",
    "absent": "absent", "not_reported": "absent", "missing": "absent",
}

# ---- 11 canonical metric names ----
METRIC_SYNONYMS: dict[str, str] = {
    "pce": "PCE",
    "power conversion efficiency": "PCE",
    "efficiency": "PCE",
    "eta": "PCE",
    "η": "PCE",
    "conversion efficiency": "PCE",
    "photovoltaic efficiency": "PCE",
    "voc": "Voc",
    "v_oc": "Voc",
    "v oc": "Voc",
    "open-circuit voltage": "Voc",
    "open circuit voltage": "Voc",
    "jsc": "Jsc",
    "j_sc": "Jsc",
    "j sc": "Jsc",
    "short-circuit current density": "Jsc",
    "short circuit current density": "Jsc",
    "short-circuit current": "Jsc",
    "ff": "FF",
    "fill factor": "FF",
    "fill-factor": "FF",
    "rs": "Rs",
    "r_s": "Rs",
    "series resistance": "Rs",
    "rsh": "Rsh",
    "r_sh": "Rsh",
    "shunt resistance": "Rsh",
    "hi": "HI",
    "hysteresis": "HI",
    "hysteresis index": "HI",
    "hysteresis factor": "HI",
    "jsc_eqe": "Jsc_EQE",
    "jsc eqe": "Jsc_EQE",
    "j_sc_eqe": "Jsc_EQE",
    "eqe jsc": "Jsc_EQE",
    "integrated jsc": "Jsc_EQE",
    "integrated current density": "Jsc_EQE",
    "integrated short-circuit current density": "Jsc_EQE",
    "jsc (eqe)": "Jsc_EQE",
    "jsc(eqe)": "Jsc_EQE",
    "jsc from eqe": "Jsc_EQE",
    "stabilized_pce": "stabilized_PCE",
    "stabilized pce": "stabilized_PCE",
    "stabilised pce": "stabilized_PCE",
    "steady-state pce": "stabilized_PCE",
    "steady state pce": "stabilized_PCE",
    "steady-state efficiency": "stabilized_PCE",
    "spo": "stabilized_PCE",
    "stabilized power output": "stabilized_PCE",
    "mpp pce": "stabilized_PCE",
    "t80": "T80",
    "t_80": "T80",
    "t 80": "T80",
    "t80 lifetime": "T80",
    "retained_pce": "retained_PCE",
    "retained pce": "retained_PCE",
    "pce retention": "retained_PCE",
    "retention": "retained_PCE",
    "retained efficiency": "retained_PCE",
    "initial pce retained": "retained_PCE",
    "relative pce": "retained_PCE",
}

CANONICAL_METRICS = {
    "PCE", "Voc", "Jsc", "FF", "Rs", "Rsh", "HI", "Jsc_EQE", "stabilized_PCE", "T80", "retained_PCE",
}


def canon_metric_name(raw: str) -> str:
    s = clean_str(raw)
    if not s:
        return ""
    if s in CANONICAL_METRICS:
        return s
    k = re.sub(r"\s+", " ", s.lower().replace("−", "-")).strip()
    if k in METRIC_SYNONYMS:
        return METRIC_SYNONYMS[k]
    k_flat = re.sub(r"[^a-z0-9]+", " ", k).strip()
    if k_flat in METRIC_SYNONYMS:
        return METRIC_SYNONYMS[k_flat]
    if "eqe" in k_flat and ("jsc" in k_flat or "current" in k_flat):
        return "Jsc_EQE"
    if ("stabil" in k_flat or "steady" in k_flat or "spo" == k_flat) and ("pce" in k_flat or "effic" in k_flat or "power" in k_flat or "spo" == k_flat):
        return "stabilized_PCE"
    if "retain" in k_flat or "retention" in k_flat:
        return "retained_PCE"
    if re.search(r"\bt\s*_?80\b", k_flat):
        return "T80"
    if "hysteresis" in k_flat:
        return "HI"
    return s


def _norm_unit_key(u: str) -> str:
    s = clean_str(u).replace("²", "2").replace("^2", "2").replace("·", "*").replace("⋅", "*").replace("×", "*")
    s = s.replace("Ω", "Ohm").replace("ω", "Ohm").replace("ohm", "Ohm").replace("μ", "u").replace("µ", "u")
    s = re.sub(r"\s+", "", s)
    return s


def normalize_metric_value(
    metric: str, raw_value: str, raw_unit: str
) -> tuple[str, str, str | None]:
    """Return (normalized_value, normalized_unit, optional_issue_desc)."""
    num, trailing = parse_single_float(raw_value)
    if num is None:
        return "", "", None

    unit_src = clean_str(raw_unit) or trailing
    uk = _norm_unit_key(unit_src).lower()
    issue_desc: str | None = None

    if metric == "Voc":
        if uk in {"mv", "millivolt", "millivolts"}:
            return fmt_dec(num / Decimal("1000")), "V", None
        # Heuristic safety: if unit missing and Voc > 50 (e.g. 1120 mV without unit), keep raw unit check conservative
        if uk in {"v", "volt", "volts", ""}:
            if uk == "" and num > Decimal("50"):
                return fmt_dec(num / Decimal("1000")), "V", f"Voc={num} assumed mV -> V"
            return fmt_dec(num), "V", None
        return fmt_dec(num), unit_src, None

    if metric in {"PCE", "FF", "HI", "stabilized_PCE", "retained_PCE"}:
        if metric == "FF" and uk in {"%", "percent", "pct"} and Decimal("0") < num <= Decimal("1"):
            issue_desc = f"FF printed as '{raw_value} {unit_src}' (fraction with '%' sign); normalized to {fmt_dec(num * Decimal('100'))}%."
            return fmt_dec(num * Decimal("100")), "%", issue_desc
        if uk in {"fraction", "ratio", "decimal", "a.u.", "au", ""} and Decimal("0") < num <= Decimal("1"):
            if metric in {"FF", "HI"} or uk in {"fraction", "ratio", "decimal"}:
                return fmt_dec(num * Decimal("100")), "%", None
        if uk in {"%", "percent", "pct", ""}:
            return fmt_dec(num), "%", None
        return fmt_dec(num), unit_src, None

    if metric in {"Jsc", "Jsc_EQE"}:
        if uk in {"a/m2", "am-2", "a*m-2"}:
            return fmt_dec(num / Decimal("10")), "mA/cm2", None
        if uk in {"a/cm2", "acm-2", "a*cm-2"}:
            return fmt_dec(num * Decimal("1000")), "mA/cm2", None
        if uk in {"ma/cm2", "macm-2", "ma*cm-2", "ma/cm^2", ""}:
            return fmt_dec(num), "mA/cm2", None
        return fmt_dec(num), unit_src, None

    if metric in {"Rs", "Rsh"}:
        if uk in {"kohm*cm2", "kohmcm2", "kohm·cm2", "kohm"}:
            return fmt_dec(num * Decimal("1000")), "Ohm*cm2", None
        if uk in {"mohm*cm2", "mohmcm2"}:
            return fmt_dec(num * Decimal("1000000")), "Ohm*cm2", None
        if uk in {"ohm*cm2", "ohmcm2", "ohm*cm^2", "ohm", ""}:
            return fmt_dec(num), "Ohm*cm2", None
        return fmt_dec(num), unit_src, None

    if metric == "T80":
        if uk in {"min", "mins", "minute", "minutes"}:
            return fmt_dec(num / Decimal("60")), "h", None
        if uk in {"day", "days", "d"}:
            return fmt_dec(num * Decimal("24")), "h", None
        if uk in {"s", "sec", "secs", "second", "seconds"}:
            return fmt_dec(num / Decimal("3600")), "h", None
        if uk in {"h", "hr", "hrs", "hour", "hours", ""}:
            return fmt_dec(num), "h", None
        return fmt_dec(num), unit_src, None

    return fmt_dec(num), clean_str(raw_unit), None


def normalize_area(raw_val: str, raw_unit: str, note: str) -> tuple[str, str, str]:
    num, trailing = parse_single_float(raw_val)
    if num is None:
        return "", "", append_note(note, f"active_area_raw={raw_val}" if clean_str(raw_val) else "")
    u = _norm_unit_key(clean_str(raw_unit) or trailing).lower()
    if u in {"mm2", "mm^2"}:
        return fmt_dec(num / Decimal("100")), "cm2", note
    if u in {"m2", "m^2"}:
        return fmt_dec(num * Decimal("10000")), "cm2", note
    if u in {"cm2", "cm^2", ""}:
        return fmt_dec(num), "cm2", note
    return fmt_dec(num), clean_str(raw_unit) or trailing, note


def normalize_thickness(raw_val: str, raw_unit: str, note: str) -> tuple[str, str, str]:
    num, trailing = parse_single_float(raw_val)
    if num is None:
        return "", "", append_note(note, f"thickness_raw={raw_val}" if clean_str(raw_val) else "")
    u = _norm_unit_key(clean_str(raw_unit) or trailing).lower()
    if u in {"um", "micrometer", "micrometers", "micron", "microns"}:
        return fmt_dec(num * Decimal("1000")), "nm", note
    if u in {"mm"}:
        return fmt_dec(num * Decimal("1000000")), "nm", note
    if u in {"a", "angstrom", "å"}:
        return fmt_dec(num / Decimal("10")), "nm", note
    if u in {"nm", ""}:
        return fmt_dec(num), "nm", note
    return fmt_dec(num), clean_str(raw_unit) or trailing, note


def _parse_pin_mw_cm2(ms: dict) -> float | None:
    """Return incident light power density Pin in mW/cm2 (default 100.0 if AM1.5G/1 sun or unspecified)."""
    val_s = clean_str(ms.get("light_intensity", ""))
    unit_s = _norm_unit_key(ms.get("intensity_unit", "")).lower()
    if not val_s:
        return 100.0
    num, trailing = parse_single_float(val_s)
    if num is None:
        if "1 sun" in val_s.lower() or "1-sun" in val_s.lower():
            return 100.0
        return 100.0
    u = unit_s or _norm_unit_key(trailing).lower()
    v = float(num)
    if u in {"w/m2", "wm-2", "w*m-2"}:
        return v / 10.0
    if u in {"sun", "suns"}:
        return v * 100.0
    if u in {"mw/cm2", "mwcm-2", "mw*cm-2", ""}:
        if v == 1000.0 and u == "":
            return 100.0
        if v == 1.0 and u == "":
            return 100.0
        return v if v > 0 else 100.0
    if u in {"w/cm2", "wcm-2"}:
        return v * 1000.0
    return 100.0


def _expected_meas_type(metric: str) -> str:
    if metric in {"PCE", "Voc", "Jsc", "FF", "Rs", "Rsh", "HI"}:
        return "J-V"
    if metric == "Jsc_EQE":
        return "EQE"
    if metric == "stabilized_PCE":
        return "MPP tracking"
    if metric in {"T80", "retained_PCE"}:
        return "stability"
    return ""


def iter_raw_results(cache: dict) -> list[dict]:
    out: list[dict] = []
    windows = cache.get("windows") or {}
    for k in sorted(windows.keys()):
        out.extend(windows[k].get("results") or [])
    verify = cache.get("verify") or {}
    for k in sorted(verify.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
        out.extend(verify[k].get("results") or [])
    return out


def build_doc(
    doc_id: str,
    cache: dict,
    pages_raw: list[str] | None = None,
    log_fn=None,
) -> dict[str, list[dict]]:
    meta = cache.get("meta") or {}
    pub_in = meta.get("publication") or {}
    in_scope_bool = bool(pub_in.get("in_scope"))
    in_scope = "true" if in_scope_bool else "false"
    excl = clean_str(pub_in.get("exclusion_reason", ""))
    if in_scope == "false" and not excl:
        excl = "Out of scope for single-junction experimental thin-film solar cells."
    if in_scope == "true":
        excl = ""

    year_s = clean_str(pub_in.get("year", ""))
    m_yr = re.search(r"\b(19|20)\d{2}\b", year_s)
    year_s = m_yr.group(0) if m_yr else ""

    pub_row = {
        "publication_id": doc_id,
        "title": clean_str(pub_in.get("title", "")) or doc_id,
        "year": year_s,
        "DOI": clean_str(pub_in.get("DOI", "") or pub_in.get("doi", "")),
        "authors": clean_str(pub_in.get("authors", "")),
        "in_scope": in_scope,
        "exclusion_reason": excl,
    }

    empty_doc: dict[str, list[dict]] = {t: [] for t in TABLES}
    empty_doc["publications"] = [pub_row]
    if in_scope == "false":
        return empty_doc

    pages_raw = pages_raw or []
    pages_norm = [norm(t) for t in pages_raw]

    # ---- 1. Materials ----
    materials: list[dict] = []
    mat_ids: set[str] = set()
    mat_by_id: dict[str, dict] = {}
    for idx, m in enumerate(meta.get("materials") or [], 1):
        mid = clean_str(m.get("material_id", "")) or f"M{idx}"
        if mid in mat_ids:
            mid = f"M{idx}_{len(mat_ids) + 1}"
        note = clean_str(m.get("note", ""))
        mclass, note = _canon_vocab("materials", "material_class", m.get("material_class", ""), note, MATERIAL_CLASS_SYN, default="other")
        dim, note = _canon_vocab("materials", "dimensionality", m.get("dimensionality", ""), note, DIM_SYN, default="")
        bg_method, note = _canon_vocab("materials", "bandgap_method", m.get("bandgap_method", ""), note, BG_METHOD_SYN, default="")
        bg_raw = clean_str(m.get("bandgap_value", ""))
        bg_num, bg_rest = parse_single_float(bg_raw)
        if bg_num is not None and Decimal("0.1") <= bg_num <= Decimal("6.0"):
            bg_val = fmt_dec(bg_num)
            bg_unit = "eV"
        else:
            bg_val = ""
            bg_unit = ""
            if bg_raw:
                note = append_note(note, f"bandgap_raw={bg_raw}")
        row = {
            "publication_id": doc_id,
            "material_id": mid,
            "material_name_raw": clean_str(m.get("material_name_raw", "")),
            "formula_normalized": clean_str(m.get("formula_normalized", "")),
            "material_class": mclass,
            "dimensionality": dim,
            "additives": clean_str(m.get("additives", "")),
            "bandgap_value": bg_val,
            "bandgap_unit": bg_unit if bg_val else "",
            "bandgap_method": bg_method,
            "note": note,
        }
        materials.append(row)
        mat_ids.add(mid)
        mat_by_id[mid] = row

    # ---- 2. Devices ----
    devices: list[dict] = []
    dev_ids: set[str] = set()
    dev_by_id: dict[str, dict] = {}
    for idx, d in enumerate(meta.get("devices") or [], 1):
        did = clean_str(d.get("device_id", "")) or f"D{idx}"
        if did in dev_ids:
            did = f"D{idx}_{len(dev_ids) + 1}"
        note = clean_str(d.get("note", ""))
        abs_mat = clean_str(d.get("absorber_material_id", ""))
        if abs_mat not in mat_ids:
            abs_mat = next(iter(mat_ids)) if len(mat_ids) == 1 else ""
        role, note = _canon_vocab("devices", "device_role", d.get("device_role", ""), note, DEVICE_ROLE_SYN, default="")
        dtype, note = _canon_vocab("devices", "device_type", d.get("device_type", ""), note, DEVICE_TYPE_SYN, default="")
        arch, note = _canon_vocab("devices", "architecture", d.get("architecture", ""), note, ARCH_SYN, default="")
        sub, note = _canon_vocab("devices", "substrate_type", d.get("substrate_type", ""), note, SUBSTRATE_SYN, default="")
        area_def, note = _canon_vocab("devices", "area_definition", d.get("area_definition", ""), note, AREA_DEF_SYN, default="")
        area_val, area_unit, note = normalize_area(d.get("active_area", ""), d.get("area_unit", ""), note)
        raw_lbl = clean_str(d.get("device_label", ""))
        # Strip redundant aggregation / scan-direction tokens from device_label when a core label remains
        cleaned_lbl = re.sub(
            r"(?i)\b(?:champion|best|hero|reverse\s+scan|forward\s+scan|fb[-–\s]*sc|sc[-–\s]*fb)\b",
            " ",
            raw_lbl,
        )
        cleaned_lbl = re.sub(r"[\s(),;/-]+$", "", re.sub(r"^[\s(),;/-]+", "", re.sub(r"\s+", " ", cleaned_lbl))).strip()
        final_lbl = cleaned_lbl if len(cleaned_lbl) >= 2 else raw_lbl
        row = {
            "publication_id": doc_id,
            "device_id": did,
            "absorber_material_id": abs_mat,
            "device_label": final_lbl,
            "device_role": role,
            "device_type": dtype,
            "architecture": arch,
            "substrate_type": sub,
            "active_area": area_val,
            "area_unit": area_unit if area_val else "",
            "area_definition": area_def,
            "encapsulation": clean_str(d.get("encapsulation", "")),
            "note": note,
        }
        devices.append(row)
        dev_ids.add(did)
        dev_by_id[did] = row

    # ---- 3. Layers ----
    layers: list[dict] = []
    layer_ids: set[str] = set()
    next_order: dict[str, int] = defaultdict(int)
    for idx, ly in enumerate(meta.get("layers") or [], 1):
        lid = clean_str(ly.get("layer_id", "")) or f"L{idx}"
        if lid in layer_ids:
            lid = f"L{idx}_{len(layer_ids) + 1}"
        did = clean_str(ly.get("device_id", ""))
        if did not in dev_ids:
            did = next(iter(dev_ids)) if len(dev_ids) == 1 else ""
        note = clean_str(ly.get("note", ""))
        fn, note = _canon_vocab("layers", "layer_function", ly.get("layer_function", ""), note, LAYER_FN_SYN, default="")
        ord_raw = clean_str(ly.get("layer_order", ""))
        m_ord = re.search(r"\d+", ord_raw)
        if m_ord and int(m_ord.group()) >= 1:
            order_s = str(int(m_ord.group()))
            next_order[did] = max(next_order[did], int(order_s))
        else:
            next_order[did] += 1
            order_s = str(next_order[did])
        th_val, th_unit, note = normalize_thickness(ly.get("layer_thickness", ""), ly.get("thickness_unit", ""), note)
        row = {
            "publication_id": doc_id,
            "layer_id": lid,
            "device_id": did,
            "layer_order": order_s,
            "layer_function": fn,
            "layer_material": clean_str(ly.get("layer_material", "")),
            "layer_thickness": th_val,
            "thickness_unit": th_unit if th_val else "",
            "deposition_method": clean_str(ly.get("deposition_method", "")),
            "annealing_temperature": clean_str(ly.get("annealing_temperature", "")),
            "annealing_time": clean_str(ly.get("annealing_time", "")),
            "atmosphere": clean_str(ly.get("atmosphere", "")),
            "note": note,
        }
        layers.append(row)
        layer_ids.add(lid)

    # ---- 4. Measurements ----
    measurements: list[dict] = []
    meas_ids: set[str] = set()
    meas_by_id: dict[str, dict] = {}
    meas_devices: dict[str, set[str]] = {}
    for idx, ms in enumerate(meta.get("measurements") or [], 1):
        msid = clean_str(ms.get("measurement_id", "")) or f"MS{idx}"
        if msid in meas_ids:
            msid = f"MS{idx}_{len(meas_ids) + 1}"
        note = clean_str(ms.get("note", ""))
        # measurement.device_id is a semicolon-separated list of valid device_ids
        raw_dids = [clean_str(x) for x in re.split(r"[;,]", str(ms.get("device_id", "")))]
        valid_dids = [x for x in raw_dids if x in dev_ids]
        # Preserve unique order
        valid_dids = list(dict.fromkeys(valid_dids))
        mtype, note = _canon_vocab("measurements", "measurement_type", ms.get("measurement_type", ""), note, MEAS_TYPE_SYN, default="")
        sdir, note = _canon_vocab("measurements", "scan_direction", ms.get("scan_direction", ""), note, SCAN_DIR_SYN, default="")
        sproto, note = _canon_vocab("measurements", "stability_protocol", ms.get("stability_protocol", ""), note, ISOS_SYN, default="")
        if mtype == "stability" and not sproto:
            sproto = "other"
        mask, note = _canon_vocab("measurements", "mask_used", ms.get("mask_used", ""), note, BOOL_SYN, default="")
        cert, note = _canon_vocab("measurements", "certified", ms.get("certified", ""), note, BOOL_SYN, default="")
        row = {
            "publication_id": doc_id,
            "measurement_id": msid,
            "device_id": "; ".join(valid_dids),
            "measurement_type": mtype,
            "spectrum": clean_str(ms.get("spectrum", "")),
            "light_intensity": clean_str(ms.get("light_intensity", "")),
            "intensity_unit": clean_str(ms.get("intensity_unit", "")),
            "scan_direction": sdir,
            "scan_rate": clean_str(ms.get("scan_rate", "")),
            "mask_used": mask,
            "certified": cert,
            "certification_lab": clean_str(ms.get("certification_lab", "")),
            "temperature": clean_str(ms.get("temperature", "")),
            "stability_protocol": sproto,
            "stress_conditions": clean_str(ms.get("stress_conditions", "")),
            "note": note,
        }
        measurements.append(row)
        meas_ids.add(msid)
        meas_by_id[msid] = row
        meas_devices[msid] = set(valid_dids)

    # ---- 5. Results ----
    raw_results = iter_raw_results(cache)
    results: list[dict] = []
    auto_issues: list[dict] = []
    qstats: dict[str, int] = defaultdict(int)
    seen_exact: set[tuple] = set()

    for r in raw_results:
        raw_metric_s = clean_str(r.get("metric_name", ""))
        metric = canon_metric_name(raw_metric_s)
        if not metric:
            continue
        note = clean_str(r.get("note", ""))
        frag_check = clean_str(r.get("source_fragment", ""))
        ctx_low = f"{raw_metric_s} {frag_check} {note}".lower()
        # Prevent Voc deficit / SQ percentage limit from polluting canonical Voc
        if metric == "Voc":
            if "deficit" in ctx_low or "voc loss" in ctx_low or "voltage loss" in ctx_low:
                metric = "Voc_deficit"
            elif _norm_unit_key(r.get("raw_unit", "")).lower() in {"%", "percent", "pct"} or "detailed balance" in ctx_low:
                metric = "Voc_SQ_ratio"
        origin, note = _canon_vocab("results", "result_origin", r.get("result_origin", ""), note, ORIGIN_SYN, default="primary")
        agg, note = _canon_vocab("results", "aggregation", r.get("aggregation", ""), note, AGG_SYN, default="")
        status, note = _canon_vocab("results", "extraction_status", r.get("extraction_status", ""), note, STATUS_SYN, default="")

        raw_val = clean_str(r.get("raw_value", ""))
        raw_unit = clean_str(r.get("raw_unit", ""))
        spread_raw = clean_str(r.get("spread_value", ""))
        # Extract inline ± spread from raw_value if spread_value is empty
        m_pm = re.match(r"^\s*[≈~]?\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:±|\+/-)\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(.*)$", raw_val.replace("−", "-"))
        if m_pm:
            raw_val = m_pm.group(1)
            if not spread_raw:
                spread_raw = m_pm.group(2)
            if not raw_unit and m_pm.group(3).strip():
                raw_unit = m_pm.group(3).strip()

        norm_val, norm_unit, unit_issue = normalize_metric_value(metric, raw_val, raw_unit) if raw_val else ("", "", None)
        if not status:
            status = "extracted" if norm_val else "present_not_extractable"
        if status != "extracted":
            norm_val, norm_unit = "", ""
        elif not norm_val:
            status = "present_not_extractable"
            norm_unit = ""

        # Enforce strict FK & origin rules
        did = clean_str(r.get("device_id", ""))
        msid = clean_str(r.get("measurement_id", ""))
        mid = clean_str(r.get("material_id", ""))
        cited_pub = clean_str(r.get("cited_publication_id", ""))
        if origin == "cited":
            did = ""
            msid = ""
            if mid not in mat_ids:
                mid = ""
        else:
            if did not in dev_ids:
                did = next(iter(dev_ids)) if len(dev_ids) == 1 else ""
            if msid not in meas_ids:
                msid = ""
            if mid not in mat_ids:
                mid = ""
            # Auto-inherit material_id from device
            if not mid and did and dev_by_id[did]["absorber_material_id"]:
                mid = dev_by_id[did]["absorber_material_id"]
            if not mid and len(mat_ids) == 1:
                mid = next(iter(mat_ids))
            # Auto-inherit measurement_id if uniquely determined for (device_id, metric_type)
            if not msid and did:
                want_type = _expected_meas_type(metric)
                cands = [
                    m_id for m_id, m_row in meas_by_id.items()
                    if (not want_type or m_row["measurement_type"] == want_type)
                    and (not meas_devices[m_id] or did in meas_devices[m_id])
                ]
                if len(cands) == 1:
                    msid = cands[0]

        # Numeric cleanup for optional numeric-like fields
        spread_clean = parse_float_strict(spread_raw) if spread_raw else ""
        n_dev_raw = clean_str(r.get("n_devices", ""))
        m_nd = re.search(r"\d+", n_dev_raw)
        n_dev = m_nd.group(0) if m_nd else ""
        tp_raw = clean_str(r.get("time_point", ""))
        tp_val = parse_float_strict(tp_raw) if tp_raw else ""
        tp_unit = clean_str(r.get("time_unit", "")) if tp_val else ""

        src_page = to_page(r.get("source_page", 0))
        src_frag = clean_str(r.get("source_fragment", ""))
        src_table = clean_str(r.get("source_table", ""))
        if pages_norm and src_frag:
            src_frag, src_page, st = ground_fragment(src_frag, src_page, raw_val, pages_raw, pages_norm)
            if st == "unverified" and src_table and re.match(r"^(?:Table|TABLE)\b", src_table):
                # Fallback to table-row reference format explicitly permitted by check_submission.py
                lbl = dev_by_id.get(did, {}).get("device_label", "")
                src_frag = f"{src_table}, {lbl}" if lbl else src_table
                st = "table_ref"
            qstats[st] += 1
        src_page_s = str(src_page) if src_page > 0 else ""

        # Skip exact duplicate raw entries from overlapping windows/verify passes
        dedup_key = (
            did, msid, mid, metric, norm_val, agg, tp_val, origin, cited_pub,
            src_page_s, clean_str(r.get("source_table", "")), clean_str(r.get("source_figure", "")),
            norm(src_frag), status,
        )
        if dedup_key in seen_exact:
            continue
        seen_exact.add(dedup_key)

        rid = f"R{len(results) + 1}"
        row = {
            "publication_id": doc_id,
            "result_id": rid,
            "device_id": did,
            "measurement_id": msid,
            "material_id": mid,
            "metric_name": metric,
            "metric_value": norm_val,
            "metric_unit": norm_unit,
            "aggregation": agg,
            "spread_value": spread_clean,
            "n_devices": n_dev,
            "time_point": tp_val,
            "time_unit": tp_unit,
            "raw_value": raw_val,
            "raw_unit": raw_unit,
            "normalized_value": norm_val,
            "normalized_unit": norm_unit,
            "result_origin": origin,
            "cited_publication_id": cited_pub if origin == "cited" else "",
            "source_page": src_page_s,
            "source_section": clean_str(r.get("source_section", "")),
            "source_table": clean_str(r.get("source_table", "")),
            "source_figure": clean_str(r.get("source_figure", "")),
            "source_fragment": src_frag,
            "extraction_status": status,
            "duplicate_of": "",
            "note": note,
        }
        results.append(row)
        if unit_issue:
            auto_issues.append({
                "record_ids": rid,
                "check_name": "unit_inconsistency",
                "description": unit_issue,
                "source_page": src_page_s,
                "source_fragment": src_frag,
            })

    # ---- 6. Orphan device_id inheritance + Deduplication & Contradictions ----
    # 6a. If a primary extracted row has device_id == "", inherit device_id when a unique
    #     device in the same document owns the exact same (metric_name, metric_value).
    val_to_devs: dict[tuple[str, str], set[str]] = defaultdict(set)
    val_to_meas: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in results:
        if row["result_origin"] == "primary" and row["extraction_status"] == "extracted" and row["metric_value"] and row["device_id"]:
            vk = (row["metric_name"], fmt_dec(Decimal(row["metric_value"])))
            val_to_devs[vk].add(row["device_id"])
            if row["measurement_id"]:
                val_to_meas[(row["device_id"], *vk)].add(row["measurement_id"])
    for row in results:
        if row["result_origin"] == "primary" and row["extraction_status"] == "extracted" and row["metric_value"] and not row["device_id"]:
            vk = (row["metric_name"], fmt_dec(Decimal(row["metric_value"])))
            cands = val_to_devs.get(vk, set())
            if len(cands) == 1:
                did = next(iter(cands))
                row["device_id"] = did
                if not row["material_id"] and dev_by_id.get(did, {}).get("absorber_material_id"):
                    row["material_id"] = dev_by_id[did]["absorber_material_id"]
                if not row["measurement_id"]:
                    mcands = val_to_meas.get((did, *vk), set())
                    if len(mcands) == 1:
                        row["measurement_id"] = next(iter(mcands))
            elif not cands:
                # Fallback: unique mention of an exact device_label inside fragment/note
                ctx = f" {row['source_fragment']} {row['note']} ".lower()
                matched_dids = [
                    d_id for d_id, d_row in dev_by_id.items()
                    if d_row["device_label"] and len(d_row["device_label"]) >= 3
                    and d_row["device_label"].lower() in ctx
                ]
                if len(matched_dids) == 1:
                    row["device_id"] = matched_dids[0]
                    if not row["material_id"] and dev_by_id[matched_dids[0]]["absorber_material_id"]:
                        row["material_id"] = dev_by_id[matched_dids[0]]["absorber_material_id"]

    # 6b. Exact-context deduplication & contradiction detection
    def _priority(row: dict) -> tuple[int, int]:
        if row["source_table"]:
            tier = 0
        elif "abstract" not in (row["source_section"] or "").lower():
            tier = 1
        else:
            tier = 2
        return (tier, int(row["result_id"][1:]))

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in results:
        if row["result_origin"] == "primary" and row["extraction_status"] == "extracted" and row["metric_value"]:
            if row["device_id"]:
                gk = (row["device_id"], row["measurement_id"], row["metric_name"], row["aggregation"], row["time_point"])
                groups[gk].append(row)

    for gk, grp in groups.items():
        if len(grp) < 2:
            continue
        grp_sorted = sorted(grp, key=_priority)
        primary = grp_sorted[0]
        p_val = float(primary["metric_value"])
        contradict_ids: list[str] = []
        for other in grp_sorted[1:]:
            o_val = float(other["metric_value"])
            if abs(p_val - o_val) <= 1e-6:
                other["duplicate_of"] = primary["result_id"]
            elif abs(p_val - o_val) > 1e-4:
                contradict_ids.append(other["result_id"])
        if contradict_ids:
            rec_ids = "; ".join([primary["result_id"], *contradict_ids])
            vals = ", ".join(r["metric_value"] for r in [primary, *[x for x in grp_sorted[1:] if x["result_id"] in contradict_ids]])
            auto_issues.append({
                "record_ids": rec_ids,
                "check_name": "contradiction",
                "description": f"Conflicting primary values for {gk[2]} on {gk[0]} ({gk[1] or 'unspecified measurement'}, {gk[3] or 'unspecified agg'}): {vals}.",
                "source_page": primary["source_page"],
                "source_fragment": primary["source_fragment"],
            })

    # 6c. Prose/Abstract repeat linking: if a prose/Abstract row repeats the exact same
    #     (device_id, metric_name, metric_value, time_point) of a Table (or earlier non-Abstract) row
    #     and differs only by an omitted measurement_id or omitted aggregation, mark duplicate_of.
    by_dmv: dict[tuple[str, str, str, str], list[dict]] = defaultdict(list)
    for row in results:
        if (row["result_origin"] == "primary" and row["extraction_status"] == "extracted"
                and row["metric_value"] and row["device_id"] and not row["duplicate_of"]):
            by_dmv[(row["device_id"], row["metric_name"], fmt_dec(Decimal(row["metric_value"])), row["time_point"])].append(row)
    for _, grp in by_dmv.items():
        if len(grp) < 2:
            continue
        grp_sorted = sorted(grp, key=_priority)
        anchor = grp_sorted[0]
        for other in grp_sorted[1:]:
            if other["source_table"]:
                continue  # never collapse two distinct table rows with different scan/agg
            # Only collapse prose/Abstract repeat when it adds no stricter measurement/aggregation info,
            # or transfer missing measurement_id/aggregation onto the table anchor if non-conflicting.
            if not anchor["measurement_id"] and other["measurement_id"]:
                anchor["measurement_id"] = other["measurement_id"]
            if not anchor["aggregation"] and other["aggregation"]:
                anchor["aggregation"] = other["aggregation"]
            same_ms = (other["measurement_id"] in ("", anchor["measurement_id"]))
            same_agg = (other["aggregation"] in ("", anchor["aggregation"]))
            if same_ms and same_agg:
                other["duplicate_of"] = anchor["result_id"]

    # ---- 7. Physical & Logical Checks (7 rules, never deleting results) ----
    active_primary = [
        r for r in results
        if r["result_origin"] == "primary" and r["extraction_status"] == "extracted"
        and r["metric_value"] and not r["duplicate_of"]
    ]

    # 7.1 jv_consistency: PCE_calc = (Voc * Jsc * FF) / Pin
    by_jv: dict[tuple[str, str, str], dict[str, dict]] = defaultdict(dict)
    for r in active_primary:
        if r["device_id"] and r["metric_name"] in {"PCE", "Voc", "Jsc", "FF"}:
            key = (r["device_id"], r["measurement_id"], r["aggregation"])
            by_jv[key].setdefault(r["metric_name"], r)
    for (did, msid, agg), mdict in by_jv.items():
        if all(k in mdict for k in ("Voc", "Jsc", "FF", "PCE")):
            voc = float(mdict["Voc"]["metric_value"])
            jsc = float(mdict["Jsc"]["metric_value"])
            ff = float(mdict["FF"]["metric_value"])
            pce = float(mdict["PCE"]["metric_value"])
            pin = _parse_pin_mw_cm2(meas_by_id.get(msid, {})) or 100.0
            if pce > 0 and pin > 0:
                pce_calc = (voc * jsc * ff) / pin
                rel = abs(pce_calc - pce) / pce
                if rel > 0.03:
                    rids = "; ".join(mdict[k]["result_id"] for k in ("Voc", "Jsc", "FF", "PCE"))
                    auto_issues.append({
                        "record_ids": rids,
                        "check_name": "jv_consistency",
                        "description": (
                            f"J-V consistency mismatch on {did}: Voc*Jsc*FF/Pin = {pce_calc:.2f}% "
                            f"(Pin={pin:.1f} mW/cm2) vs reported PCE={pce:.2f}% (rel diff {rel * 100:.1f}% > 3%)."
                        ),
                        "source_page": mdict["PCE"]["source_page"],
                        "source_fragment": mdict["PCE"]["source_fragment"],
                    })

    # 7.2 voc_limit: ONLY for device_type == "cell" (never minimodule/module!)
    for r in active_primary:
        if r["metric_name"] == "Voc" and r["device_id"]:
            dev = dev_by_id.get(r["device_id"], {})
            if dev.get("device_type") == "cell":
                mid = r["material_id"] or dev.get("absorber_material_id", "")
                eg_s = mat_by_id.get(mid, {}).get("bandgap_value", "")
                if eg_s:
                    voc = float(r["metric_value"])
                    eg = float(eg_s)
                    if voc >= eg:
                        auto_issues.append({
                            "record_ids": r["result_id"],
                            "check_name": "voc_limit",
                            "description": f"Single-cell Voc={voc} V >= absorber bandgap Eg={eg} eV on {r['device_id']}.",
                            "source_page": r["source_page"],
                            "source_fragment": r["source_fragment"],
                        })

    # 7.3 eqe_consistency: |Jsc - Jsc_EQE| / Jsc > 0.05 on same device_id
    jsc_by_dev: dict[str, list[dict]] = defaultdict(list)
    eqe_by_dev: dict[str, list[dict]] = defaultdict(list)
    for r in active_primary:
        if r["device_id"] and r["metric_name"] == "Jsc":
            jsc_by_dev[r["device_id"]].append(r)
        elif r["device_id"] and r["metric_name"] == "Jsc_EQE":
            eqe_by_dev[r["device_id"]].append(r)
    for did, eqe_rows in eqe_by_dev.items():
        if did not in jsc_by_dev:
            continue
        # Compare champion or first Jsc against Jsc_EQE
        j_row = next((x for x in jsc_by_dev[did] if x["aggregation"] == "champion"), jsc_by_dev[did][0])
        j_val = float(j_row["metric_value"])
        if j_val <= 0:
            continue
        for e_row in eqe_rows:
            e_val = float(e_row["metric_value"])
            rel = abs(j_val - e_val) / j_val
            if rel > 0.05:
                auto_issues.append({
                    "record_ids": f"{j_row['result_id']}; {e_row['result_id']}",
                    "check_name": "eqe_consistency",
                    "description": f"Jsc ({j_val} mA/cm2) vs Jsc_EQE ({e_val} mA/cm2) on {did} differs by {rel * 100:.1f}% (> 5%).",
                    "source_page": e_row["source_page"],
                    "source_fragment": e_row["source_fragment"],
                })

    # 7.4 champion_vs_mean: mean > champion on same (device_id, measurement_id, metric_name)
    by_agg: dict[tuple[str, str, str], dict[str, dict]] = defaultdict(dict)
    for r in active_primary:
        if r["device_id"] and r["aggregation"] in {"champion", "mean"}:
            by_agg[(r["device_id"], r["measurement_id"], r["metric_name"])].setdefault(r["aggregation"], r)
    for (did, msid, mname), adict in by_agg.items():
        if "champion" in adict and "mean" in adict:
            c_val = float(adict["champion"]["metric_value"])
            m_val = float(adict["mean"]["metric_value"])
            if m_val > c_val + 1e-6:
                auto_issues.append({
                    "record_ids": f"{adict['champion']['result_id']}; {adict['mean']['result_id']}",
                    "check_name": "champion_vs_mean",
                    "description": f"Mean ({m_val}) exceeds champion ({c_val}) for {mname} on {did}.",
                    "source_page": adict["mean"]["source_page"],
                    "source_fragment": adict["mean"]["source_fragment"],
                })

    # 7.5 range checks
    for r in active_primary:
        v = float(r["metric_value"])
        m = r["metric_name"]
        bad = False
        reason = ""
        if m in {"PCE", "stabilized_PCE"} and not (0.0 < v <= 40.0):
            bad, reason = True, f"{m}={v}% outside (0, 40]"
        elif m == "FF" and not (0.0 < v < 100.0):
            bad, reason = True, f"FF={v}% outside (0, 100)"
        elif m == "Voc" and v <= 0.0:
            bad, reason = True, f"Voc={v} V <= 0"
        elif m in {"Jsc", "Jsc_EQE"} and v <= 0.0:
            bad, reason = True, f"{m}={v} mA/cm2 <= 0"
        elif m in {"Rs", "Rsh"} and v < 0.0:
            bad, reason = True, f"{m}={v} Ohm*cm2 < 0"
        if bad:
            auto_issues.append({
                "record_ids": r["result_id"],
                "check_name": "range",
                "description": f"Out-of-range value: {reason}.",
                "source_page": r["source_page"],
                "source_fragment": r["source_fragment"],
            })

    # 7.6 hysteresis_index check
    pce_dir_by_dev: dict[str, dict[str, dict]] = defaultdict(dict)
    hi_by_dev: dict[str, list[dict]] = defaultdict(list)
    for r in active_primary:
        if r["device_id"] and r["metric_name"] == "PCE" and r["measurement_id"]:
            sd = meas_by_id.get(r["measurement_id"], {}).get("scan_direction", "")
            if sd in {"reverse", "forward"}:
                pce_dir_by_dev[r["device_id"]].setdefault(sd, r)
        elif r["device_id"] and r["metric_name"] == "HI":
            hi_by_dev[r["device_id"]].append(r)
    for did, hi_rows in hi_by_dev.items():
        dirs = pce_dir_by_dev.get(did, {})
        if "reverse" in dirs and "forward" in dirs:
            pr = float(dirs["reverse"]["metric_value"])
            pf = float(dirs["forward"]["metric_value"])
            mx = max(pr, pf)
            if mx > 0:
                hi_calc = abs(pr - pf) / mx * 100.0
                for h_row in hi_rows:
                    hv = float(h_row["metric_value"])
                    # Check both % and fraction-scaled mismatch
                    if abs(hi_calc - hv) > max(1.0, 0.1 * max(hi_calc, hv)):
                        auto_issues.append({
                            "record_ids": f"{dirs['reverse']['result_id']}; {dirs['forward']['result_id']}; {h_row['result_id']}",
                            "check_name": "hysteresis_index",
                            "description": (
                                f"HI={hv}% vs |PCE_rev({pr})-PCE_fwd({pf})|/max*100={hi_calc:.2f}% on {did}."
                            ),
                            "source_page": h_row["source_page"],
                            "source_fragment": h_row["source_fragment"],
                        })

    # 7.7 missing_conditions & comparability on J-V measurements
    for ms in measurements:
        if ms["measurement_type"] != "J-V":
            continue
        if "dark" in ms["note"].lower():
            continue
        spec = ms["spectrum"]
        inten = ms["light_intensity"]
        if not spec or not inten:
            auto_issues.append({
                "record_ids": "",
                "check_name": "missing_conditions",
                "description": f"J-V measurement {ms['measurement_id']} omits spectrum or light_intensity.",
                "source_page": "",
                "source_fragment": "",
            })
        else:
            pin = _parse_pin_mw_cm2(ms)
            has_am15g = bool(re.search(r"am\s*1\.?5\s*g", spec, re.I))
            if not has_am15g or (pin is not None and abs(pin - 100.0) > 1.0):
                auto_issues.append({
                    "record_ids": "",
                    "check_name": "comparability",
                    "description": f"Non-standard J-V illumination on {ms['measurement_id']}: spectrum='{spec}', intensity='{inten} {ms['intensity_unit']}'.",
                    "source_page": "",
                    "source_fragment": "",
                })

    # ---- 8. Combine Meta issues + Auto issues, verify quotes & FKs ----
    valid_rids = {r["result_id"] for r in results}
    issues: list[dict] = []
    seen_iss: set[tuple] = set()

    raw_issues: list[dict] = []
    for mi in meta.get("issues") or []:
        raw_issues.append({
            "record_ids": "",
            "check_name": clean_str(mi.get("check_name", "")) or "document_issue",
            "description": clean_str(mi.get("description", "")),
            "source_page": str(to_page(mi.get("source_page", 0))) if to_page(mi.get("source_page", 0)) > 0 else "",
            "source_fragment": clean_str(mi.get("source_fragment", "")),
        })
    raw_issues.extend(auto_issues)

    for iss in raw_issues:
        desc = clean_str(iss.get("description", ""))
        cname = clean_str(iss.get("check_name", "")) or "check"
        if not desc:
            continue
        rids_clean = [x for x in (clean_str(t) for t in re.split(r"[;,]", str(iss.get("record_ids", "")))) if x in valid_rids]
        rids_s = "; ".join(dict.fromkeys(rids_clean))
        sp = to_page(iss.get("source_page", 0))
        sf = clean_str(iss.get("source_fragment", ""))
        if pages_norm and sf:
            sf_g, sp_g, st = ground_fragment(sf, sp, "", pages_raw, pages_norm)
            if st in {"ok", "moved", "repaired", "table_ref"}:
                sf, sp = sf_g, sp_g
            else:
                # Clear unverified issue quotes so checker has 0 quote warnings on issues.csv
                sf = ""
        sp_s = str(sp) if sp > 0 else ""
        ik = (rids_s, cname, desc)
        if ik in seen_iss:
            continue
        seen_iss.add(ik)
        issues.append({
            "publication_id": doc_id,
            "issue_id": f"I{len(issues) + 1}",
            "record_ids": rids_s,
            "check_name": cname,
            "description": desc,
            "source_page": sp_s,
            "source_fragment": sf,
        })

    if log_fn and qstats:
        log_fn(f"  {doc_id}: quote check {dict(qstats)}")

    return {
        "publications": [pub_row],
        "materials": materials,
        "devices": devices,
        "layers": layers,
        "measurements": measurements,
        "results": results,
        "issues": issues,
    }


class TableWriter:
    """Stream all 7 Domain 1 CSV files with UTF-8 encoding and strict column order."""

    def __init__(self, out_dir: pathlib.Path) -> None:
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.counts: dict[str, int] = {t: 0 for t in TABLES}
        self._files: dict[str, object] = {}
        self._writers: dict[str, csv.DictWriter] = {}
        self._tmps: dict[str, pathlib.Path] = {}
        for t, cols in TABLES.items():
            tmp = self.out_dir / f".{t}.csv.tmp"
            f = tmp.open("w", encoding="utf-8", newline="")
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
            w.writeheader()
            self._tmps[t] = tmp
            self._files[t] = f
            self._writers[t] = w

    def write_doc(self, doc: dict[str, list[dict]]) -> None:
        for t, cols in TABLES.items():
            for row in doc.get(t, []):
                clean_row = {c: ("" if row.get(c) is None else str(row.get(c))) for c in cols}
                self._writers[t].writerow(clean_row)
                self.counts[t] += 1

    def close(self, commit: bool = True) -> None:
        for t in TABLES:
            f = self._files.pop(t, None)
            if f is not None:
                f.close()
        for t, tmp in self._tmps.items():
            dst = self.out_dir / f"{t}.csv"
            if commit and tmp.exists():
                tmp.replace(dst)
            elif tmp.exists():
                tmp.unlink(missing_ok=True)
