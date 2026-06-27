"""IFC export: build_ifc authors a valid IFC4 building (slab + walls + spaces + furniture)."""

from __future__ import annotations

import ifcopenshell

from app.floorplan.dxf_ingest import PlanModel
from app.ifc.service import build_ifc
from app.testfit.layout import generate_mixed_layout


def _plan() -> PlanModel:
    return PlanModel(
        units="ft", sqft_factor=1.0,
        boundary=[(0, 0), (120, 0), (120, 90), (0, 90)],
        gross_area_sf=10800, core_area_sf=0, usable_area_sf=10000, columns=[], cores=[],
    )


def test_build_ifc_emits_valid_ifc_spf():
    data = build_ifc(_plan(), generate_mixed_layout(_plan()))
    assert data[:13] == b"ISO-10303-21;"  # IFC-SPF header — opens in any IFC viewer


def test_build_ifc_has_slab_walls_spaces_and_furniture():
    plan = _plan()
    fit = generate_mixed_layout(plan)
    model = ifcopenshell.file.from_string(build_ifc(plan, fit).decode())

    assert len(model.by_type("IfcSlab")) >= 1
    assert len(model.by_type("IfcWall")) == len(plan.boundary)  # one perimeter wall per edge
    # one IfcSpace per enclosed room (offices + meeting + collaboration)
    enclosed = sum(1 for i in fit.instances if i.type in {"private_office", "meeting_room", "collaboration"})
    assert len(model.by_type("IfcSpace")) == enclosed
    # a furnishing element per placed instance
    assert len(model.by_type("IfcFurnishingElement")) == len(fit.instances)


def test_build_ifc_units_are_metric():
    model = ifcopenshell.file.from_string(build_ifc(_plan(), generate_mixed_layout(_plan())).decode())
    units = model.by_type("IfcUnitAssignment")[0].Units
    length = next(u for u in units if getattr(u, "UnitType", None) == "LENGTHUNIT")
    assert length.Name == "METRE"
