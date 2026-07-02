"""Scored-generation integration — the variant ranking is real, not decorative.

Asserts every alternative carries score/recommended/breakdown, the recommended variant holds the
batch-max score, an over-asked program shows its shortfall in the recommended variant's
program_match, and — the anti-decoration guard — that an open-heavy and an enclosed-heavy program
recommend DIFFERENT variants (if intent never moved the pick, the weights would be a fixed opinion
dressed as analysis).
"""

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.concept import ConceptProgram, generate_from_concept
from app.testfit.detailed import DetailedProgram, RoomRequest, generate_from_detailed


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


def _recommended(result: dict) -> dict:
    return next(a for a in result["alternatives"] if a["recommended"])


def test_alternatives_carry_score_and_single_recommended():
    result = generate_from_detailed(
        _plan(), DetailedProgram(rooms=[RoomRequest(type="office", count=4, placement="window")])
    )
    alts = result["alternatives"]
    for a in alts:
        assert 0.0 <= a["score"] <= 1.0
        assert set(a["score_breakdown"]) == {"program_match", "seat_yield", "daylight", "efficiency"}
        assert "program_match" not in a  # folded into the breakdown
    recs = [a for a in alts if a["recommended"]]
    assert len(recs) == 1
    assert recs[0]["score"] == max(a["score"] for a in alts)


def test_overshoot_shows_shortfall_in_recommended_match():
    result = generate_from_detailed(
        _plan(), DetailedProgram(rooms=[RoomRequest(type="meeting", count=40, placement="window")])
    )
    assert _recommended(result)["score_breakdown"]["program_match"] < 1.0


def test_open_and_enclosed_programs_recommend_differently():
    """Intent must move the pick. Open-plan and enclosed-heavy concepts scored on the same plate
    must not both land on the same variant."""
    plan = _plan()
    open_plan = generate_from_concept(plan, ConceptProgram(planning_style="modern", closed_ratio=0.05))
    enclosed = generate_from_concept(plan, ConceptProgram(planning_style="traditional", closed_ratio=0.4))
    assert _recommended(open_plan)["id"] != _recommended(enclosed)["id"]


def test_scored_generation_is_deterministic():
    program = DetailedProgram(rooms=[RoomRequest(type="office", count=3, placement="window")])
    assert generate_from_detailed(_plan(), program) == generate_from_detailed(_plan(), program)
