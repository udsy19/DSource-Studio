"""IFC/BIM export — author a valid IFC4 building model from a generated test-fit.

The open-standard route to the "editable Revit/BIM" deliverable: a native .rvt would require paid
Autodesk Platform Services, so we emit IFC4 via IfcOpenShell, which opens in Revit, ArchiCAD, and
any web IFC viewer. Geometry is intentionally simple — a floor slab, perimeter walls, one IfcSpace
per enclosed room, and a box per furniture instance. Real catalog geometry is out of scope; these
are honest placeholders sized from the plan, not fabricated detail.

World coordinates are in the plan's units (feet for the CAD sample); they are converted to IFC SI
metres and baked into each element's profile, so every element shares the storey placement and we
avoid per-element placement matrices.
"""

from __future__ import annotations

import ifcopenshell
import ifcopenshell.api
from ifcopenshell.api import run
from ifcopenshell.util.shape_builder import ShapeBuilder, V

from ..floorplan.dxf_ingest import PlanModel
from ..testfit.layout import TestFit

FT_TO_M = 0.3048
WALL_HEIGHT_M = 3.0  # ~10 ft
WALL_THICKNESS_M = 0.1
FURNITURE_HEIGHT_M = 0.75
SLAB_THICKNESS_M = 0.2

_ENCLOSED = {"private_office", "meeting_room", "collaboration"}
_ROOM_LABEL = {
    "private_office": "Private Office",
    "meeting_room": "Meeting Room",
    "collaboration": "Collaboration",
}
_FURNITURE_LABEL = {
    "workstation": "Workstation",
    "private_office": "Office furniture",
    "meeting_room": "Meeting furniture",
    "collaboration": "Lounge furniture",
}


def _rect(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    """A closed rectangle in metres from a (x, y, w, h) footprint given in plan units."""
    return [
        (x * FT_TO_M, y * FT_TO_M),
        ((x + w) * FT_TO_M, y * FT_TO_M),
        ((x + w) * FT_TO_M, (y + h) * FT_TO_M),
        (x * FT_TO_M, (y + h) * FT_TO_M),
    ]


def _extruded(builder: ShapeBuilder, body, points, height_m: float, z0_m: float = 0.0):
    """A swept-solid body representation: extrude a closed polyline profile upward."""
    curve = builder.polyline([V(p[0], p[1]) for p in points], closed=True)
    profile = builder.profile(curve)
    solid = builder.extrude(profile, magnitude=height_m, position=(0.0, 0.0, z0_m))
    return builder.get_representation(body, [solid])


def _wall_rect(a: tuple[float, float], b: tuple[float, float], thickness_m: float):
    """A thin rectangle (in metres) running from a to b — one perimeter wall segment."""
    ax, ay = a[0] * FT_TO_M, a[1] * FT_TO_M
    bx, by = b[0] * FT_TO_M, b[1] * FT_TO_M
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0.0:
        return None
    nx, ny = -dy / length * thickness_m, dx / length * thickness_m
    return [(ax, ay), (bx, by), (bx + nx, by + ny), (ax + nx, ay + ny)]


def build_ifc(plan: PlanModel, fit: TestFit, project_name: str = "DSource Studio") -> bytes:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = run("root.create_entity", model, ifc_class="IfcProject", name=project_name)
    run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = run("context.add_context", model, context_type="Model")
    body = run(
        "context.add_context", model,
        context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=ctx,
    )

    site = run("root.create_entity", model, ifc_class="IfcSite", name="Site")
    building = run("root.create_entity", model, ifc_class="IfcBuilding", name="Building")
    storey = run("root.create_entity", model, ifc_class="IfcBuildingStorey", name="Level 1")
    run("aggregate.assign_object", model, products=[site], relating_object=project)
    run("aggregate.assign_object", model, products=[building], relating_object=site)
    run("aggregate.assign_object", model, products=[storey], relating_object=building)

    builder = ShapeBuilder(model)

    def add(ifc_class: str, name: str, points, height_m: float, z0_m: float = 0.0) -> None:
        element = run("root.create_entity", model, ifc_class=ifc_class, name=name)
        rep = _extruded(builder, body, points, height_m, z0_m)
        run("geometry.assign_representation", model, product=element, representation=rep)
        if ifc_class == "IfcSpace":
            run("aggregate.assign_object", model, products=[element], relating_object=storey)
        else:
            run("spatial.assign_container", model, products=[element], relating_structure=storey)

    # Floor slab from the boundary polygon.
    boundary_m = [(px * FT_TO_M, py * FT_TO_M) for px, py in plan.boundary]
    if len(boundary_m) >= 3:
        slab = run("root.create_entity", model, ifc_class="IfcSlab", name="Floor")
        rep = _extruded(builder, body, boundary_m, SLAB_THICKNESS_M, -SLAB_THICKNESS_M)
        run("geometry.assign_representation", model, product=slab, representation=rep)
        run("spatial.assign_container", model, products=[slab], relating_structure=storey)

    # Perimeter walls along each boundary edge.
    pts = plan.boundary
    for i in range(len(pts)):
        seg = _wall_rect(pts[i], pts[(i + 1) % len(pts)], WALL_THICKNESS_M)
        if seg is not None:
            add("IfcWall", f"Perimeter wall {i + 1}", seg, WALL_HEIGHT_M)

    # One IfcSpace per enclosed room, and a furniture box per instance.
    for idx, inst in enumerate(fit.instances):
        if inst.type in _ENCLOSED:
            add("IfcSpace", f"{_ROOM_LABEL[inst.type]} {idx}", _rect(inst.x, inst.y, inst.w, inst.h),
                WALL_HEIGHT_M)
        add(
            "IfcFurnishingElement",
            f"{_FURNITURE_LABEL.get(inst.type, 'Furniture')} {idx}",
            _rect(inst.x, inst.y, inst.w, inst.h),
            FURNITURE_HEIGHT_M,
        )

    return model.to_string().encode("utf-8")
