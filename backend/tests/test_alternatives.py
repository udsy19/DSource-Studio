"""Space-metrics + alternatives tests — pure geometry, no DB/catalog/network/torch.

Builds a PlanModel directly from a rectangular boundary (the floorplan layer is geometry-only),
so nothing here touches ingest_cad, the catalog, or embeddings.
"""

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.alternatives import generate_alternatives
from app.testfit.layout import ProgramSpec, WorkstationSpec, generate_mixed_layout
from app.testfit.metrics import compute_metrics

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


def test_compute_metrics_keys_and_ranges():
    plan = _plan()
    fit = generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())
    m = compute_metrics(plan, fit)

    assert set(m) == _METRIC_KEYS
    assert m["seats"] == fit.workstation_count + fit.office_count
    assert m["seats"] >= 0
    assert m["open_space_seats"] == fit.workstation_count
    assert m["offices"] == fit.office_count
    assert m["conf_rooms"] == fit.meeting_count
    assert m["density_sf_per_person"] >= 0
    assert 0.0 <= m["daylight_pct"] <= 1.0
    assert 0.0 <= m["privacy_pct"] <= 1.0
    assert 0.0 <= m["efficiency_pct"] <= 1.0
    assert m["usf"] == plan.usable_area_sf


def test_metrics_zero_when_no_seats():
    """A degenerate plate too small for any furniture -> safe zeros, no divide-by-zero."""
    tiny = PlanModel(
        units="feet", sqft_factor=1.0,
        boundary=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (0.0, 0.0)],
        gross_area_sf=16.0, core_area_sf=0.0, usable_area_sf=16.0,
        columns=[], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )
    fit = generate_mixed_layout(tiny, WorkstationSpec(), ProgramSpec())
    m = compute_metrics(tiny, fit)
    assert m["seats"] == 0
    assert m["density_sf_per_person"] == 0.0
    assert m["daylight_pct"] == 0.0
    assert m["privacy_pct"] == 0.0


def test_generate_alternatives_returns_three_distinct():
    result = generate_alternatives(_plan())

    assert [a["id"] for a in result["alternatives"]] == ["A", "B", "C"]
    assert result["plan"]["usable_area_sf"] == 12600.0
    for alt in result["alternatives"]:
        assert set(alt["metrics"]) == _METRIC_KEYS
        assert "instances" in alt["testfit"]

    metrics = [tuple(sorted(a["metrics"].items())) for a in result["alternatives"]]
    assert len(set(metrics)) == 3, "the three alternatives must differ in their metrics"


def test_generate_alternatives_is_deterministic():
    a = generate_alternatives(_plan())
    b = generate_alternatives(_plan())
    assert a == b
