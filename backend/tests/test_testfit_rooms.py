"""Phase 2 Gate C (enriched) — the MIXED test-fit produces a VALID, sane mixed layout + BOM.

We assert geometrically what a constraint-based engine must guarantee:
  * enclosed rooms ARE placed (offices + meeting rooms) on the sample plate,
  * EVERY instance (workstations + rooms + collaboration) is inside the usable boundary and
    clear of the core + columns,
  * ALL instances are mutually non-overlapping (every pair, area intersection < 1e-6),
  * the per-type BOM has multiple SKU types and prices out to a budgetary total.
"""

from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon, box
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.floorplan.dxf_ingest import ingest_dxf
from app.ingest import service
from app.ingest.sif import parse_sif
from app.routers.testfit import _build_bom_and_quote
from app.seed import seed
from app.testfit.bom import sku_demand
from app.testfit.layout import ProgramSpec, WorkstationSpec, generate_mixed_layout
from app.testfit.settings import SLOTTABLE_TYPES

ROOT = Path(__file__).resolve().parent.parent
DXF = ROOT / "data" / "floorplans" / "sample_office.dxf"
CATALOG = ROOT / "data" / "synthetic" / "dealer_catalog.sif"
pytestmark = pytest.mark.skipif(not DXF.exists(), reason="sample DXF not generated")


def _fit():
    plan = ingest_dxf(str(DXF))
    spec = WorkstationSpec()
    fit = generate_mixed_layout(plan, spec, ProgramSpec())
    return plan, spec, fit


def test_rooms_are_placed():
    _plan, _spec, fit = _fit()
    assert fit.office_count > 0, "expected private offices on the sample plate"
    assert fit.meeting_count > 0, "expected at least one meeting room"
    assert fit.workstation_count > 0
    # program summary is exposed for the frontend
    assert fit.program and fit.program["headcount"] > 0
    types = {i.type for i in fit.instances}
    assert "workstation" in types and "private_office" in types and "meeting_room" in types


def test_all_instances_geometrically_valid_and_non_overlapping():
    plan, spec, fit = _fit()
    boundary = Polygon(plan.boundary).buffer(-spec.perimeter_setback_ft)
    cores = [Polygon(c) for c in plan.cores]
    columns = [Point(c).buffer(spec.column_clearance_ft) for c in plan.columns]

    # The structural rooms tile the plan; slotted Steelcase furniture lives INSIDE the room boxes
    # (overlapping them by design), so it's excluded from the tiling/non-overlap invariant.
    rooms = [i for i in fit.instances if not i.slotted]
    rects = [box(i.x, i.y, i.x + i.w, i.y + i.h) for i in rooms]
    assert len(rects) == (fit.workstation_count + fit.office_count
                          + fit.meeting_count + fit.collab_count)

    for r in rects:
        assert boundary.contains(r)                          # inside usable boundary
        assert all(not r.intersects(c) for c in cores)       # clear of core
        assert all(not r.intersects(col) for col in columns)  # clear of columns

    # Every pair of instances is non-overlapping (area-wise).
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert rects[i].intersection(rects[j]).area < 1e-6


def test_slotted_furniture_stays_inside_its_room_and_is_specd():
    """No furniture spills over a wall: every slotted piece sits inside a room box. And only real,
    SKU-tagged pieces are slotted (the un-spec'd CET sub-components that caused the tangle are
    dropped). A no-op assertion when no Steelcase library is present (nothing slotted)."""
    _plan, _spec, fit = _fit()
    slotted = [i for i in fit.instances if i.slotted]
    rooms = [
        box(i.x, i.y, i.x + i.w, i.y + i.h)
        for i in fit.instances if not i.slotted and i.type in SLOTTABLE_TYPES
    ]
    for s in slotted:
        # only recognizable furniture is slotted — the 'other' CET sub-parts (base/bracket/seat
        # blocks of one physical item) overlap each other and are the source of the tangle.
        assert s.type != "other", f"un-categorized CET sub-component slotted at ({s.x},{s.y})"
        piece = box(s.x, s.y, s.x + s.w, s.y + s.h)
        inside = any(r.intersection(piece).area >= piece.area - 0.1 for r in rooms)
        assert inside, f"slotted {s.type} at ({s.x},{s.y}) {s.w}x{s.h} spills outside every room"


def test_meeting_room_size_is_reasonable():
    _plan, _spec, fit = _fit()
    for i in fit.instances:
        if i.type == "meeting_room":
            # sized to a real Steelcase meeting application (>= ~110 sf setting + clearance), not a
            # tiny box; the legacy parametric room was a fixed 20x15.
            assert i.w * i.h >= 100


def _seeded_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    seed(db)
    if CATALOG.exists():
        service.upsert_catalog(db, parse_sif(CATALOG.read_text()), source="sif")
    return db


def test_bom_has_multiple_sku_types_and_prices_out():
    _plan, _spec, fit = _fit()
    demand = sku_demand(fit)
    # workstation desk + chair (chair now maps to the REAL Aeron AER1), office desk,
    # meeting table — multiple distinct SKU types across the layout.
    assert "SC-OLOGY-RECT" in demand and "AER1" in demand   # desk (synthetic) + real chair
    assert "HM-RENEW-SS" in demand                           # private-office desk
    assert "HM-EVERYWHERE-6" in demand                       # meeting table
    assert len(demand) >= 4

    db = _seeded_session()
    try:
        bom, quote, skipped = _build_bom_and_quote(db, fit)
    finally:
        db.close()

    # On a synthetic-only catalog the real-only SKUs (AER1/PX100) gracefully fall back/skip;
    # the real-catalog path is covered in test_realdata.py. Here we check BOM mechanics.
    assert isinstance(skipped, list)
    assert len({line["sku"] for line in bom}) >= 3  # multiple distinct SKU types still price out
    assert all(line["qty"] > 0 and line["unit_list"] > 0 for line in bom)
    assert quote["subtotal_list"] > 0
    assert quote["net_merchandise"] < quote["subtotal_list"]  # discount applied
    assert quote["total"] > quote["net_merchandise"]          # install/freight/tax added
    assert quote["is_budgetary"] is True
