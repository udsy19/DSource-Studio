"""Phase 1 Gate B — the DXF ingester recovers the known floor-plate geometry.

Runs against the generated sample_office.dxf fixture (real DXF format). Asserts the
extraction math: it must pick the L-shaped exterior boundary (8,400 sf) among several
closed polylines, subtract the 600 sf core, and find all 8 structural columns.
"""

from pathlib import Path

import pytest

from app.floorplan.capacity import Program, estimate_capacity
from app.floorplan.dxf_ingest import ingest_dxf

DXF = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"
pytestmark = pytest.mark.skipif(not DXF.exists(), reason="sample DXF not generated")


def test_recovers_known_geometry():
    plan = ingest_dxf(str(DXF))
    assert plan.units == "feet"
    assert plan.boundary_source == "polyline"
    # Known ground truth from the fixture (L-shape 9600 - 50x30 notch = 8100 gross,
    # 600 sf core, 7500 usable, 8 columns).
    assert plan.gross_area_sf == pytest.approx(8100.0, rel=0.01)
    assert plan.core_area_sf == pytest.approx(600.0, rel=0.01)
    assert plan.usable_area_sf == pytest.approx(7500.0, rel=0.01)
    assert len(plan.columns) == 8
    assert plan.needs_confirmation is True


def test_capacity_envelope_is_sane():
    plan = ingest_dxf(str(DXF))
    cap = estimate_capacity(plan.usable_area_sf, Program(density_rsf_per_person=175.0))
    # 7500 / 175 ~= 42 people
    assert cap.estimated_headcount == 42
    ws = next(z for z in cap.zones if z.zone == "workstations")
    assert ws.seats and ws.seats > 0
    assert cap.net_usable_sf < plan.usable_area_sf  # circulation removed
