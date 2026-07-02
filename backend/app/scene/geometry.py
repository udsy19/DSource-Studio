"""Pure geometry over a scene — shared by metrics, export, and the move/rotate commands.

Single source of truth for where a placed item actually lands in world feet (resolving a
placement's transform + a plate item's local pose + any per-item override) and for keeping an item
inside its zone. Kept pure (no scene mutation) so metrics stay a pure function of the scene.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.affinity import rotate as _rotate
from shapely.geometry import Polygon, box

from .model import Placement, PlacementItem, Plate, Scene, Zone


@dataclass
class ResolvedItem:
    """A placed item in world feet — its min-corner (x, y), size (w, h) and rotation about centre."""

    zone_id: str
    category: str
    model: str | None
    x: float
    y: float
    w: float
    h: float
    rotation: float


def zone_polygon(zone: Zone) -> Polygon:
    return Polygon(zone.polygon)


def _pose(placement: Placement, item: PlacementItem, plate: Plate) -> tuple[float, float, float]:
    """(local dx, local dy, rotation) of an item relative to the plate origin — the override when
    present, else the plate item's own pose."""
    base = plate.items[item.plate_item_ref]
    if item.transform_override is not None:
        t = item.transform_override
        return t.x, t.y, t.rotation
    return base.dx, base.dy, base.rotation


def resolved_items(scene: Scene) -> list[ResolvedItem]:
    """Every non-deleted placed item in world feet. Used by metrics, export and clamping."""
    out: list[ResolvedItem] = []
    for placement in scene.placements:
        plate = scene.plates.get(placement.plate_id)
        if plate is None:
            continue
        for item in placement.items:
            if item.deleted or item.plate_item_ref >= len(plate.items):
                continue
            base = plate.items[item.plate_item_ref]
            dx, dy, rot = _pose(placement, item, plate)
            out.append(ResolvedItem(
                zone_id=placement.zone_id,
                category=base.category, model=base.model,
                x=placement.transform.x + dx, y=placement.transform.y + dy,
                w=base.w, h=base.h, rotation=rot,
            ))
    return out


def item_footprint(x: float, y: float, w: float, h: float, rotation: float) -> Polygon:
    """The item's footprint polygon in world feet, rotated about its centre (matches the engine)."""
    rect = box(x, y, x + w, y + h)
    return _rotate(rect, rotation, origin="center") if rotation else rect


def clamp_local_into_zone(
    zone: Zone, plate: Plate, item_ref: int, dx: float, dy: float, rotation: float
) -> tuple[float, float]:
    """Clamp a LOCAL translation (dx, dy) so the item's world footprint stays inside `zone`.

    Positions are local to the placement origin, which for scene_from_generated is the zone
    min-corner, so we clamp against the zone bounds in that same local frame. Deterministic: shifts
    the footprint the minimum amount needed; if the zone is smaller than the item it pins to the
    zone min-corner.
    """
    base = plate.items[item_ref]
    zminx, zminy, zmaxx, zmaxy = zone_polygon(zone).bounds
    # world footprint bounds for a trial (dx, dy) — the placement origin is (zminx, zminy) here.
    fminx, fminy, fmaxx, fmaxy = item_footprint(
        zminx + dx, zminy + dy, base.w, base.h, rotation
    ).bounds

    # Shift the minimum amount to bring the footprint inside; if it is wider/taller than the zone,
    # pin its min-corner to the zone's min-corner.
    if (fmaxx - fminx) >= (zmaxx - zminx) or fminx < zminx:
        dx += zminx - fminx
    elif fmaxx > zmaxx:
        dx -= fmaxx - zmaxx
    if (fmaxy - fminy) >= (zmaxy - zminy) or fminy < zminy:
        dy += zminy - fminy
    elif fmaxy > zmaxy:
        dy -= fmaxy - zmaxy
    return round(dx, 3), round(dy, 3)
