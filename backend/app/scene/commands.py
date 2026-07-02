"""Editor operations as Commands + the per-design stack (invariant 3).

Every mutation of a scene is a Command with a do/undo pair, executed through a `CommandStack` that
gives undo/redo and an audit trail. A command whose result violates a scene invariant is rolled
back and the `SceneError` surfaced — so invariant 2 (enclosed zones need a door) is enforced by
construction, not by scattered UI checks.

Versioning: generated alternatives are IMMUTABLE. `EditedDesign.fork` deep-copies an alternative's
scene and gives it its own stack (fork-to-edit), so editing never mutates the base alternative.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from shapely.geometry import Polygon
from shapely.ops import unary_union

from .geometry import clamp_local_into_zone
from .model import (
    Door,
    Partition,
    Placement,
    PlacementItem,
    Plate,
    Scene,
    SceneError,
    Transform,
    Zone,
    door_by_id,
    partition_by_id,
    placement_by_id,
    validate_invariants,
    zone_by_id,
)


@runtime_checkable
class Command(Protocol):
    description: str

    def do(self, scene: Scene) -> None: ...

    def undo(self, scene: Scene) -> None: ...


class CommandStack:
    """Per-design do/undo/redo stack. `execute` runs a command and rolls it back if the result is
    invalid, so the scene never lands in a state that breaks an invariant."""

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def execute(self, command: Command) -> Scene:
        command.do(self.scene)
        try:
            validate_invariants(self.scene)
        except SceneError:
            command.undo(self.scene)
            raise
        self._undo.append(command)
        self._redo.clear()
        return self.scene

    def undo(self) -> Scene:
        if not self._undo:
            raise SceneError("nothing_to_undo", "The command stack is empty.")
        command = self._undo.pop()
        command.undo(self.scene)
        self._redo.append(command)
        return self.scene

    def redo(self) -> Scene:
        if not self._redo:
            raise SceneError("nothing_to_redo", "Nothing has been undone.")
        command = self._redo.pop()
        command.do(self.scene)
        self._undo.append(command)
        return self.scene

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def history(self) -> list[str]:
        """The audit trail: descriptions of the applied (not-undone) commands, oldest first."""
        return [c.description for c in self._undo]


@dataclass
class EditedDesign:
    """A forked, editable copy of a generated alternative — its own scene + command stack.

    The base alternative stays immutable: `fork` deep-copies its scene, so edits never touch it.
    """

    base_alternative_id: str
    scene: Scene
    stack: CommandStack

    @classmethod
    def fork(cls, base_alternative_id: str, base_scene: Scene) -> "EditedDesign":
        scene = copy.deepcopy(base_scene)
        return cls(base_alternative_id, scene, CommandStack(scene))


# ── item helpers ────────────────────────────────────────────────────────────
def _item(placement: Placement, plate_item_ref: int) -> PlacementItem:
    for it in placement.items:
        if it.plate_item_ref == plate_item_ref:
            return it
    raise SceneError("unknown_item", f"No item {plate_item_ref} in placement {placement.id!r}.")


def _local_pose(placement: Placement, plate: Plate, item: PlacementItem) -> tuple[float, float, float]:
    if item.transform_override is not None:
        t = item.transform_override
        return t.x, t.y, t.rotation
    base = plate.items[item.plate_item_ref]
    return base.dx, base.dy, base.rotation


def _zone_placement(scene: Scene, zone_id: str) -> Placement | None:
    for p in scene.placements:
        if p.zone_id == zone_id:
            return p
    return None


def _snap_45(angle: float) -> float:
    return float(round(angle / 45.0) * 45 % 360)


# ── commands ──────────────────────────────────────────────────────────────
@dataclass
class ChangeRoomType:
    zone_id: str
    new_type: str
    _old: str = field(default="", init=False)

    @property
    def description(self) -> str:
        return f"change room type of {self.zone_id} to {self.new_type}"

    def do(self, scene: Scene) -> None:
        zone = zone_by_id(scene, self.zone_id)
        self._old = zone.room_type
        zone.room_type = self.new_type

    def undo(self, scene: Scene) -> None:
        zone_by_id(scene, self.zone_id).room_type = self._old


@dataclass
class SwapPlate:
    placement_id: str
    plate: Plate
    _old_plate_id: str = field(default="", init=False)
    _old_items: list[PlacementItem] = field(default_factory=list, init=False)
    _added_plate: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return f"swap plate of {self.placement_id} to {self.plate.id}"

    def do(self, scene: Scene) -> None:
        placement = placement_by_id(scene, self.placement_id)
        self._old_plate_id = placement.plate_id
        self._old_items = placement.items
        self._added_plate = self.plate.id not in scene.plates
        scene.plates[self.plate.id] = self.plate
        placement.plate_id = self.plate.id
        placement.items = [PlacementItem(plate_item_ref=i) for i in range(len(self.plate.items))]

    def undo(self, scene: Scene) -> None:
        placement = placement_by_id(scene, self.placement_id)
        placement.plate_id = self._old_plate_id
        placement.items = self._old_items
        if self._added_plate:
            scene.plates.pop(self.plate.id, None)


@dataclass
class SetOpenEnclosed:
    """enclosed->open removes the zone's generated partitions (+ their doors); open->enclosed rings
    the zone with partitions and adds a door (so the enclosed-zone invariant holds by construction).
    An optional `plate` swaps the zone's placement to an open/enclosed plate in the same command."""

    zone_id: str
    enclosed: bool
    plate: Plate | None = None
    _old_enclosed: bool = field(default=False, init=False)
    _old_boundary: list[str] = field(default_factory=list, init=False)
    _removed_partitions: list[Partition] = field(default_factory=list, init=False)
    _removed_doors: list[Door] = field(default_factory=list, init=False)
    _added_partition_ids: list[str] = field(default_factory=list, init=False)
    _added_door_id: str | None = field(default=None, init=False)
    _swap: SwapPlate | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return f"set {self.zone_id} {'enclosed' if self.enclosed else 'open'}"

    def do(self, scene: Scene) -> None:
        zone = zone_by_id(scene, self.zone_id)
        self._old_enclosed = zone.enclosed
        self._old_boundary = list(zone.boundary_partition_ids)
        if self.enclosed:
            self._enclose(scene, zone)
        else:
            self._open(scene, zone)
        placement = _zone_placement(scene, zone.id)
        if self.plate is not None and placement is not None:
            self._swap = SwapPlate(placement.id, self.plate)
            self._swap.do(scene)

    def _enclose(self, scene: Scene, zone: Zone) -> None:
        ring = list(zone.polygon)
        if ring[0] != ring[-1]:
            ring = ring + [ring[0]]
        partitions: list[Partition] = []
        for i in range(len(ring) - 1):
            pid = f"{zone.id}-p{i}"
            partitions.append(Partition(id=pid, segment=(ring[i], ring[i + 1])))
        scene.partitions.extend(partitions)
        self._added_partition_ids = [p.id for p in partitions]
        zone.boundary_partition_ids = list(self._added_partition_ids)
        # a door on the longest partition so the enclosed-zone invariant holds by construction.
        host = max(partitions, key=lambda p: p.length())
        width = round(min(3.0, host.length() * 0.8), 2)
        door = Door(id=f"{zone.id}-d0", host_partition_id=host.id,
                    offset=round((host.length() - width) / 2, 2), width=width)
        scene.doors.append(door)
        self._added_door_id = door.id
        zone.enclosed = True

    def _open(self, scene: Scene, zone: Zone) -> None:
        remove_ids = set(zone.boundary_partition_ids)
        self._removed_partitions = [p for p in scene.partitions if p.id in remove_ids]
        self._removed_doors = [d for d in scene.doors if d.host_partition_id in remove_ids]
        scene.partitions = [p for p in scene.partitions if p.id not in remove_ids]
        removed_door_ids = {d.id for d in self._removed_doors}
        scene.doors = [d for d in scene.doors if d.id not in removed_door_ids]
        zone.boundary_partition_ids = []
        zone.enclosed = False

    def undo(self, scene: Scene) -> None:
        if self._swap is not None:
            self._swap.undo(scene)
            self._swap = None
        zone = zone_by_id(scene, self.zone_id)
        if self.enclosed:
            added = set(self._added_partition_ids)
            scene.partitions = [p for p in scene.partitions if p.id not in added]
            scene.doors = [d for d in scene.doors if d.id != self._added_door_id]
            self._added_partition_ids = []
            self._added_door_id = None
        else:
            scene.partitions.extend(self._removed_partitions)
            scene.doors.extend(self._removed_doors)
            self._removed_partitions = []
            self._removed_doors = []
        zone.enclosed = self._old_enclosed
        zone.boundary_partition_ids = list(self._old_boundary)


@dataclass
class MergeZones:
    """Delete the partition(s) shared by two zones, union their polygons into `a`, drop `b`, and
    re-point `b`'s placements at the merged zone. An optional `merged_plate` re-fits `a`'s plate."""

    a_id: str
    b_id: str
    merged_plate: Plate | None = None
    _b_index: int = field(default=-1, init=False)
    _b_zone: Zone | None = field(default=None, init=False)
    _a_before: Zone | None = field(default=None, init=False)
    _removed_partitions: list[Partition] = field(default_factory=list, init=False)
    _removed_doors: list[Door] = field(default_factory=list, init=False)
    _reassigned: list[tuple[str, str]] = field(default_factory=list, init=False)
    _swap: SwapPlate | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return f"merge zone {self.b_id} into {self.a_id}"

    def do(self, scene: Scene) -> None:
        za = zone_by_id(scene, self.a_id)
        zb = zone_by_id(scene, self.b_id)
        self._a_before = copy.deepcopy(za)
        self._b_index = scene.zones.index(zb)
        self._b_zone = zb

        shared = set(za.boundary_partition_ids) & set(zb.boundary_partition_ids)
        self._removed_partitions = [p for p in scene.partitions if p.id in shared]
        self._removed_doors = [d for d in scene.doors if d.host_partition_id in shared]
        removed_door_ids = {d.id for d in self._removed_doors}
        scene.partitions = [p for p in scene.partitions if p.id not in shared]
        scene.doors = [d for d in scene.doors if d.id not in removed_door_ids]

        merged = unary_union([Polygon(za.polygon), Polygon(zb.polygon)])
        poly = merged if merged.geom_type == "Polygon" else merged.convex_hull
        za.polygon = [(round(x, 3), round(y, 3)) for x, y in poly.exterior.coords]
        if Polygon(zb.polygon).area > Polygon(self._a_before.polygon).area:
            za.room_type = zb.room_type
        za.enclosed = za.enclosed or zb.enclosed
        za.boundary_partition_ids = [
            pid for pid in (za.boundary_partition_ids + zb.boundary_partition_ids)
            if pid not in shared
        ]

        for placement in scene.placements:
            if placement.zone_id == zb.id:
                self._reassigned.append((placement.id, placement.zone_id))
                placement.zone_id = za.id
        scene.zones.remove(zb)

        if self.merged_plate is not None:
            target = _zone_placement(scene, za.id)
            if target is not None:
                self._swap = SwapPlate(target.id, self.merged_plate)
                self._swap.do(scene)

    def undo(self, scene: Scene) -> None:
        if self._swap is not None:
            self._swap.undo(scene)
            self._swap = None
        za = zone_by_id(scene, self.a_id)
        before = self._a_before
        za.polygon = before.polygon
        za.room_type = before.room_type
        za.enclosed = before.enclosed
        za.boundary_partition_ids = before.boundary_partition_ids
        scene.zones.insert(self._b_index, self._b_zone)
        for placement_id, old_zone_id in self._reassigned:
            placement_by_id(scene, placement_id).zone_id = old_zone_id
        self._reassigned = []
        scene.partitions.extend(self._removed_partitions)
        scene.doors.extend(self._removed_doors)
        self._removed_partitions = []
        self._removed_doors = []


@dataclass
class MoveItem:
    placement_id: str
    item_ref: int
    dx: float
    dy: float
    _old_override: Transform | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return f"move item {self.item_ref} of {self.placement_id}"

    def do(self, scene: Scene) -> None:
        placement = placement_by_id(scene, self.placement_id)
        plate = scene.plates[placement.plate_id]
        zone = zone_by_id(scene, placement.zone_id)
        item = _item(placement, self.item_ref)
        self._old_override = item.transform_override
        cx, cy, rot = _local_pose(placement, plate, item)
        ndx, ndy = clamp_local_into_zone(zone, plate, self.item_ref, cx + self.dx, cy + self.dy, rot)
        item.transform_override = Transform(ndx, ndy, rot)

    def undo(self, scene: Scene) -> None:
        _item(placement_by_id(scene, self.placement_id), self.item_ref).transform_override = self._old_override


@dataclass
class RotateItem:
    placement_id: str
    item_ref: int
    delta: float
    _old_override: Transform | None = field(default=None, init=False)

    @property
    def description(self) -> str:
        return f"rotate item {self.item_ref} of {self.placement_id}"

    def do(self, scene: Scene) -> None:
        placement = placement_by_id(scene, self.placement_id)
        plate = scene.plates[placement.plate_id]
        zone = zone_by_id(scene, placement.zone_id)
        item = _item(placement, self.item_ref)
        self._old_override = item.transform_override
        cx, cy, rot = _local_pose(placement, plate, item)
        new_rot = _snap_45(rot + self.delta)
        ndx, ndy = clamp_local_into_zone(zone, plate, self.item_ref, cx, cy, new_rot)
        item.transform_override = Transform(ndx, ndy, new_rot)

    def undo(self, scene: Scene) -> None:
        _item(placement_by_id(scene, self.placement_id), self.item_ref).transform_override = self._old_override


@dataclass
class DeleteItem:
    placement_id: str
    item_ref: int
    _old_deleted: bool = field(default=False, init=False)

    @property
    def description(self) -> str:
        return f"delete item {self.item_ref} of {self.placement_id}"

    def do(self, scene: Scene) -> None:
        item = _item(placement_by_id(scene, self.placement_id), self.item_ref)
        self._old_deleted = item.deleted
        item.deleted = True

    def undo(self, scene: Scene) -> None:
        _item(placement_by_id(scene, self.placement_id), self.item_ref).deleted = self._old_deleted


@dataclass
class EditDoor:
    """Slide the door along its host segment (`offset`, clamped to the segment) and/or flip its swing."""

    door_id: str
    offset: float | None = None
    flip_swing: bool = False
    _old_offset: float = field(default=0.0, init=False)
    _old_swing: str = field(default="left", init=False)

    @property
    def description(self) -> str:
        return f"edit door {self.door_id}"

    def do(self, scene: Scene) -> None:
        door = door_by_id(scene, self.door_id)
        self._old_offset = door.offset
        self._old_swing = door.swing
        if self.offset is not None:
            host = partition_by_id(scene, door.host_partition_id)
            door.offset = round(min(max(self.offset, 0.0), max(host.length() - door.width, 0.0)), 3)
        if self.flip_swing:
            door.swing = "right" if door.swing == "left" else "left"

    def undo(self, scene: Scene) -> None:
        door = door_by_id(scene, self.door_id)
        door.offset = self._old_offset
        door.swing = self._old_swing
