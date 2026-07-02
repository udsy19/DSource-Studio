"""Scene metrics — a PURE function of the scene, recomputed after every command.

Reuses the existing live-layout metric logic (`ingestion.layout_metrics.compute_layout_metrics`)
rather than reinventing seats/areas/density: the scene is projected to an `ExtractedLayout` view and
scored, then a program scoreboard (actual vs target per room type) is laid on top against
`scene.program_ref`. Nothing is invented — every number derives from the scene geometry.
"""

from __future__ import annotations

from collections import Counter

from shapely.geometry import Polygon

from ..ingestion.layout_metrics import compute_layout_metrics
from ..ingestion.schema import ExtractedLayout, FurnitureItem, Room
from .geometry import resolved_items
from .model import Scene

# scene room_type -> the layout room `type` vocabulary compute_layout_metrics understands (its
# enclosed-seat test keys off office/meeting/huddle).
_ROOM_TYPE_TO_LAYOUT = {
    "private_office": "office",
    "meeting_room": "meeting",
    "collaboration": "collab",
    "open": "open",
    "open_plan": "open",
}


def _scene_as_layout(scene: Scene) -> ExtractedLayout:
    """Project the scene into the shared ExtractedLayout shape so the live-layout metrics apply."""
    items = resolved_items(scene)
    rooms = [
        Room(
            id=z.id, label=None,
            area_sf=round(Polygon(z.polygon).area, 1) if len(z.polygon) >= 3 else None,
            polygon=list(z.polygon),
            type=_ROOM_TYPE_TO_LAYOUT.get(z.room_type, z.room_type),
            boundary_basis="walls_closed" if z.enclosed else "open", confidence=1.0,
        )
        for z in scene.zones
    ]
    furniture = [
        FurnitureItem(
            category=it.category, block_name=it.model or it.category,
            brand=None, model=it.model,
            x=it.x, y=it.y, w=it.w, h=it.h, rotation=it.rotation, room_id=it.zone_id,
        )
        for it in items
    ]
    xs = [x for x, _ in scene.underlay.boundary]
    ys = [y for _, y in scene.underlay.boundary]
    bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 0.0, 0.0)
    return ExtractedLayout(source="cad", units="ft", bounds=bounds, rooms=rooms, furniture=furniture)


def _program_scoreboard(scene: Scene) -> dict:
    """Actual zone counts per room type vs the program targets — the editor's scoreboard."""
    actual = Counter(z.room_type for z in scene.zones)
    lines = [
        {"room_type": line.room_type, "label": line.label,
         "target": line.target, "actual": actual.get(line.room_type, 0)}
        for line in scene.program_ref.lines
    ]
    return {
        "headcount": scene.program_ref.headcount,
        "density_rsf_per_person": scene.program_ref.density_rsf_per_person,
        "lines": lines,
    }


def compute_scene_metrics(scene: Scene) -> dict:
    """Seats, areas, density and room mix (from compute_layout_metrics) + the program scoreboard."""
    metrics = compute_layout_metrics(_scene_as_layout(scene))
    metrics["program"] = _program_scoreboard(scene)
    return metrics
