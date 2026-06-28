"""DXF/CAD export — author a real .dxf drawing from a generated test-fit.

The CAD route to the "open it in AutoCAD/Revit/any drafting tool" deliverable, alongside the
Excel takeoff and IFC/BIM exports. Geometry is intentionally simple and honest: the boundary and
service cores as closed wall polylines, structural columns as circles, and one rotated rectangle
per furniture instance on an AIA-style layer, with a centred room label for each enclosed room.
Units are feet (the plan's units), matching the IFC and takeoff exports.
"""

from __future__ import annotations

import io
import math

import ezdxf

from ..floorplan.dxf_ingest import PlanModel
from ..testfit.layout import TestFit

COLUMN_RADIUS_FT = 0.75
LABEL_HEIGHT_FT = 2.0

# type -> furniture layer. Enclosed rooms also get a centred text label.
_FURN_LAYER = {
    "private_office": "A-FURN-OFFICE",
    "meeting_room": "A-FURN-MEET",
    "collaboration": "A-FURN-COLLAB",
    "phone_booth": "A-FURN-BOOTH",
    "reception": "A-FURN-AMEN",
    "kitchen": "A-FURN-AMEN",
    "wellness": "A-FURN-AMEN",
    "copy_print": "A-FURN-AMEN",
    "storage": "A-FURN-AMEN",
    "workstation": "A-FURN-WORK",
}

# enclosed rooms get a centred label; the open workstation field does not (hundreds of desks).
_LABELLED = set(_FURN_LAYER) - {"workstation"}

# AIA-style layers with sensible AutoCAD Color Index colours.
_LAYERS = {
    "A-WALL": 7,           # white/black — boundary + cores
    "A-COLS": 8,           # grey — structural columns
    "A-FURN-OFFICE": 5,    # blue
    "A-FURN-MEET": 3,      # green
    "A-FURN-COLLAB": 4,    # cyan
    "A-FURN-BOOTH": 6,     # magenta
    "A-FURN-AMEN": 2,      # yellow
    "A-FURN-WORK": 9,      # light grey
    "A-AREA-IDEN": 1,      # red — room labels
}


def _rotated_rect(x: float, y: float, w: float, h: float, rotation: float) -> list[tuple[float, float]]:
    """The 4 footprint corners (x,y)-(x+w,y+h) rotated about the footprint centre by `rotation`
    degrees — matching the engine's convention (rotation about the footprint centre)."""
    cx, cy = x + w / 2.0, y + h / 2.0
    theta = math.radians(rotation)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    out: list[tuple[float, float]] = []
    for px, py in corners:
        dx, dy = px - cx, py - cy
        out.append((cx + dx * cos_t - dy * sin_t, cy + dx * sin_t + dy * cos_t))
    return out


def build_testfit_dxf(plan: PlanModel, fit: TestFit) -> bytes:
    """Author a DXF (R2010, units = feet) of the plan shell + the generated test-fit."""
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.FT
    for name, color in _LAYERS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    if len(plan.boundary) >= 3:
        msp.add_lwpolyline(plan.boundary, close=True, dxfattribs={"layer": "A-WALL"})
    for core in plan.cores:
        if len(core) >= 3:
            msp.add_lwpolyline(core, close=True, dxfattribs={"layer": "A-WALL"})
    for (cx, cy) in plan.columns:
        msp.add_circle((cx, cy), COLUMN_RADIUS_FT, dxfattribs={"layer": "A-COLS"})

    for inst in fit.instances:
        layer = _FURN_LAYER.get(inst.type, "A-FURN-WORK")
        corners = _rotated_rect(inst.x, inst.y, inst.w, inst.h, inst.rotation)
        msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": layer})
        if inst.type in _LABELLED:
            center = (inst.x + inst.w / 2.0, inst.y + inst.h / 2.0)
            text = msp.add_text(
                inst.type.upper(),
                height=LABEL_HEIGHT_FT,
                dxfattribs={"layer": "A-AREA-IDEN"},
            )
            text.set_placement(center, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
