"""Pure material-attribute derivation: family (+ finish, + per-SKU overrides) -> 6 axes."""

from __future__ import annotations

import json
import re
from pathlib import Path

AXES = (
    "abrasion_wear",
    "dent_hardness",
    "cleanability",
    "dust_static_affinity",
    "moisture_humidity_behavior",
    "indoor_air_voc",
)

_TABLE: dict[str, dict] = json.loads(
    (Path(__file__).parent / "material_table.json").read_text()
)

# A real measured field in an override -> the standard it cites, by axis. Anything not
# listed here is not a recognized lab measurement and won't promote an axis to measured.
_OVERRIDE_STANDARDS = {
    "abrasion_wear": {
        "martindale": "ISO 12947 Martindale",
        "wyzenbeek": "ASTM D4157 Wyzenbeek",
        "pei": "ISO 10545-7 PEI",
        "ac_rating": "EN 13329 AC rating",
        "janka": "Janka ASTM D1037",
        "taber": "ASTM D4060 Taber",
    },
    "dent_hardness": {
        "janka": "Janka ASTM D1037",
        "shore": "ISO 868 / ASTM D2240 Shore hardness",
    },
    "indoor_air_voc": {
        "greenguard": "GREENGUARD UL 2818",
        "formaldehyde_class": "Formaldehyde class E1/E0 / CARB Phase 2",
        "tvoc": "GREENGUARD UL 2818 (TVOC)",
    },
}


def _normalize(material_family: str) -> str:
    return re.sub(r"[\s\-]+", "_", material_family.strip().lower())


def _estimated_axis(axis: str, family: str) -> dict:
    return {
        "score": 2,
        "basis": "estimated",
        "standard_ref": "estimated from material class; no standard available",
        "rationale": f"Unknown material family '{family}'; score is a conservative class estimate, "
        "not grounded in a measured standard.",
    }


def _apply_override(axis: str, base: dict, override: dict) -> dict:
    """Promote an axis to measured_standard only when the override carries a recognized lab value."""
    standards = _OVERRIDE_STANDARDS.get(axis, {})
    measured = {k: v for k, v in override.items() if k in standards}
    if not measured:
        return base

    field, value = next(iter(measured.items()))
    return {
        **base,
        "basis": "measured_standard",
        "standard_ref": f"{standards[field]} = {value}",
        "rationale": f"Per-SKU measured {field}={value}; supersedes the class proxy.",
    }


def derive_material_attributes(
    material_family: str,
    finish: str | None = None,
    sku_overrides: dict | None = None,
) -> dict:
    family = _normalize(material_family)
    base_row = _TABLE.get(family)
    overrides = sku_overrides or {}

    result: dict[str, dict] = {}
    for axis in AXES:
        if base_row is None:
            axis_value = _estimated_axis(axis, material_family)
        else:
            axis_value = dict(base_row[axis])
        if axis in overrides:
            axis_value = _apply_override(axis, axis_value, overrides[axis])
        result[axis] = axis_value

    return result
