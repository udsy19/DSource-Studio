"""scene_to_dxf — author a .dxf from a scene, the inverse of DXF ingest.

Pure function, invokable per design on demand. The immutable underlay is passed through unchanged
(shell/cores/columns/base doors), and the GENERATED, editable entities — partitions, doors, and
resolved placement items — are authored on their OWN named layers so a round-trip can tell base
building from generated design. Units are feet, mirroring dxf_ingest and testfit.dxf_export.
"""

from __future__ import annotations

import io

import ezdxf

from .geometry import item_footprint, resolved_items
from .model import Scene

# Underlay passes through on A-* layers (mirrors dxf_ingest / testfit.dxf_export); generated,
# editable entities get S-* layers so a reader can separate base building from generated design.
_LAYERS = {
    "A-WALL": 7,        # underlay shell + cores
    "A-COLS": 8,        # underlay columns
    "A-DOOR-BASE": 8,   # underlay (base-drawing) doors — display-only
    "S-PARTITION": 3,   # generated partitions
    "S-DOOR": 1,        # generated doors
    "S-ZONE": 4,        # generated zone outlines
    "S-FURN": 5,        # placed furniture items
}
_COLUMN_RADIUS_FT = 0.75
_DOOR_LEAF_THICKNESS_FT = 0.4


def _add_underlay(msp, scene: Scene) -> None:
    u = scene.underlay
    if len(u.boundary) >= 3:
        msp.add_lwpolyline(u.boundary, close=True, dxfattribs={"layer": "A-WALL"})
    for core in u.cores:
        if len(core) >= 3:
            msp.add_lwpolyline(core, close=True, dxfattribs={"layer": "A-WALL"})
    for (cx, cy) in u.columns:
        msp.add_circle((cx, cy), _COLUMN_RADIUS_FT, dxfattribs={"layer": "A-COLS"})
    for d in u.base_doors:
        msp.add_lwpolyline(
            [(d.x, d.y), (d.x + d.width, d.y)], dxfattribs={"layer": "A-DOOR-BASE"}
        )


def _add_generated(msp, scene: Scene) -> None:
    for zone in scene.zones:
        if len(zone.polygon) >= 3:
            msp.add_lwpolyline(zone.polygon, close=True, dxfattribs={"layer": "S-ZONE"})
    hosts = {p.id: p for p in scene.partitions}
    for part in scene.partitions:
        (x1, y1), (x2, y2) = part.segment
        msp.add_lwpolyline([(x1, y1), (x2, y2)], dxfattribs={"layer": "S-PARTITION"})
    for door in scene.doors:
        host = hosts.get(door.host_partition_id)
        if host is None:
            continue
        (x1, y1), (x2, y2) = host.segment
        length = host.length() or 1.0
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        sx, sy = x1 + ux * door.offset, y1 + uy * door.offset
        ex, ey = sx + ux * door.width, sy + uy * door.width
        # leaf offset to the swing side (perpendicular), so the door reads as an opening, not a wall.
        sign = 1.0 if door.swing == "left" else -1.0
        nx, ny = -uy * _DOOR_LEAF_THICKNESS_FT * sign, ux * _DOOR_LEAF_THICKNESS_FT * sign
        msp.add_lwpolyline(
            [(sx, sy), (ex, ey), (ex + nx, ey + ny)], dxfattribs={"layer": "S-DOOR"}
        )


def _add_items(msp, scene: Scene) -> None:
    for it in resolved_items(scene):
        corners = list(item_footprint(it.x, it.y, it.w, it.h, it.rotation).exterior.coords)
        msp.add_lwpolyline(corners, close=True, dxfattribs={"layer": "S-FURN"})


def scene_to_dxf(scene: Scene) -> bytes:
    """Author a DXF (R2010, units = feet): underlay passthrough + generated design on S-* layers."""
    doc = ezdxf.new("R2010")
    doc.units = ezdxf.units.FT
    for name, color in _LAYERS.items():
        doc.layers.add(name, color=color)
    msp = doc.modelspace()

    _add_underlay(msp, scene)
    _add_generated(msp, scene)
    _add_items(msp, scene)

    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
