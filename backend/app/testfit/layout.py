"""Generative test-fit engine v2 — MIXED layout (the AI moat).

v1 placed an open-plan workstation field only. v2 produces a richer mix that resembles a real
test-fit: enclosed PRIVATE OFFICES and MEETING ROOMS packed against the exterior wall, open
COLLABORATION lounges in the interior, and the open-plan WORKSTATION field filling whatever
interior is left.

Method (deliberate, per the Phase-0 research): everything here is **procedural placement +
geometric constraint filtering** (Shapely), the method WeWork validated against ~13,000 real
offices. It is fast, deterministic, and human-editable. We do NOT use OR-Tools CP-SAT — for a
plate with a handful of rooms the greedy edge-march / grid scan is fast (<<1s) and reliable;
CP-SAT optimal packing is a future upgrade, not required for a valid starting layout.

Placement ORDER matters and is the key invariant:
  1. Place perimeter rooms (offices + meeting rooms) against the exterior wall.
  2. Place collaboration lounges in the interior.
  3. SUBTRACT every room/lounge footprint from the placeable region, THEN run the workstation
     grid on what's left.
This guarantees ALL instances (workstations + rooms + lounges) are mutually non-overlapping.

Hard constraints (enforced geometrically with Shapely), for every instance type:
  * containment   — fully inside the usable boundary (minus perimeter setback)
  * core avoidance — clear of the service core(s)
  * column clearance — clear of structural columns
  * no overlap    — every pair of instances has ~zero area intersection

Program: counts are driven by headcount (given, or derived from usable area at ~175 rsf/person)
and a zone mix (~40% workstations / 10% private offices / 20% meeting / 15% collaboration).
These are reasonable deterministic heuristics, not an optimizer.

The open area is broken by a circulation spine + cross-aisles into legible neighborhoods.
Deferred (honest): door swings, code-exact egress/ADA compliance beyond aisle/corridor width
and setback, acoustic/adjacency rules, skewed (non-orthogonal) walls.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon, box
from shapely.prepared import prep

from ..floorplan.dxf_ingest import PlanModel
from .rooms import PRIVATE_OFFICE, MEETING_ROOM, RoomSpec, place_perimeter_rooms
from .settings import SLOT_CATS, SLOTTABLE_TYPES, Setting, load_settings, pick_settings
from .zones import COLLAB_SIZE_FT, place_collaboration_zones, place_interior_rooms


_CM_PER_FT = 30.48
# Access/chair depth BEHIND the desk worktop. A 70 cm worktop is not a workstation — the seated
# occupant + chair pull-out needs this much again, so the footprint that gets placed/counted is the
# worktop depth plus this zone. Without it desks pack ~2x too dense and read as a barcode.
_CHAIR_ZONE_CM = 85.0


@dataclass
class WorkstationSpec:
    width_ft: float = 6.0          # workstation footprint width (desk width)
    depth_ft: float = 5.0          # workstation footprint depth (worktop + chair/access zone)
    aisle_ft: float = 3.0          # clear aisle between rows (ADA accessible route = 36in)
    perimeter_setback_ft: float = 3.0
    column_clearance_ft: float = 1.5
    corridor_ft: float = 5.5       # primary circulation spine width (~5-6 ft per code/ADA)
    neighborhood_ft: float = 40.0  # target open-block size between cross-aisles -> departments

    @classmethod
    def from_desk_cm(cls, width_cm: float, depth_cm: float, benching: bool = False) -> "WorkstationSpec":
        """Build a spec from a desk worktop (cm). Benching desks share a long run, so their width
        reads wider; the chair/access zone is added to the depth so the placed footprint is a real
        workstation, not a bare worktop."""
        width_ft = width_cm / _CM_PER_FT
        if benching:
            width_ft *= 1.4
        depth_ft = (depth_cm + _CHAIR_ZONE_CM) / _CM_PER_FT
        return cls(width_ft=round(width_ft, 3), depth_ft=round(depth_ft, 3))


@dataclass
class ProgramSpec:
    """High-level program driving the zone mix. Counts derive from headcount + these ratios."""
    headcount: int | None = None          # if None, derive from usable area / density
    density_rsf_per_person: float = 175.0  # rentable sf per person (typical modern office)
    workstation_ratio: float = 0.40
    private_office_ratio: float = 0.10
    meeting_ratio: float = 0.20
    collaboration_ratio: float = 0.15


@dataclass
class FurnitureInstance:
    type: str
    x: float
    y: float
    w: float
    h: float
    rotation: int = 0  # degrees
    # Carried only for SKU-tagged pieces slotted from a real Steelcase setting; None for the
    # parametric room boxes + workstations the procedural packers place.
    brand: str | None = None
    model: str | None = None
    list_price: float | None = None
    # True for furniture dropped INSIDE a room by slot_settings — distinguishes a real "workstation"
    # product from a structural workstation slot, which share a type string.
    slotted: bool = False


@dataclass
class TestFit:
    workstation_count: int
    office_count: int = 0
    meeting_count: int = 0
    collab_count: int = 0
    instances: list[FurnitureInstance] = field(default_factory=list)
    placeable_area_sf: float = 0.0
    sf_per_workstation: float | None = None
    program: dict | None = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Placeable region helpers (shared with v1)
# ---------------------------------------------------------------------------

def _usable_boundary(plan: PlanModel, spec: WorkstationSpec) -> Polygon:
    region = Polygon(plan.boundary)
    if spec.perimeter_setback_ft:
        region = region.buffer(-spec.perimeter_setback_ft)
    return region


def _cores(plan: PlanModel) -> list[Polygon]:
    out = []
    for core in plan.cores:
        try:
            p = Polygon(core)
            if p.is_valid and p.area > 0:
                out.append(p)
        except Exception:  # noqa: BLE001
            pass
    return out


def _column_circles(plan: PlanModel, spec: WorkstationSpec) -> list:
    return [Point(cx, cy).buffer(spec.column_clearance_ft) for (cx, cy) in plan.columns]


def _placeable_region(plan: PlanModel, spec: WorkstationSpec):
    region = _usable_boundary(plan, spec)
    for core in _cores(plan):
        try:
            region = region.difference(core)
        except Exception:  # noqa: BLE001
            pass
    for col in _column_circles(plan, spec):
        region = region.difference(col)
    return region


# ---------------------------------------------------------------------------
# Program derivation
# ---------------------------------------------------------------------------

def derive_program(plan: PlanModel, program: ProgramSpec) -> dict:
    """Turn usable area + ratios into target instance counts.

    Headcount drives offices/meetings/collab; the remaining open interior is filled with the
    workstation field (its count is whatever physically fits, not a hard target).
    """
    if program.headcount and program.headcount > 0:
        headcount = int(program.headcount)
    else:
        headcount = max(1, int(plan.usable_area_sf / max(program.density_rsf_per_person, 1.0)))

    target_offices = max(0, round(headcount * program.private_office_ratio))
    # ~6 seats per meeting room -> meeting ROOMS, not seats
    meeting_seats = headcount * program.meeting_ratio
    target_meetings = max(0, round(meeting_seats / 6.0))
    # ~6 people per collaboration lounge cluster
    collab_seats = headcount * program.collaboration_ratio
    target_collab = max(0, round(collab_seats / 6.0))

    return {
        "headcount": headcount,
        "density_rsf_per_person": program.density_rsf_per_person,
        "mix": {
            "workstation_ratio": program.workstation_ratio,
            "private_office_ratio": program.private_office_ratio,
            "meeting_ratio": program.meeting_ratio,
            "collaboration_ratio": program.collaboration_ratio,
        },
        "target_offices": target_offices,
        "target_meetings": target_meetings,
        "target_collaboration": target_collab,
    }


# ---------------------------------------------------------------------------
# Circulation: carve a primary spine + cross-aisles so the open field reads as
# legible neighborhoods around a corridor, not one solid block of desks.
# ---------------------------------------------------------------------------

def circulation_corridors(region, spec: WorkstationSpec) -> list[Polygon]:
    """Derive circulation bands to subtract from the open workstation field.

    A primary spine runs the full span of the region's longer axis, centred on the field, plus
    evenly spaced cross-aisles along the longer axis that split the field into ~`neighborhood_ft`
    departments. Bands are clipped to the region so they connect to the perimeter setback (the
    inset boundary doubles as the perimeter route) and never sit over rooms/core/columns. Pure
    geometry, deterministic — no desks land in the returned bands once they are subtracted.
    """
    if region.is_empty or region.area <= 0 or spec.corridor_ft <= 0:
        return []
    minx, miny, maxx, maxy = region.bounds
    span_x, span_y = maxx - minx, maxy - miny
    half = spec.corridor_ft / 2.0
    bands: list[Polygon] = []

    # Primary spine down the centre of the LONGER axis (a desk-free aisle through the field).
    if span_x >= span_y:
        cy = (miny + maxy) / 2.0
        bands.append(box(minx, cy - half, maxx, cy + half))
        long_lo, long_span = minx, span_x
        cross_axis_horizontal = False
    else:
        cx = (minx + maxx) / 2.0
        bands.append(box(cx - half, miny, cx + half, maxy))
        long_lo, long_span = miny, span_y
        cross_axis_horizontal = True

    # Cross-aisles perpendicular to the spine, splitting the long axis into neighborhoods.
    n_blocks = max(1, round(long_span / max(spec.neighborhood_ft, 1.0)))
    for i in range(1, n_blocks):
        pos = long_lo + long_span * i / n_blocks
        if cross_axis_horizontal:
            bands.append(box(minx, pos - half, maxx, pos + half))
        else:
            bands.append(box(pos - half, miny, pos + half, maxy))

    clipped = [b.intersection(region) for b in bands]
    return [c for c in clipped if not c.is_empty and c.area > 0]


# ---------------------------------------------------------------------------
# Workstation grid (v1, now run on a region with rooms subtracted)
# ---------------------------------------------------------------------------

def _grid_layout(region_prepared, bounds, w: float, h: float, step_y: float,
                 off_x: float, off_y: float) -> list[FurnitureInstance]:
    minx, miny, maxx, maxy = bounds
    out: list[FurnitureInstance] = []
    y = miny + off_y
    while y + h <= maxy:
        x = minx + off_x
        while x + w <= maxx:
            cell = box(x, y, x + w, y + h)
            if region_prepared.contains(cell):
                out.append(FurnitureInstance(type="workstation", x=round(x, 2), y=round(y, 2),
                                             w=w, h=h, rotation=0 if w >= h else 90))
            x += w
        y += step_y
    return out


def _place_workstation_field(region, spec: WorkstationSpec) -> list[FurnitureInstance]:
    if region.is_empty or region.area <= 0:
        return []
    for corridor in circulation_corridors(region, spec):
        region = region.difference(corridor)
    if region.is_empty or region.area <= 0:
        return []
    prepared = prep(region)
    bounds = region.bounds
    best: list[FurnitureInstance] = []
    for (w, h) in [(spec.width_ft, spec.depth_ft), (spec.depth_ft, spec.width_ft)]:
        step_y = h + spec.aisle_ft
        for off_x in (0.0, w / 2):
            for off_y in (0.0, step_y / 2):
                layout = _grid_layout(prepared, bounds, w, h, step_y, off_x, off_y)
                if len(layout) > len(best):
                    best = layout
    return best


# ---------------------------------------------------------------------------
# Settings slotting: drop a real, SKU-tagged Steelcase room into a matching program room
# ---------------------------------------------------------------------------

ROOM_CLEAR = 1.0  # ft kept clear between a setting and the room walls


def furnish_room(x: float, y: float, w: float, h: float, setting: Setting) -> list[FurnitureInstance]:
    """A specific Steelcase setting's real furniture, CENTERED in a room box and filtered to
    SLOT_CATS (the un-categorized CET sub-parts + glass are dropped). Any piece that would fall
    outside the room is skipped, so nothing spills over a wall. When the room is the setting's
    footprint + 2·ROOM_CLEAR (settings-as-rooms), every piece fits with clearance."""
    ox = x + (w - setting.width_ft) / 2
    oy = y + (h - setting.height_ft) / 2
    room = box(x, y, x + w, y + h)
    out: list[FurnitureInstance] = []
    for f in setting.furniture:
        if f.category not in SLOT_CATS:
            continue
        fx = round(ox + f.dx, 2)
        fy = round(oy + f.dy, 2)
        if not room.contains(box(fx, fy, fx + f.w, fy + f.h)):
            continue
        out.append(FurnitureInstance(
            type=f.category, x=fx, y=fy, w=f.w, h=f.h, rotation=int(round(f.rotation)),
            brand=f.brand, model=f.model, list_price=f.list_price, slotted=True,
        ))
    return out


def _fitting_settings(inst: FurnitureInstance, settings: list[Setting]) -> list[Setting]:
    """Settings whose type matches the room and whose footprint fits inside the room MINUS a
    wall-clearance margin (so the centered setting never touches the walls), largest first."""
    avail_w = inst.w - 2 * ROOM_CLEAR
    avail_h = inst.h - 2 * ROOM_CLEAR
    return sorted(
        (s for s in settings
         if s.setting_type == inst.type and s.width_ft <= avail_w and s.height_ft <= avail_h),
        key=lambda s: (s.sqft, s.id), reverse=True,
    )


def slot_settings(
    instances: list[FurnitureInstance], settings: list[Setting]
) -> list[FurnitureInstance]:
    """Furnish each PARAMETRIC enclosed room by re-picking a Steelcase setting that fits inside it.

    Used by the Detailed program, whose rooms are fixed program rectangles (Concept's
    generate_mixed_layout instead sizes each room to its setting and furnishes from it directly).
    A no-op when the library is empty, so the output is unchanged with no library.
    """
    if not settings:
        return instances
    out = list(instances)
    used: dict[str, int] = {}  # per room-type counter -> cycle settings so adjacent rooms differ
    for inst in instances:
        if inst.type not in SLOTTABLE_TYPES:
            continue
        candidates = _fitting_settings(inst, settings)
        if not candidates:
            continue
        i = used.get(inst.type, 0)
        used[inst.type] = i + 1
        out += furnish_room(inst.x, inst.y, inst.w, inst.h, candidates[i % len(candidates)])
    return out


def _setting_room_specs(lib: list[Setting], setting_type: str, n: int) -> list[RoomSpec]:
    """RoomSpecs for up to `n` enclosed rooms, each sized to a chosen Steelcase application's
    footprint plus a wall-clearance margin, and tagged with that application so the room is
    furnished from it. Empty when the library has no placeable setting of the type."""
    return [
        RoomSpec(
            type=setting_type,
            width_ft=round(s.width_ft + 2 * ROOM_CLEAR, 2),
            depth_ft=round(s.height_ft + 2 * ROOM_CLEAR, 2),
            setting=s,
        )
        for s in pick_settings(lib, setting_type, n)
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def place_workstations(plan: PlanModel, spec: WorkstationSpec | None = None) -> TestFit:
    """Backwards-compatible v1 entry point: open-plan workstation field ONLY.

    Kept so existing callers/tests that only want the workstation field still work. The
    richer mixed layout is `generate_mixed_layout`.
    """
    spec = spec or WorkstationSpec()
    region = _placeable_region(plan, spec)
    if region.is_empty or region.area <= 0:
        return TestFit(workstation_count=0, placeable_area_sf=0.0,
                       notes=["No placeable area after setbacks/core/columns."])
    best = _place_workstation_field(region, spec)
    count = len(best)
    placeable_sf = round(region.area, 1)
    return TestFit(
        workstation_count=count,
        instances=best,
        placeable_area_sf=placeable_sf,
        sf_per_workstation=round(placeable_sf / count, 1) if count else None,
        notes=[
            "Open-plan workstation field (procedural grid + constraint filter). Aisles between "
            "rows; desks held off walls/columns/core. Human-editable starting layout, not final.",
            "Use generate_mixed_layout for offices/meeting rooms/collaboration zones.",
        ],
    )


def generate_mixed_layout(
    plan: PlanModel,
    spec: WorkstationSpec | None = None,
    program: ProgramSpec | None = None,
    settings: list[Setting] | None = None,
) -> TestFit:
    """Produce the full mixed test-fit: rooms (perimeter) + collab (interior) + workstations.

    Invariant: rooms and lounges are placed FIRST and subtracted from the placeable region
    before the workstation grid runs, so every instance is mutually non-overlapping.
    """
    spec = spec or WorkstationSpec()
    program = program or ProgramSpec()
    prog = derive_program(plan, program)

    usable = _usable_boundary(plan, spec)
    if usable.is_empty or usable.area <= 0:
        return TestFit(workstation_count=0, placeable_area_sf=0.0, program=prog,
                       notes=["No usable area after perimeter setback."])
    cores = _cores(plan)
    columns = _column_circles(plan, spec)

    lib = load_settings() if settings is None else settings

    # 1) Perimeter rooms (offices + meeting rooms) against the exterior wall. With a Steelcase
    #    library each room is sized to a real application's footprint (so the rich, fully-furnished
    #    applications actually get used, not just the few tiny ones that fit a parametric box);
    #    without one, fall back to parametric program rectangles.
    office_specs = _setting_room_specs(lib, "private_office", prog["target_offices"])
    meeting_specs = _setting_room_specs(lib, "meeting_room", prog["target_meetings"])
    room_order = (
        meeting_specs + office_specs
        if (office_specs or meeting_specs)
        else [MEETING_ROOM] * prog["target_meetings"] + [PRIVATE_OFFICE] * prog["target_offices"]
    )
    rooms = place_perimeter_rooms(
        boundary_poly=usable, cores=cores, column_circles=columns,
        setback_ft=0.0,  # `usable` is already inset by the perimeter setback
        column_clearance_ft=spec.column_clearance_ft, room_order=room_order,
    )
    room_polys = [box(r.x, r.y, r.x + r.w, r.y + r.h) for r in rooms]

    # Region left after removing rooms, core, and columns (for collab + workstations).
    # A tiny clearance epsilon is buffered around obstacles so placed footprints stay strictly
    # CLEAR of (not merely touching) the core/columns/rooms — the geometric-validity gate treats
    # edge-touching as a violation.
    eps = 0.05
    region = usable
    for c in cores:
        region = region.difference(c.buffer(eps))
    for col in columns:
        region = region.difference(col.buffer(eps))
    for rp in room_polys:
        region = region.difference(rp.buffer(eps))

    # 2) Collaboration in the interior — real collaboration applications (sized to their footprint)
    #    when the library has them, else fixed-size lounges.
    collab_specs = _setting_room_specs(lib, "collaboration", prog["target_collaboration"])
    zones = (
        place_interior_rooms(region, occupied_polys=list(room_polys), room_order=collab_specs)
        if collab_specs
        else place_collaboration_zones(
            placeable_region=region, occupied_polys=list(room_polys),
            target_count=prog["target_collaboration"], size_ft=COLLAB_SIZE_FT,
        )
    )
    zone_polys = [box(z.x, z.y, z.x + z.w, z.y + z.h) for z in zones]

    # 3) Subtract lounges, then place the workstation field on what remains.
    for zp in zone_polys:
        region = region.difference(zp)
    workstations = _place_workstation_field(region, spec)

    instances: list[FurnitureInstance] = []
    instances += [FurnitureInstance(r.type, r.x, r.y, r.w, r.h, r.rotation) for r in rooms]
    instances += [FurnitureInstance(z.type, z.x, z.y, z.w, z.h, z.rotation) for z in zones]
    instances += workstations
    # Furnish each enclosed room from the real Steelcase application it was sized to.
    for r in (*rooms, *zones):
        setting = getattr(r, "setting", None)
        if setting is not None:
            instances += furnish_room(r.x, r.y, r.w, r.h, setting)

    office_count = sum(1 for r in rooms if r.type == "private_office")
    meeting_count = sum(1 for r in rooms if r.type == "meeting_room")
    collab_count = len(zones)
    ws_count = len(workstations)
    placeable_sf = round(_placeable_region(plan, spec).area, 1)

    notes = [
        "Mixed test-fit (procedural): perimeter rooms + interior collaboration + open workstation "
        "field. Rooms placed first and subtracted from the field, so nothing overlaps.",
        f"Program: headcount={prog['headcount']} @ {prog['density_rsf_per_person']:.0f} rsf/person; "
        f"targets offices={prog['target_offices']} meetings={prog['target_meetings']} "
        f"collab={prog['target_collaboration']}.",
        "Procedural placement + Shapely constraint filter (no OR-Tools). Deferred: egress spines, "
        "door swings/corridors, code/ADA compliance, acoustic/adjacency, skewed walls.",
    ]
    if office_count < prog["target_offices"] or meeting_count < prog["target_meetings"]:
        notes.append(
            f"Placed fewer rooms than targeted (offices {office_count}/{prog['target_offices']}, "
            f"meetings {meeting_count}/{prog['target_meetings']}) — perimeter ran out of clear wall."
        )

    return TestFit(
        workstation_count=ws_count,
        office_count=office_count,
        meeting_count=meeting_count,
        collab_count=collab_count,
        instances=instances,
        placeable_area_sf=placeable_sf,
        sf_per_workstation=round(placeable_sf / ws_count, 1) if ws_count else None,
        program=prog,
        notes=notes,
    )
