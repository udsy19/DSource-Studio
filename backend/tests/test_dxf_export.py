"""DXF export tests — pure geometry, no DB/catalog/network.

Builds a small PlanModel + TestFit directly (mirrors test_detailed.py's `_plan()`), authors a DXF,
and re-parses it to assert the shell (boundary on A-WALL), furniture rectangles, and a room label
land on the right layers.
"""

import io

import ezdxf

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.dxf_export import build_testfit_dxf
from app.testfit.layout import FurnitureInstance, TestFit


def _plan() -> PlanModel:
    w, h = 140.0, 90.0
    boundary = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    area = w * h
    return PlanModel(
        units="feet", sqft_factor=1.0, boundary=boundary,
        gross_area_sf=area, core_area_sf=0.0, usable_area_sf=area,
        columns=[(40.0, 40.0)], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )


def _fit() -> TestFit:
    return TestFit(
        workstation_count=1, office_count=1,
        instances=[
            FurnitureInstance(type="private_office", x=5.0, y=5.0, w=10.0, h=12.0, rotation=0),
            FurnitureInstance(type="workstation", x=50.0, y=50.0, w=6.0, h=5.0, rotation=90),
        ],
        placeable_area_sf=12600.0,
    )


def _modelspace(data: bytes):
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    return doc.modelspace()


def test_dxf_starts_with_marker():
    data = build_testfit_dxf(_plan(), _fit())
    assert data.startswith(b"  0\nSECTION")


def test_boundary_polyline_on_a_wall():
    msp = _modelspace(build_testfit_dxf(_plan(), _fit()))
    walls = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "A-WALL"]
    assert len(walls) >= 1
    assert any(len(list(e.get_points())) == 5 for e in walls)


def test_furniture_rectangle_present():
    msp = _modelspace(build_testfit_dxf(_plan(), _fit()))
    furn = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer.startswith("A-FURN-")]
    assert len(furn) >= 1


def test_room_label_text_present():
    msp = _modelspace(build_testfit_dxf(_plan(), _fit()))
    labels = [e for e in msp.query("TEXT") if e.dxf.layer == "A-AREA-IDEN"]
    assert any(e.dxf.text == "PRIVATE_OFFICE" for e in labels)


def test_workstation_has_no_label():
    msp = _modelspace(build_testfit_dxf(_plan(), _fit()))
    texts = {e.dxf.text for e in msp.query("TEXT")}
    assert "WORKSTATION" not in texts


def test_column_circle_on_a_cols():
    msp = _modelspace(build_testfit_dxf(_plan(), _fit()))
    cols = [e for e in msp.query("CIRCLE") if e.dxf.layer == "A-COLS"]
    assert len(cols) == 1
