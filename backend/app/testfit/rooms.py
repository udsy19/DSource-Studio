"""Enclosed-room placement for the mixed test-fit (private offices + meeting rooms).

This is the "perimeter band" packer. Real test-fits put enclosed rooms (private offices,
meeting/conference rooms) against the exterior glass line so the open field keeps the
daylit interior. We reproduce that pattern PROCEDURALLY:

  1. Walk the exterior boundary edge-by-edge.
  2. For each straight edge long enough to host a room, march room-sized rectangles along
     it, flush to the wall (inset by the perimeter setback), trying meeting rooms first
     (bigger) then private offices.
  3. Keep a candidate only if it is fully inside the usable boundary AND clear of the core
     and every column AND non-overlapping with rooms already placed.

This is a greedy, deterministic heuristic — NOT an optimizer. It does not guarantee maximal
room packing and it does not yet model door swings, corridors, or egress spines (deferred;
see notes). It DOES guarantee geometric validity + mutual non-overlap, which is the gate the
downstream BOM/quote depends on.

OR-Tools CP-SAT could pack these rooms optimally, but for an L-shaped plate with a handful
of rooms the greedy edge-march is fast (<<1s), reliable, and human-legible, so we use it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep


@dataclass
class RoomSpec:
    type: str
    width_ft: float
    depth_ft: float  # depth measured perpendicular to the wall it sits against


# Reasonable program rectangles (feet). Depth = how far the room reaches in from the wall.
PRIVATE_OFFICE = RoomSpec(type="private_office", width_ft=10.0, depth_ft=12.0)
MEETING_ROOM = RoomSpec(type="meeting_room", width_ft=20.0, depth_ft=15.0)


@dataclass
class PlacedRoom:
    type: str
    x: float
    y: float
    w: float
    h: float
    rotation: int = 0


def _edges(boundary: Polygon) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    coords = list(boundary.exterior.coords)
    return [(coords[i], coords[i + 1]) for i in range(len(coords) - 1)]


def _interior_normal(boundary: Polygon, p1, p2):
    """Unit normal of edge (p1->p2) pointing INTO the polygon."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return None, None, 0.0
    tx, ty = dx / length, dy / length
    # two candidate normals
    n1 = (-ty, tx)
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    test = Point(mx + n1[0] * 0.5, my + n1[1] * 0.5)
    normal = n1 if boundary.contains(test) else (ty, -tx)
    return (tx, ty), normal, length


def _room_rect(p1, tangent, normal, along: float, room_w: float, room_d: float, setback: float):
    """Build a room rectangle anchored at distance `along` from p1, inset `setback` from wall."""
    tx, ty = tangent
    nx, ny = normal
    # near-wall edge start, pushed in by the perimeter setback
    bx = p1[0] + tx * along + nx * setback
    by = p1[1] + ty * along + ny * setback
    corners = [
        (bx, by),
        (bx + tx * room_w, by + ty * room_w),
        (bx + tx * room_w + nx * room_d, by + ty * room_w + ny * room_d),
        (bx + nx * room_d, by + ny * room_d),
    ]
    return Polygon(corners)


def _axis_aligned_bbox(poly: Polygon) -> tuple[float, float, float, float]:
    minx, miny, maxx, maxy = poly.bounds
    return minx, miny, maxx, maxy


def place_perimeter_rooms(
    boundary_poly: Polygon,
    cores: list[Polygon],
    column_circles: list,
    setback_ft: float,
    target_offices: int,
    target_meetings: int,
    column_clearance_ft: float = 1.5,
) -> list[PlacedRoom]:
    """Greedy edge-march placement of enclosed rooms along the exterior wall.

    Returns axis-aligned PlacedRoom rects. We only place rooms on axis-aligned edges
    (horizontal/vertical), which covers orthogonal office plates; skewed walls are skipped
    (deferred). Counts are targets, not guarantees — we place up to the target that fits.
    """
    placed: list[PlacedRoom] = []
    placed_polys: list[Polygon] = []
    usable = boundary_poly
    prepared_usable = prep(usable)

    def valid(rect: Polygon) -> bool:
        if not prepared_usable.contains(rect):
            return False
        if any(rect.intersects(c) for c in cores):
            return False
        if any(rect.intersects(col) for col in column_circles):
            return False
        if any(rect.intersection(pp).area > 1e-9 for pp in placed_polys):
            return False
        return True

    # Try meeting rooms first (scarcer, bigger), then offices, walking each wall edge.
    plan_order = (
        [MEETING_ROOM] * target_meetings + [PRIVATE_OFFICE] * target_offices
    )
    remaining = {"meeting_room": target_meetings, "private_office": target_offices}

    edges = _edges(boundary_poly)
    for (p1, p2) in edges:
        tangent, normal, length = _interior_normal(boundary_poly, p1, p2)
        if tangent is None:
            continue
        tx, ty = tangent
        # only axis-aligned edges (orthogonal plates)
        if abs(tx) > 1e-6 and abs(ty) > 1e-6:
            continue
        along = 0.0
        guard = 0
        while along < length and guard < 200:
            guard += 1
            specs = [s for s in (MEETING_ROOM, PRIVATE_OFFICE) if remaining[s.type] > 0]
            if not specs:
                break
            placed_one = False
            for spec in specs:
                if remaining[spec.type] <= 0:
                    continue
                if along + spec.width_ft > length + 1e-6:
                    continue
                rect = _room_rect(p1, tangent, normal, along, spec.width_ft, spec.depth_ft, setback_ft)
                if not rect.is_valid or rect.area <= 0:
                    continue
                if valid(rect):
                    minx, miny, maxx, maxy = _axis_aligned_bbox(rect)
                    placed.append(PlacedRoom(
                        type=spec.type, x=round(minx, 2), y=round(miny, 2),
                        w=round(maxx - minx, 2), h=round(maxy - miny, 2), rotation=0,
                    ))
                    placed_polys.append(rect)
                    remaining[spec.type] -= 1
                    along += spec.width_ft  # march past this room
                    placed_one = True
                    break
            if not placed_one:
                along += 2.0  # nudge along the wall and retry
    return placed
