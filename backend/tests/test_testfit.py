"""Phase 2 Gate C — the test-fit produces a VALID, sane workstation field.

Validity is the whole point of a constraint-based engine, so we assert it geometrically:
every placed desk is inside the usable boundary, off the walls, clear of the core and
columns, and no two desks overlap. Plus a sane density.
"""

from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon, box

from app.floorplan.dxf_ingest import ingest_dxf
from app.testfit.layout import WorkstationSpec, place_workstations

DXF = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"
pytestmark = pytest.mark.skipif(not DXF.exists(), reason="sample DXF not generated")


def test_places_workstations():
    plan = ingest_dxf(str(DXF))
    fit = place_workstations(plan, WorkstationSpec())
    assert fit.workstation_count > 10            # a real field, not a token few
    assert len(fit.instances) == fit.workstation_count
    # Density sanity: a 6x5 desk + 3ft aisle is ~48-90 sf/seat including circulation.
    assert 40 <= fit.sf_per_workstation <= 150


def test_every_desk_is_geometrically_valid():
    plan = ingest_dxf(str(DXF))
    spec = WorkstationSpec()
    fit = place_workstations(plan, spec)

    boundary = Polygon(plan.boundary).buffer(-spec.perimeter_setback_ft)
    cores = [Polygon(c) for c in plan.cores]
    columns = [Point(c).buffer(spec.column_clearance_ft) for c in plan.columns]

    rects = [box(i.x, i.y, i.x + i.w, i.y + i.h) for i in fit.instances]
    for r in rects:
        assert boundary.contains(r)                          # inside usable boundary
        assert all(not r.intersects(c) for c in cores)       # clear of core
        assert all(not r.intersects(col) for col in columns)  # clear of columns

    # No two desks overlap (area-wise).
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert rects[i].intersection(rects[j]).area < 1e-6
