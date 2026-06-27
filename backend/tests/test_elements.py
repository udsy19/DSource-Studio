"""Element extraction: component counts reconcile with the test-fit and the wall geometry."""

from __future__ import annotations

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.elements import extract_elements
from app.testfit.layout import generate_mixed_layout


def _plan() -> PlanModel:
    return PlanModel(
        units="ft", sqft_factor=1.0,
        boundary=[(0, 0), (120, 0), (120, 90), (0, 90)],
        gross_area_sf=10800, core_area_sf=0, usable_area_sf=10000, columns=[], cores=[],
    )


def test_furniture_counts_reconcile_with_testfit():
    plan = _plan()
    fit = generate_mixed_layout(plan)
    el = extract_elements(plan, fit)

    assert el["furniture"]["desks"] == fit.workstation_count + fit.office_count
    assert el["furniture"]["tables"] == fit.meeting_count
    assert el["furniture"]["chairs"] >= el["furniture"]["desks"]  # meetings add seats
    assert el["spaces"]["workstations"] == fit.workstation_count
    assert el["spaces"]["huddle_spaces"] == fit.collab_count


def test_walls_are_perimeter_plus_room_partitions():
    plan = _plan()
    fit = generate_mixed_layout(plan)
    el = extract_elements(plan, fit)

    enclosed = fit.office_count + fit.meeting_count + fit.collab_count
    assert el["construction"]["perimeter_walls"] == len(plan.boundary)
    assert el["construction"]["room_partitions"] == 4 * enclosed
    assert el["construction"]["walls"] == len(plan.boundary) + 4 * enclosed
