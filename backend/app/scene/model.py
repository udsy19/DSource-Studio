"""The semantic scene model — the editor's foundation.

A qbiq-style editor edits a *scene*, not lines. The base building (DXF-ingested shell/core/base
doors) is a DISPLAY-ONLY `Underlay` that is never mutated; only the test-fit-GENERATED partitions,
zones, doors and furniture placements are editable, and every edit is a high-level operation on
these entities (see `commands.py`). This module defines the entity types and the invariants that
hold structurally rather than being re-checked by every caller.

Three invariants live here (not in the UI):
  1. The underlay is IMMUTABLE — `Underlay` is a frozen dataclass of tuples, so it exposes no
     mutation methods and any assignment raises. Inedibility is a type/shape fact, not a guard.
  2. Every enclosed zone has >=1 door on its boundary partitions, and every door hosts a GENERATED
     partition. `validate_invariants` rejects any scene that breaks this with a structured
     `SceneError` — commands roll back and surface the reason (see CommandStack).
  3. (enforced in `commands.py`) every mutation is a Command with a do/undo pair on a stack.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

Point2 = tuple[float, float]


class SceneError(Exception):
    """A rejected mutation. Carries a machine `code` + human `message` so the UI can show why."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── the immutable base building ─────────────────────────────────────────────
@dataclass(frozen=True)
class BaseDoor:
    """A door from the base drawing — display-only, part of the underlay, never edited."""

    x: float
    y: float
    width: float
    rotation: float


@dataclass(frozen=True)
class Underlay:
    """Shell walls, service core(s), structural columns and base doors from DXF ingest.

    Frozen + tuple-typed on purpose: there is no way to mutate it, so invariant 1 (the underlay is
    display-only) is structural. Built from a `PlanModel` by `adapters.scene_from_generated`.
    """

    boundary: tuple[Point2, ...]
    cores: tuple[tuple[Point2, ...], ...] = ()
    columns: tuple[Point2, ...] = ()
    base_doors: tuple[BaseDoor, ...] = ()


# ── editable, generated entities ────────────────────────────────────────────
@dataclass
class Transform:
    """A pose relative to a plate/zone origin: translation + rotation (degrees, about the centre)."""

    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class Partition:
    """A generated interior wall segment. Only generated partitions exist in a scene (base walls are
    underlay), so these are exactly the editable walls — `generated` is always True and documents it."""

    id: str
    segment: tuple[Point2, Point2]
    generated: bool = True

    def length(self) -> float:
        (x1, y1), (x2, y2) = self.segment
        return math.hypot(x2 - x1, y2 - y1)


@dataclass
class Door:
    """A parametric door hosted on a GENERATED partition (never on the underlay).

    `offset` slides the leaf along the host segment from its first point; `swing` (left|right) is
    the hinge side. Correct by construction because it can only reference `scene.partitions`.
    """

    id: str
    host_partition_id: str
    offset: float
    width: float
    swing: str = "left"


@dataclass
class Zone:
    """A programmed area. `enclosed` zones are walled (their `boundary_partition_ids` name the
    generated partitions that ring them and must carry a door); open zones have none."""

    id: str
    polygon: list[Point2]
    room_type: str
    enclosed: bool = False
    program_line_ref: str | None = None
    boundary_partition_ids: list[str] = field(default_factory=list)


# ── the plate library contract (built by a sibling agent) ───────────────────
# The scene REFERENCES plates by id; the plate library itself is a separate deliverable. These
# lightweight types are the contract the scene depends on — the item shape the task specifies
# ({category, model, dx, dy, w, h, rotation}) plus room_type/capacity for the scoreboard. Kept here
# (not reusing testfit.Setting) because this is the editor's interface boundary, carrying capacity +
# room_type naming Setting does not. The referenced plates are embedded in the Scene so
# metrics/export stay PURE functions of the scene alone.
@dataclass
class PlateItem:
    category: str
    model: str | None
    dx: float
    dy: float
    w: float
    h: float
    rotation: float = 0.0


@dataclass
class Plate:
    id: str
    room_type: str
    sqft: float
    width_ft: float
    height_ft: float
    capacity: int
    items: list[PlateItem] = field(default_factory=list)


@dataclass
class PlacementItem:
    """One item of a placed plate. `transform_override` (when set) fully re-poses the item relative
    to the plate origin, replacing the plate item's dx/dy/rotation; `deleted` hides it."""

    plate_item_ref: int
    transform_override: Transform | None = None
    deleted: bool = False


@dataclass
class Placement:
    """A plate instanced into a zone at `transform` (its origin in world feet)."""

    id: str
    zone_id: str
    plate_id: str
    transform: Transform
    items: list[PlacementItem] = field(default_factory=list)


# ── the program contract (the scoreboard target) ────────────────────────────
@dataclass
class ProgramLine:
    room_type: str
    target: int
    label: str | None = None


@dataclass
class Program:
    lines: list[ProgramLine] = field(default_factory=list)
    headcount: int | None = None
    density_rsf_per_person: float | None = None


@dataclass
class Scene:
    underlay: Underlay
    zones: list[Zone] = field(default_factory=list)
    partitions: list[Partition] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=list)
    plates: dict[str, Plate] = field(default_factory=dict)
    program_ref: Program = field(default_factory=Program)


# ── lookups (raise SceneError so commands fail loud, never silently no-op) ───
def zone_by_id(scene: Scene, zone_id: str) -> Zone:
    for z in scene.zones:
        if z.id == zone_id:
            return z
    raise SceneError("unknown_zone", f"No zone {zone_id!r} in scene.")


def partition_by_id(scene: Scene, partition_id: str) -> Partition:
    for p in scene.partitions:
        if p.id == partition_id:
            return p
    raise SceneError("unknown_partition", f"No partition {partition_id!r} in scene.")


def door_by_id(scene: Scene, door_id: str) -> Door:
    for d in scene.doors:
        if d.id == door_id:
            return d
    raise SceneError("unknown_door", f"No door {door_id!r} in scene.")


def placement_by_id(scene: Scene, placement_id: str) -> Placement:
    for p in scene.placements:
        if p.id == placement_id:
            return p
    raise SceneError("unknown_placement", f"No placement {placement_id!r} in scene.")


# ── invariant enforcement (invariant 2) ─────────────────────────────────────
def validate_invariants(scene: Scene) -> None:
    """Raise SceneError if the scene violates a structural invariant. Called after every command;
    a command whose result is invalid is rolled back and the error surfaced (see CommandStack)."""
    partition_ids = {p.id for p in scene.partitions}

    for door in scene.doors:
        if door.host_partition_id not in partition_ids:
            raise SceneError(
                "door_without_host",
                f"Door {door.id!r} hosts partition {door.host_partition_id!r}, which is not a "
                "generated partition (doors may only sit on generated partitions).",
            )

    doored_partitions = {d.host_partition_id for d in scene.doors}
    for zone in scene.zones:
        if not zone.enclosed:
            continue
        if not (set(zone.boundary_partition_ids) & doored_partitions):
            raise SceneError(
                "enclosed_zone_without_door",
                f"Zone {zone.id!r} ({zone.room_type}) is enclosed but has no door on its boundary "
                "partitions — every enclosed zone needs at least one door.",
            )
