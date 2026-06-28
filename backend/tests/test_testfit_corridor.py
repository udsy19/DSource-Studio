"""Circulation realism — the open workstation field is broken by a desk-free spine + cross-aisles.

A real test-fit reads as neighborhoods around a primary corridor, not one solid block of desks.
We assert geometrically that:
  * a circulation spine + cross-aisles are carved from the placeable open field,
  * NO workstation sits in any corridor band (the spine breaks the desk field),
  * carving corridors strictly reduces the desk count vs. an uncarved grid (the field is split),
  * perimeter private offices remain non-overlapping,
  * the carve is deterministic (same plan -> identical layout).
"""

from pathlib import Path

import pytest
from shapely.geometry import Polygon, box

from app.floorplan.dxf_ingest import ingest_dxf
from app.testfit.layout import (
    ProgramSpec,
    WorkstationSpec,
    _place_workstation_field,
    _placeable_region,
    circulation_corridors,
    generate_mixed_layout,
)

DXF = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"
pytestmark = pytest.mark.skipif(not DXF.exists(), reason="sample DXF not generated")


def _fit():
    plan = ingest_dxf(str(DXF))
    return plan, WorkstationSpec(), generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())


def test_circulation_bands_exist_and_break_the_field():
    plan, spec = ingest_dxf(str(DXF)), WorkstationSpec()
    region = _placeable_region(plan, spec)
    bands = circulation_corridors(region, spec)
    # one primary spine + at least one cross-aisle on a plate this size.
    assert len(bands) >= 2
    # the spine spans (near-)fully across one axis of the field.
    minx, miny, maxx, maxy = region.bounds
    spine = max(bands, key=lambda b: b.area)
    sx0, sy0, sx1, sy1 = spine.bounds
    spans_x = (sx1 - sx0) >= 0.9 * (maxx - minx)
    spans_y = (sy1 - sy0) >= 0.9 * (maxy - miny)
    assert spans_x or spans_y


def test_no_workstation_sits_in_a_corridor():
    plan, spec, fit = _fit()
    region = _placeable_region(plan, spec)
    bands = circulation_corridors(region, spec)
    desks = [box(i.x, i.y, i.x + i.w, i.y + i.h) for i in fit.instances if i.type == "workstation"]
    for d in desks:
        for band in bands:
            assert d.intersection(band).area < 1e-6


def test_corridor_carving_reduces_desk_count():
    """Carving the spine + cross-aisles must remove desks vs. the same region gridded whole."""
    plan, spec = ingest_dxf(str(DXF)), WorkstationSpec()
    region = _placeable_region(plan, spec)
    carved = len(_place_workstation_field(region, spec))
    no_circulation = WorkstationSpec(corridor_ft=0.0)
    uncarved = len(_place_workstation_field(region, no_circulation))
    assert 0 < carved < uncarved


def test_perimeter_offices_do_not_overlap():
    _plan, _spec, fit = _fit()
    offices = [box(i.x, i.y, i.x + i.w, i.y + i.h)
               for i in fit.instances if i.type == "private_office"]
    assert offices
    for i in range(len(offices)):
        for j in range(i + 1, len(offices)):
            assert offices[i].intersection(offices[j]).area < 1e-6


def test_layout_is_deterministic():
    plan = ingest_dxf(str(DXF))
    a = generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())
    b = generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())
    pa = [(i.type, i.x, i.y, i.w, i.h) for i in a.instances]
    pb = [(i.type, i.x, i.y, i.w, i.h) for i in b.instances]
    assert pa == pb
