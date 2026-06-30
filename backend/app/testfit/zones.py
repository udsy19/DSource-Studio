"""Collaboration-zone placement for the mixed test-fit (open lounge areas).

Collaboration zones are open (un-walled) lounge footprints dropped into the INTERIOR of the
plate, after perimeter rooms are placed. Like the rooms, this is a deterministic greedy
heuristic, not an optimizer: we scan the interior placeable region on a coarse grid and drop
square lounge footprints where they are fully valid and non-overlapping with everything placed
so far. We bias toward the centroid (interior) so lounges land in the open field, not jammed
against the rooms.

Deferred: adjacency rules (lounges near circulation/cafe), acoustic separation. Geometric
validity + non-overlap ARE enforced.
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.prepared import prep

from .rooms import PlacedRoom, RoomSpec

COLLAB_SIZE_FT = 12.0  # ~12x12 lounge cluster


@dataclass
class PlacedZone:
    type: str
    x: float
    y: float
    w: float
    h: float
    rotation: int = 0


def _interior_candidates(
    region: Polygon, w: float, h: float, margin_ft: float
) -> list[tuple[float, float]]:
    """Coarse grid of (x, y) origins for a w x h footprint, sorted centroid-first (interior bias)."""
    minx, miny, maxx, maxy = region.bounds
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    step = max(w, h) + margin_ft
    out: list[tuple[float, float, float]] = []
    y = miny
    while y + h <= maxy:
        x = minx
        while x + w <= maxx:
            ox, oy = x + w / 2, y + h / 2
            out.append(((ox - cx) ** 2 + (oy - cy) ** 2, x, y))
            x += step / 2  # finer scan than the placement step for better fits
        y += step / 2
    out.sort(key=lambda t: t[0])
    return [(x, y) for _d, x, y in out]


def place_collaboration_zones(
    placeable_region: Polygon,
    occupied_polys: list[Polygon],
    target_count: int,
    size_ft: float = COLLAB_SIZE_FT,
    margin_ft: float = 2.0,
) -> list[PlacedZone]:
    """Drop up to `target_count` lounge footprints into the interior placeable region.

    `placeable_region` is the usable area already net of perimeter setback, core, and columns.
    `occupied_polys` are footprints (rooms, etc.) we must not overlap. A `margin_ft` gap is
    kept around lounges so they read as distinct open clusters, not abutting the rooms.
    """
    if target_count <= 0 or placeable_region.is_empty:
        return []

    prepared = prep(placeable_region)
    placed: list[PlacedZone] = []
    placed_polys: list[Polygon] = list(occupied_polys)

    for x, y in _interior_candidates(placeable_region, size_ft, size_ft, margin_ft):
        if len(placed) >= target_count:
            break
        rect = box(x, y, x + size_ft, y + size_ft)
        if not prepared.contains(rect):
            continue
        grown = rect.buffer(margin_ft, join_style=2)
        if any(grown.intersects(pp) for pp in placed_polys):
            continue
        placed.append(PlacedZone(
            type="collaboration", x=round(x, 2), y=round(y, 2),
            w=size_ft, h=size_ft, rotation=0,
        ))
        placed_polys.append(rect)
    return placed


def place_interior_rooms(
    placeable_region: Polygon,
    occupied_polys: list[Polygon],
    room_order: list[RoomSpec],
    margin_ft: float = 2.0,
) -> list[PlacedRoom]:
    """Drop explicit rooms (core placement) into the interior, biased toward the centroid/core.

    Mirrors `place_collaboration_zones` but for arbitrary RoomSpec footprints — used by the
    Detailed program for `placement="core"` rooms. Largest-first so big rooms claim space before
    small ones fragment it. Returns PlacedRoom rects; geometric validity + non-overlap enforced.
    """
    if not room_order or placeable_region.is_empty:
        return []

    prepared = prep(placeable_region)
    placed: list[PlacedRoom] = []
    placed_polys: list[Polygon] = list(occupied_polys)

    for spec in sorted(room_order, key=lambda s: s.width_ft * s.depth_ft, reverse=True):
        w, h = spec.width_ft, spec.depth_ft
        for x, y in _interior_candidates(placeable_region, w, h, margin_ft):
            rect = box(x, y, x + w, y + h)
            if not prepared.contains(rect):
                continue
            if any(rect.buffer(margin_ft, join_style=2).intersects(pp) for pp in placed_polys):
                continue
            placed.append(PlacedRoom(
                type=spec.type, x=round(x, 2), y=round(y, 2), w=w, h=h, rotation=0,
                setting=spec.setting,
            ))
            placed_polys.append(rect)
            break
    return placed
