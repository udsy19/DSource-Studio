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
from typing import TYPE_CHECKING

from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

if TYPE_CHECKING:
    from .settings import Setting


@dataclass
class RoomSpec:
    type: str
    width_ft: float
    depth_ft: float  # depth measured perpendicular to the wall it sits against
    setting: "Setting | None" = None  # the Steelcase application this room IS (sized to its footprint)


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
    setting: "Setting | None" = None  # the Steelcase application that furnishes this room


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
    target_offices: int = 0,
    target_meetings: int = 0,
    column_clearance_ft: float = 1.5,
    room_order: list[RoomSpec] | None = None,
    occupied_polys: list[Polygon] | None = None,
) -> list[PlacedRoom]:
    """Greedy edge-march placement of enclosed rooms along the exterior wall.

    Returns axis-aligned PlacedRoom rects. We only place rooms on axis-aligned edges
    (horizontal/vertical), which covers orthogonal office plates; skewed walls are skipped
    (deferred). Counts are targets, not guarantees — we place up to what fits.

    `room_order` lets callers pass an explicit ordered list of RoomSpec to place (used by the
    Detailed program for arbitrary per-type counts incl. huddle/phone_booth). When omitted, the
    legacy `target_meetings`/`target_offices` path runs (meeting rooms first, then offices).
    `occupied_polys` are footprints already placed elsewhere (e.g. core rooms) to avoid.
    """
    placed: list[PlacedRoom] = []
    placed_polys: list[Polygon] = list(occupied_polys or [])
    prepared_usable = prep(boundary_poly)

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

    if room_order is None:
        # Legacy: meeting rooms first (scarcer, bigger), then offices.
        room_order = [MEETING_ROOM] * target_meetings + [PRIVATE_OFFICE] * target_offices

    # Largest-first so big rooms claim wall before small ones fragment it, preserving determinism.
    queue = sorted(room_order, key=lambda s: s.width_ft * s.depth_ft, reverse=True)

    for spec in queue:
        if _place_one_along_walls(spec, boundary_poly, setback_ft, valid, placed, placed_polys):
            continue
    return placed


def _place_one_along_walls(
    spec: RoomSpec,
    boundary_poly: Polygon,
    setback_ft: float,
    valid,
    placed: list[PlacedRoom],
    placed_polys: list[Polygon],
) -> bool:
    """March `spec` along every axis-aligned wall edge; place at the first valid slot."""
    for (p1, p2) in _edges(boundary_poly):
        tangent, normal, length = _interior_normal(boundary_poly, p1, p2)
        if tangent is None:
            continue
        tx, ty = tangent
        if abs(tx) > 1e-6 and abs(ty) > 1e-6:  # only axis-aligned edges
            continue
        along = 0.0
        guard = 0
        while along + spec.width_ft <= length + 1e-6 and guard < 200:
            guard += 1
            rect = _room_rect(p1, tangent, normal, along, spec.width_ft, spec.depth_ft, setback_ft)
            if rect.is_valid and rect.area > 0 and valid(rect):
                minx, miny, maxx, maxy = _axis_aligned_bbox(rect)
                placed.append(PlacedRoom(
                    type=spec.type, x=round(minx, 2), y=round(miny, 2),
                    w=round(maxx - minx, 2), h=round(maxy - miny, 2), rotation=0,
                    setting=spec.setting,
                ))
                placed_polys.append(rect)
                return True
            along += 2.0
    return False
