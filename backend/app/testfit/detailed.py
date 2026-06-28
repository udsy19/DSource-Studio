"""Detailed-mode generative space planning — Qbiq's "Detailed" program -> 3 test-fit variants.

The high-control counterpart to Concept mode. Instead of high-level dials, the user states
EXPLICIT room-type COUNTS and a placement preference per type, and the engine honours them:

  rooms: [{type, count, placement}]   type = any room catalog key (see catalog.py)
                                       placement in {window, core, flexible}

Type -> instance is defined by the room CATALOG (`catalog.py`): each key carries its footprint
(feet) and the placement instance type the packers + metrics understand. Many keys are size
variants of one instance type — e.g. office_exec/large/medium/small and the team offices all place
as `private_office`; every conference size places as `meeting_room`. Amenities (reception, kitchen,
wellness, copy/print, storage) carry their own instance types (enclosed support rooms, not seats).
The legacy keys office/meeting/huddle/phone_booth remain as aliases.

Placement:
  window   -> perimeter band (edge-march along the exterior wall, daylight)
  core     -> interior, biased toward the building core/centroid
  flexible -> engine decides (tried at the perimeter first, then interior)

After the requested rooms land, the remaining open area is filled with the workstation field
(desk_type/dims, as in Concept). HONESTY: we track placed-vs-requested per type and, when fewer
fit than asked, add a note — we never fabricate off-plate rooms.

Deterministic: same program -> same output. Returns the shared `AlternativesResult` dict shape.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
from shapely.geometry import Polygon, box

from ..floorplan.dxf_ingest import PlanModel
from .catalog import is_valid_key, lookup, room_spec
from .layout import (
    FurnitureInstance,
    TestFit,
    WorkstationSpec,
    _column_circles,
    _cores,
    _place_workstation_field,
    _placeable_region,
    _usable_boundary,
)
from .metrics import compute_metrics
from .payloads import plan_payload, testfit_payload
from .rooms import RoomSpec, place_perimeter_rooms
from .zones import place_interior_rooms


class RoomRequest(BaseModel):
    type: str  # any room catalog key or legacy alias (validated against catalog.py)
    count: int = Field(ge=0)
    placement: str = Field("flexible", pattern="^(window|core|flexible)$")

    @field_validator("type")
    @classmethod
    def _known_type(cls, v: str) -> str:
        if not is_valid_key(v):
            raise ValueError(f"unknown room type {v!r}")
        return v


class DetailedProgram(BaseModel):
    """Explicit per-type room counts + placement, plus the desk geometry dials from Concept."""

    rooms: list[RoomRequest] = Field(default_factory=list)
    desk_type: str = Field("workstations", pattern="^(workstations|benchings)$")
    desk_width_cm: int = Field(140, gt=0)
    desk_depth_cm: int = Field(70, gt=0)


def _workstation_spec(program: DetailedProgram) -> WorkstationSpec:
    """Desk geometry from cm dials (mirrors Concept): benchings widen the per-desk footprint."""
    return WorkstationSpec.from_desk_cm(
        program.desk_width_cm, program.desk_depth_cm, benching=program.desk_type == "benchings"
    )


def _requested_counts(program: DetailedProgram) -> dict[str, int]:
    """Sum requested counts per Detailed type (a type may appear more than once)."""
    counts: dict[str, int] = {}
    for r in program.rooms:
        counts[r.type] = counts.get(r.type, 0) + r.count
    return counts


def _place_rooms(
    program: DetailedProgram,
    usable: Polygon,
    cores: list[Polygon],
    columns: list,
    spec: WorkstationSpec,
    density_scale: float,
    pre_occupied: list[Polygon] | None = None,
    locked_by_instance: dict[str, int] | None = None,
):
    """Place every requested room honouring placement, then return (instances, occupied).

    Order: window rooms first (perimeter edge-march), then core rooms (interior packer), then
    flexible (perimeter, falling back to interior). `density_scale` < 1 drops a few rooms to make
    a sparser variant; > 1 is clamped to the request (never invents rooms beyond what was asked).
    `pre_occupied` (locked-room footprints) is reserved so new rooms avoid it; `locked_by_instance`
    reduces the request so a locked room counts toward its type's total instead of doubling it.
    """
    window: list[RoomSpec] = []
    core: list[RoomSpec] = []
    flexible: list[RoomSpec] = []
    for req in program.rooms:
        spec_room = room_spec(req.type)
        n = max(0, round(req.count * density_scale)) if density_scale < 1.0 else req.count
        bucket = {"window": window, "core": core, "flexible": flexible}[req.placement]
        bucket += [spec_room] * n

    # A locked room of a given instance type already satisfies one requested room of that type.
    remaining_locked = dict(locked_by_instance or {})
    window = _drop_locked(window, remaining_locked)
    core = _drop_locked(core, remaining_locked)
    flexible = _drop_locked(flexible, remaining_locked)

    placed_rooms = []
    occupied: list[Polygon] = list(pre_occupied or [])

    perimeter = place_perimeter_rooms(
        boundary_poly=usable, cores=cores, column_circles=columns, setback_ft=0.0,
        room_order=window, column_clearance_ft=spec.column_clearance_ft,
    )
    placed_rooms += perimeter
    occupied += [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in perimeter]

    if core:
        interior_region = _interior_region(usable, cores, columns, occupied)
        core_placed = place_interior_rooms(interior_region, occupied, core)
        placed_rooms += core_placed
        occupied += [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in core_placed]

    # Flexible: perimeter first, then interior for whatever didn't fit on the wall.
    if flexible:
        flex_peri = place_perimeter_rooms(
            boundary_poly=usable, cores=cores, column_circles=columns, setback_ft=0.0,
            room_order=flexible, column_clearance_ft=spec.column_clearance_ft,
            occupied_polys=occupied,
        )
        placed_rooms += flex_peri
        occupied += [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in flex_peri]
        leftover = _subtract_placed(flexible, flex_peri)
        if leftover:
            interior_region = _interior_region(usable, cores, columns, occupied)
            flex_int = place_interior_rooms(interior_region, occupied, leftover)
            placed_rooms += flex_int

    instances = [FurnitureInstance(r.type, r.x, r.y, r.w, r.h, r.rotation) for r in placed_rooms]
    return instances, occupied


def _interior_region(usable: Polygon, cores, columns, occupied: list[Polygon]):
    """Usable area net of core/columns/already-placed rooms — where interior rooms may land."""
    eps = 0.05
    region = usable
    for c in cores:
        region = region.difference(c.buffer(eps))
    for col in columns:
        region = region.difference(col.buffer(eps))
    for op in occupied:
        region = region.difference(op.buffer(eps))
    return region


def _drop_locked(bucket: list[RoomSpec], remaining_locked: dict[str, int]) -> list[RoomSpec]:
    """Drop specs already covered by a locked room of the same instance type (mutates the counter
    so coverage is shared across window/core/flexible buckets, never double-spent)."""
    out: list[RoomSpec] = []
    for spec in bucket:
        if remaining_locked.get(spec.type, 0) > 0:
            remaining_locked[spec.type] -= 1
        else:
            out.append(spec)
    return out


def _subtract_placed(requested: list[RoomSpec], placed) -> list[RoomSpec]:
    """Return the requested RoomSpecs not yet satisfied by `placed` (by instance type)."""
    placed_counts: dict[str, int] = {}
    for r in placed:
        placed_counts[r.type] = placed_counts.get(r.type, 0) + 1
    leftover: list[RoomSpec] = []
    for spec in requested:
        if placed_counts.get(spec.type, 0) > 0:
            placed_counts[spec.type] -= 1
        else:
            leftover.append(spec)
    return leftover


def _placed_by_catalog_key(program, placed, density_scale: float) -> dict[str, int]:
    """Attribute placed rooms back to the catalog keys that asked for them — for honest reporting.

    Several catalog keys share one instance type (e.g. office_exec and office_small are both
    `private_office`), so the packers' instance-type tag can't tell them apart. We count placements
    by instance type, then walk the requested keys (in request order) of each instance type and
    assign placements greedily up to each key's (density-scaled) requested count.
    """
    placed_by_instance: dict[str, int] = {}
    for r in placed:
        placed_by_instance[r.type] = placed_by_instance.get(r.type, 0) + 1

    out: dict[str, int] = {}
    for req in program.rooms:
        inst = lookup(req.type).instance_type
        want = max(0, round(req.count * density_scale)) if density_scale < 1.0 else req.count
        give = min(want, placed_by_instance.get(inst, 0))
        out[req.type] = out.get(req.type, 0) + give
        placed_by_instance[inst] -= give
    return out


def _build_testfit(
    plan: PlanModel, program: DetailedProgram, spec: WorkstationSpec, density_scale: float,
    locked: list[FurnitureInstance] | None = None,
) -> TestFit:
    """One Detailed test-fit: explicit rooms (honouring placement) + a workstation field.

    `locked` instances (pinned from a prior version) are kept exactly: their footprints are
    reserved, they count toward their type's requested total, and they appear in the output."""
    usable = _usable_boundary(plan, spec)
    requested = _requested_counts(program)
    if usable.is_empty or usable.area <= 0:
        return TestFit(workstation_count=0, placeable_area_sf=0.0,
                       notes=["No usable area after perimeter setback."])

    locked = locked or []
    locked_rooms = [i for i in locked if i.type != "workstation"]
    locked_boxes = [box(i.x, i.y, i.x + i.w, i.y + i.h) for i in locked]
    locked_by_instance: dict[str, int] = {}
    for i in locked_rooms:
        locked_by_instance[i.type] = locked_by_instance.get(i.type, 0) + 1

    cores = _cores(plan)
    columns = _column_circles(plan, spec)
    room_instances, occupied = _place_rooms(
        program, usable, cores, columns, spec, density_scale,
        pre_occupied=locked_boxes, locked_by_instance=locked_by_instance,
    )
    placed_by_type = _placed_by_catalog_key(program, locked_rooms + room_instances, density_scale)

    region = _interior_region(usable, cores, columns, occupied)
    workstations = _place_workstation_field(region, spec)

    instances = locked + room_instances + workstations
    office_count = sum(1 for i in instances if i.type == "private_office")
    meeting_count = sum(1 for i in instances if i.type == "meeting_room")
    # Both huddles (collaboration) and booths (phone_booth) are enclosed clusters, not desks.
    collab_count = sum(1 for i in instances if i.type in ("collaboration", "phone_booth"))
    placeable_sf = round(_placeable_region(plan, spec).area, 1)

    notes = _honesty_notes(requested, placed_by_type)
    return TestFit(
        workstation_count=len(workstations),
        office_count=office_count,
        meeting_count=meeting_count,
        collab_count=collab_count,
        instances=instances,
        placeable_area_sf=placeable_sf,
        sf_per_workstation=round(placeable_sf / len(workstations), 1) if workstations else None,
        program={"requested": requested, "placed": placed_by_type},
        notes=notes,
    )


def _honesty_notes(requested: dict[str, int], placed: dict[str, int]) -> list[str]:
    notes = [
        "Detailed test-fit: explicit requested room counts placed by stated preference "
        "(window=perimeter band, core=interior), then the open area filled with workstations.",
        "Procedural placement + Shapely constraint filter — every room is contained, clear of "
        "core/columns, and non-overlapping; the open area is broken by a circulation spine and "
        "cross-aisles. Deferred: door swings, code-exact egress/ADA compliance.",
    ]
    shortfalls = [
        f"{t} {placed.get(t, 0)}/{requested[t]}"
        for t in requested
        if placed.get(t, 0) < requested[t]
    ]
    if shortfalls:
        notes.append(
            "Placed fewer than requested (the plate ran out of clear space): "
            + ", ".join(shortfalls) + ". No off-plate rooms were invented."
        )
    return notes


# Density scales per variant: A as requested, B sparser open plan, C denser. Rooms are only
# DROPPED (scale < 1), never added beyond the request — the user's counts are a ceiling.
_VARIANTS: list[tuple[str, float, float]] = [
    ("A", 1.0, 1.0),   # rooms as requested, desks as given
    ("B", 1.0, 0.85),  # same rooms, tighter desks -> denser open plan
    ("C", 0.7, 1.15),  # fewer rooms, looser desks -> more open area
]


def _locked_instances(locked: list[dict] | None) -> list[FurnitureInstance]:
    """Parse pinned instances (from a prior version's payload) into FurnitureInstances."""
    return [
        FurnitureInstance(
            type=i["type"], x=float(i["x"]), y=float(i["y"]),
            w=float(i["w"]), h=float(i["h"]), rotation=int(i.get("rotation", 0)),
        )
        for i in (locked or [])
    ]


def generate_from_detailed(
    plan: PlanModel, program: DetailedProgram, n: int = 3, locked: list[dict] | None = None
) -> dict:
    """Place the explicit requested rooms honouring placement, then return `n` scored variants.

    Variants vary workstation density and (for C) how many of the requested rooms are kept, so the
    three options trade enclosed-vs-open while never exceeding the requested room counts. `locked`
    pins instances from a prior version — kept exactly while the rest re-places (the iterate loop).
    Same `AlternativesResult` dict shape as /api/generate and /api/testfit/alternatives.
    """
    spec = _workstation_spec(program)
    pinned = _locked_instances(locked)
    alternatives = []
    for alt_id, room_scale, desk_scale in _VARIANTS[:n]:
        variant_spec = WorkstationSpec(
            width_ft=round(spec.width_ft * desk_scale, 3),
            depth_ft=round(spec.depth_ft * desk_scale, 3),
            aisle_ft=spec.aisle_ft,
            perimeter_setback_ft=spec.perimeter_setback_ft,
            column_clearance_ft=spec.column_clearance_ft,
        )
        fit = _build_testfit(plan, program, variant_spec, room_scale, locked=pinned)
        alternatives.append({
            "id": alt_id,
            "testfit": testfit_payload(fit),
            "metrics": compute_metrics(plan, fit),
        })
    return {"plan": plan_payload(plan), "alternatives": alternatives}
