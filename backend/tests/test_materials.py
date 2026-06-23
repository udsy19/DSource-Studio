"""Material derivation tests — fast, deterministic (no network, no model, no DB)."""

from app.materials.derive import AXES, derive_material_attributes

VALID_BASES = {"measured_standard", "derived_proxy", "estimated"}


def test_known_family_returns_six_valid_axes():
    attrs = derive_material_attributes("velvet")
    assert set(attrs) == set(AXES)
    for axis in AXES:
        a = attrs[axis]
        assert a["basis"] in VALID_BASES
        assert isinstance(a["score"], int) and 0 <= a["score"] <= 5


def test_family_normalization_is_case_and_separator_insensitive():
    assert derive_material_attributes("Leather Full Grain") == derive_material_attributes(
        "leather_full_grain"
    )


def test_unknown_family_is_estimated_with_no_fabricated_number():
    attrs = derive_material_attributes("unobtanium_weave")
    for axis in AXES:
        a = attrs[axis]
        assert a["basis"] == "estimated"
        # Honest-data rule: never a precise standard value for an unknown material.
        assert not any(ch.isdigit() for ch in a["standard_ref"])


def test_override_with_measured_value_flips_axis_to_measured_standard():
    attrs = derive_material_attributes(
        "polyester_fabric", sku_overrides={"abrasion_wear": {"martindale": 40000}}
    )
    abrasion = attrs["abrasion_wear"]
    assert abrasion["basis"] == "measured_standard"
    assert "40000" in abrasion["standard_ref"]
    assert "Martindale" in abrasion["standard_ref"]
    # Untouched axes keep their class proxy.
    assert attrs["cleanability"]["basis"] != "measured_standard"


def test_override_without_recognized_lab_field_does_not_promote():
    attrs = derive_material_attributes(
        "velvet", sku_overrides={"abrasion_wear": {"vibes": "tough"}}
    )
    assert attrs["abrasion_wear"]["basis"] != "measured_standard"


def test_dust_static_affinity_velvet_high_glass_low():
    assert derive_material_attributes("velvet")["dust_static_affinity"]["score"] >= 4
    assert derive_material_attributes("glass")["dust_static_affinity"]["score"] <= 1
