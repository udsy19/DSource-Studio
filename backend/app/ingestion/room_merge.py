"""Merge two adjacent rooms into one larger space.

The pure geometry lives in `union_room_polygon`: shapely-union the two boundaries, bridging the
shared-wall gap with a symmetric buffer(+eps)/buffer(-eps) so the seam closes into one continuous
outline, then simplify. `merge_rooms` wraps it into an ExtractedLayout edit — the two rooms become
one (area, type/label, honest confidence), furniture is re-homed onto the survivor, and any wall
segment that now sits INSIDE the merged room (the former shared partition) is dropped.

All coordinates are in feet, so a polygon's shapely area is already square feet.
"""

from __future__ import annotations

from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.ops import unary_union

from .schema import ExtractedLayout, Room, Wall

# Buffer distance (feet) used to bridge the shared-wall gap between two adjacent rooms: grow both
# polygons by eps so their edges overlap across the wall, union, then shrink back by eps. 0.75 ft
# closes gaps up to ~1.5 ft (any interior partition) without visibly inflating the boundary.
_BRIDGE_FT = 0.75
# Simplify tolerance (feet) — collapses the near-duplicate vertices the buffer round-trip leaves.
_SIMPLIFY_FT = 0.1
# Wall types that can be an interior partition between two rooms (perimeter/core/door are never
# dropped by a merge — only these read as a droppable shared wall).
_PARTITION_WALL_TYPES = frozenset({"drywall", "half_drywall", "glass", "unknown"})
# A wall counts as interior when its representative point falls this far inside the merged room.
_INTERIOR_INSET_FT = 0.5


def union_room_polygon(
    poly_a: list[tuple[float, float]],
    poly_b: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Union two adjacent room boundaries into one outer ring, bridging the shared-wall gap.

    Returns the merged exterior ring as a list of (x, y) in feet. Raises ValueError if either
    input has fewer than 3 points (no area to union).
    """
    if len(poly_a) < 3 or len(poly_b) < 3:
        raise ValueError("both rooms need a closed polygon (>= 3 points) to merge")

    a = Polygon(poly_a).buffer(_BRIDGE_FT, join_style="mitre")
    b = Polygon(poly_b).buffer(_BRIDGE_FT, join_style="mitre")
    merged = unary_union([a, b]).buffer(-_BRIDGE_FT, join_style="mitre")

    # A clean adjacency yields one polygon; if the shapes barely touched and the shrink split it,
    # keep the largest piece so the result is always a single room.
    if isinstance(merged, MultiPolygon):
        merged = max(merged.geoms, key=lambda g: g.area)
    merged = merged.simplify(_SIMPLIFY_FT, preserve_topology=True)

    coords = list(merged.exterior.coords)
    # shapely closes the ring (last == first); drop the duplicate to match the schema convention.
    if len(coords) > 1 and coords[0] == coords[-1]:
        coords = coords[:-1]
    return [(round(x, 2), round(y, 2)) for x, y in coords]


def merge_rooms(layout: ExtractedLayout, room_a: str, room_b: str) -> ExtractedLayout:
    """Replace rooms `room_a` and `room_b` with one merged room; re-home furniture, drop the
    now-interior shared wall. Raises ValueError if either id is missing."""
    rooms_by_id = {r.id: r for r in layout.rooms}
    a = rooms_by_id.get(room_a)
    b = rooms_by_id.get(room_b)
    if a is None or b is None:
        raise ValueError(f"room not found: {room_a if a is None else room_b}")
    if a.id == b.id:
        raise ValueError("cannot merge a room with itself")

    ring = union_room_polygon(a.polygon, b.polygon)
    merged_poly = Polygon(ring)
    area_sf = round(merged_poly.area, 1)
    centroid = merged_poly.centroid

    # The survivor keeps room_a's id (so callers can find the merged room). Label/type come from the
    # larger contributor — the dominant space wins — and confidence is the weaker of the two (a merge
    # is no more trustworthy than its shakiest input; the bridged seam makes it best-effort).
    larger = a if (a.area_sf or 0.0) >= (b.area_sf or 0.0) else b
    merged_room = Room(
        id=a.id,
        label=larger.label,
        area_sf=area_sf,
        polygon=ring,
        center=(round(centroid.x, 2), round(centroid.y, 2)),
        type=larger.type,
        boundary_basis="merged",
        confidence=round(min(a.confidence, b.confidence), 3),
    )

    rooms = [r for r in layout.rooms if r.id not in (a.id, b.id)] + [merged_room]

    # Re-home furniture that pointed at the absorbed room onto the survivor.
    furniture = [
        f.model_copy(update={"room_id": merged_room.id}) if f.room_id == b.id else f
        for f in layout.furniture
    ]

    walls = [w for w in layout.walls if not _is_interior_partition(w, merged_poly)]

    return layout.model_copy(update={"rooms": rooms, "furniture": furniture, "walls": walls})


def _is_interior_partition(wall: Wall, merged_poly: Polygon) -> bool:
    """True when a wall is the former shared partition now inside the merged room — a droppable
    interior segment. Perimeter/core/door walls and any wall on the merged boundary are kept."""
    if wall.type not in _PARTITION_WALL_TYPES or len(wall.points) < 2:
        return False
    interior = merged_poly.buffer(-_INTERIOR_INSET_FT)
    if interior.is_empty:
        return False
    midpoint = LineString(wall.points).interpolate(0.5, normalized=True)
    return interior.contains(midpoint)
