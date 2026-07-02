"""Adapters — build a scene from an existing generated test-fit so the model isn't orphaned.

`scene_from_generated(plan, instances, program)` maps a testfit `PlanModel` + `FurnitureInstance[]`
into a Scene: the plan's shell/core/columns become the immutable underlay; enclosed room boxes
become enclosed zones (ringed with generated partitions + a door); the open workstation field
becomes an open zone; and the SKU-tagged furniture placed inside each room is distilled into a
per-zone plate + placement. Minimal on purpose — wiring into the routers/UI is a later step.
"""

from __future__ import annotations

from collections import Counter

from shapely.geometry import Polygon

from ..floorplan.dxf_ingest import PlanModel
from ..testfit.layout import FurnitureInstance
from .model import (
    Door,
    Partition,
    Placement,
    PlacementItem,
    Plate,
    PlateItem,
    Program,
    ProgramLine,
    Scene,
    Transform,
    Underlay,
    Zone,
)

_ROOM_TYPES = ("private_office", "meeting_room", "collaboration")
_ENCLOSED_TYPES = ("private_office", "meeting_room")
_SEAT_CATEGORIES = ("desk", "workstation", "chair", "stool")
# testfit target keys per room type, so program targets carry through to the scoreboard.
_TARGET_KEY = {
    "private_office": "target_offices",
    "meeting_room": "target_meetings",
    "collaboration": "target_collaboration",
}


def _rect(x: float, y: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def _plate_from(plate_id: str, room_type: str, x: float, y: float, w: float, h: float,
                items: list[FurnitureInstance]) -> Plate:
    plate_items = [
        PlateItem(category=i.type, model=i.model,
                  dx=round(i.x - x, 2), dy=round(i.y - y, 2), w=i.w, h=i.h,
                  rotation=float(i.rotation) % 360)
        for i in items
    ]
    capacity = sum(1 for i in items if i.type in _SEAT_CATEGORIES)
    return Plate(id=plate_id, room_type=room_type, sqft=round(w * h, 1),
                 width_ft=round(w, 2), height_ft=round(h, 2), capacity=capacity, items=plate_items)


def _contained(item: FurnitureInstance, box: Polygon) -> bool:
    return box.contains(Polygon(_rect(item.x, item.y, item.w, item.h)).centroid)


def _program_ref(scene_zones: list[Zone], program: dict | None) -> Program:
    counts = Counter(z.room_type for z in scene_zones)
    if program is None:
        lines = [ProgramLine(room_type=rt, target=counts[rt]) for rt in sorted(counts)]
        return Program(lines=lines)
    lines = [
        ProgramLine(room_type=rt, target=int(program.get(_TARGET_KEY[rt], 0)))
        for rt in _ROOM_TYPES
    ]
    return Program(lines=lines, headcount=program.get("headcount"),
                   density_rsf_per_person=program.get("density_rsf_per_person"))


def scene_from_generated(
    plan: PlanModel, instances: list[FurnitureInstance], program: dict | None = None
) -> Scene:
    """Build an editable Scene from a generated test-fit (plan + placed instances)."""
    underlay = Underlay(
        boundary=tuple((x, y) for x, y in plan.boundary),
        cores=tuple(tuple((x, y) for x, y in core) for core in plan.cores),
        columns=tuple((x, y) for x, y in plan.columns),
    )

    room_boxes = [i for i in instances if i.type in _ROOM_TYPES and not i.slotted]
    workstations = [i for i in instances if i.type == "workstation" and not i.slotted]
    slotted = [i for i in instances if i.slotted]

    scene = Scene(underlay=underlay)
    for n, room in enumerate(room_boxes):
        zone_id = f"Z{n}"
        polygon = _rect(room.x, room.y, room.w, room.h)
        enclosed = room.type in _ENCLOSED_TYPES
        zone = Zone(id=zone_id, polygon=polygon, room_type=room.type,
                    enclosed=enclosed, program_line_ref=room.type)
        scene.zones.append(zone)

        box = Polygon(polygon)
        inside = [i for i in slotted if _contained(i, box)]
        plate = _plate_from(f"{zone_id}-plate", room.type, room.x, room.y, room.w, room.h, inside)
        scene.plates[plate.id] = plate
        scene.placements.append(Placement(
            id=f"{zone_id}-pl", zone_id=zone_id, plate_id=plate.id,
            transform=Transform(x=room.x, y=room.y),
            items=[PlacementItem(plate_item_ref=k) for k in range(len(plate.items))],
        ))

        if enclosed:
            ring = polygon + [polygon[0]]
            partitions = [
                Partition(id=f"{zone_id}-p{i}", segment=(ring[i], ring[i + 1]))
                for i in range(len(ring) - 1)
            ]
            scene.partitions.extend(partitions)
            zone.boundary_partition_ids = [p.id for p in partitions]
            host = max(partitions, key=lambda p: p.length())
            width = round(min(3.0, host.length() * 0.8), 2)
            scene.doors.append(Door(
                id=f"{zone_id}-d0", host_partition_id=host.id,
                offset=round((host.length() - width) / 2, 2), width=width,
            ))

    if workstations:
        zone_id = f"Z{len(room_boxes)}"
        minx = min(i.x for i in workstations)
        miny = min(i.y for i in workstations)
        maxx = max(i.x + i.w for i in workstations)
        maxy = max(i.y + i.h for i in workstations)
        polygon = _rect(minx, miny, maxx - minx, maxy - miny)
        scene.zones.append(Zone(id=zone_id, polygon=polygon, room_type="open",
                                enclosed=False, program_line_ref="open"))
        plate = _plate_from(f"{zone_id}-plate", "open", minx, miny, maxx - minx, maxy - miny, workstations)
        scene.plates[plate.id] = plate
        scene.placements.append(Placement(
            id=f"{zone_id}-pl", zone_id=zone_id, plate_id=plate.id,
            transform=Transform(x=minx, y=miny),
            items=[PlacementItem(plate_item_ref=k) for k in range(len(plate.items))],
        ))

    scene.program_ref = _program_ref(scene.zones, program)
    return scene
