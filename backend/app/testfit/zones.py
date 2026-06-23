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

COLLAB_SIZE_FT = 12.0  # ~12x12 lounge cluster


@dataclass
class PlacedZone:
    type: str
    x: float
    y: float
    w: float
    h: float
    rotation: int = 0


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

    minx, miny, maxx, maxy = placeable_region.bounds
    cx = (minx + maxx) / 2
    cy = (miny + maxy) / 2

    # Candidate origins on a coarse grid, sorted by distance from centroid (interior-first).
    step = size_ft + margin_ft
    candidates: list[tuple[float, float, float]] = []
    y = miny
    while y + size_ft <= maxy:
        x = minx
        while x + size_ft <= maxx:
            ox, oy = x + size_ft / 2, y + size_ft / 2
            dist = (ox - cx) ** 2 + (oy - cy) ** 2
            candidates.append((dist, x, y))
            x += step / 2  # finer scan than the placement step for better fits
        y += step / 2
    candidates.sort(key=lambda t: t[0])

    for _dist, x, y in candidates:
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
