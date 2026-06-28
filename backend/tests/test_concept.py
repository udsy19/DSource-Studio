"""Concept-mode tests — pure geometry, no DB/catalog/network.

Builds a PlanModel directly from a rectangular boundary (mirrors test_alternatives.py) so nothing
here touches ingest_cad, the catalog, or embeddings. Asserts the core Concept behaviours: 3 scored
variants, traditional > modern in offices, larger desks -> fewer workstations, and determinism.
"""

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.concept import ConceptProgram, generate_from_concept

_METRIC_KEYS = {
    "usf", "seats", "open_space_seats", "offices", "conf_rooms",
    "density_sf_per_person", "daylight_pct", "privacy_pct", "efficiency_pct",
}


def _plan() -> PlanModel:
    """A plain 140 x 90 ft rectangular plate (12,600 sf), no core/columns."""
    w, h = 140.0, 90.0
    boundary = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    area = w * h
    return PlanModel(
        units="feet", sqft_factor=1.0, boundary=boundary,
        gross_area_sf=area, core_area_sf=0.0, usable_area_sf=area,
        columns=[], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )


def _total_offices(result: dict) -> int:
    return sum(a["metrics"]["offices"] for a in result["alternatives"])


def _total_workstations(result: dict) -> int:
    return sum(a["metrics"]["open_space_seats"] for a in result["alternatives"])


def test_generate_from_concept_returns_three_scored_variants():
    result = generate_from_concept(_plan(), ConceptProgram())

    assert [a["id"] for a in result["alternatives"]] == ["A", "B", "C"]
    for alt in result["alternatives"]:
        assert set(alt["metrics"]) == _METRIC_KEYS
        assert "instances" in alt["testfit"]
    metrics = [tuple(sorted(a["metrics"].items())) for a in result["alternatives"]]
    assert len(set(metrics)) == 3, "the three variants must differ in their metrics"


def test_traditional_yields_more_offices_than_modern():
    plan = _plan()
    traditional = generate_from_concept(
        plan, ConceptProgram(planning_style="traditional", closed_ratio=0.4)
    )
    modern = generate_from_concept(
        plan, ConceptProgram(planning_style="modern", closed_ratio=0.4)
    )
    assert _total_offices(traditional) > _total_offices(modern)


def test_larger_desks_yield_fewer_workstations():
    plan = _plan()
    small = generate_from_concept(plan, ConceptProgram(desk_width_cm=120))
    large = generate_from_concept(plan, ConceptProgram(desk_width_cm=200))
    assert _total_workstations(large) < _total_workstations(small)


def test_generate_from_concept_is_deterministic():
    concept = ConceptProgram(planning_style="cowork", desk_type="benchings", closed_ratio=0.3)
    assert generate_from_concept(_plan(), concept) == generate_from_concept(_plan(), concept)
