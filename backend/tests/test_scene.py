"""Scene model tests — invariants, command do/undo round-trips, metric purity, DXF round-trip.

Builds small scenes directly (and via the adapter from a generated test-fit) with no DB/network.
Pure geometry + ezdxf only, mirroring test_dxf_export.py.
"""

import io

import ezdxf
import pytest

from app.floorplan.dxf_ingest import PlanModel
from app.scene.adapters import scene_from_generated
from app.scene.commands import (
    ChangeRoomType,
    CommandStack,
    DeleteItem,
    EditDoor,
    EditedDesign,
    MergeZones,
    MoveItem,
    RotateItem,
    SetOpenEnclosed,
    SwapPlate,
)
from app.scene.export import scene_to_dxf
from app.scene.geometry import scene_to_layout
from app.scene.metrics import compute_scene_metrics
from app.scene.model import (
    Door,
    Partition,
    Placement,
    PlacementItem,
    Plate,
    PlateItem,
    Program,
    ProgramLine,
    Scene,
    SceneError,
    Transform,
    Underlay,
    Zone,
    validate_invariants,
)
from app.testfit.layout import FurnitureInstance


# ── fixtures ────────────────────────────────────────────────────────────────
def _office_plate(plate_id: str = "office-plate") -> Plate:
    return Plate(
        id=plate_id, room_type="private_office", sqft=120.0, width_ft=10.0, height_ft=12.0,
        capacity=1,
        items=[
            PlateItem(category="desk", model="D1", dx=1.0, dy=1.0, w=5.0, h=2.5, rotation=0),
            PlateItem(category="chair", model="C1", dx=2.0, dy=4.0, w=2.0, h=2.0, rotation=0),
        ],
    )


def _enclosed_scene() -> Scene:
    """One enclosed private-office zone: 4 partitions ring it, one door on p0, a plate placed in it."""
    poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 12.0), (0.0, 12.0)]
    ring = poly + [poly[0]]
    partitions = [
        Partition(id=f"z0-p{i}", segment=(ring[i], ring[i + 1])) for i in range(4)
    ]
    zone = Zone(id="z0", polygon=poly, room_type="private_office", enclosed=True,
                boundary_partition_ids=[p.id for p in partitions])
    plate = _office_plate()
    scene = Scene(
        underlay=Underlay(boundary=((-5.0, -5.0), (25.0, -5.0), (25.0, 25.0), (-5.0, 25.0))),
        zones=[zone],
        partitions=partitions,
        doors=[Door(id="z0-d0", host_partition_id="z0-p2", offset=3.0, width=3.0)],
        placements=[Placement(id="z0-pl", zone_id="z0", plate_id=plate.id,
                              transform=Transform(x=0.0, y=0.0),
                              items=[PlacementItem(plate_item_ref=0), PlacementItem(plate_item_ref=1)])],
        plates={plate.id: plate},
        program_ref=Program(lines=[ProgramLine(room_type="private_office", target=2)]),
    )
    validate_invariants(scene)
    return scene


# ── invariant 1: underlay is immutable ────────────────────────────────────
def test_underlay_is_frozen():
    u = Underlay(boundary=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)))
    with pytest.raises(Exception):  # FrozenInstanceError
        u.boundary = ((0.0, 0.0),)


def test_underlay_boundary_is_tuple_no_append():
    u = Underlay(boundary=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)))
    assert isinstance(u.boundary, tuple)
    assert not hasattr(u.boundary, "append")


# ── invariant 2: enclosed zone needs a door on a generated partition ────────
def test_enclosed_zone_without_door_is_rejected():
    scene = _enclosed_scene()
    scene.doors = []
    with pytest.raises(SceneError) as exc:
        validate_invariants(scene)
    assert exc.value.code == "enclosed_zone_without_door"


def test_door_must_host_a_generated_partition():
    scene = _enclosed_scene()
    scene.doors[0].host_partition_id = "does-not-exist"
    with pytest.raises(SceneError) as exc:
        validate_invariants(scene)
    assert exc.value.code == "door_without_host"


def test_open_zone_needs_no_door():
    scene = _enclosed_scene()
    scene.zones[0].enclosed = False
    scene.doors = []
    validate_invariants(scene)  # no raise


# ── invariant 3 + commands: do/undo round-trips ─────────────────────────────
def test_change_room_type_round_trip():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(ChangeRoomType("z0", "meeting_room"))
    assert scene.zones[0].room_type == "meeting_room"
    stack.undo()
    assert scene.zones[0].room_type == "private_office"
    stack.redo()
    assert scene.zones[0].room_type == "meeting_room"


def test_swap_plate_round_trip():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    new_plate = Plate(id="p2", room_type="private_office", sqft=120.0, width_ft=10.0,
                      height_ft=12.0, capacity=1,
                      items=[PlateItem(category="desk", model="D2", dx=1, dy=1, w=4, h=2, rotation=0)])
    stack.execute(SwapPlate("z0-pl", new_plate))
    assert scene.placements[0].plate_id == "p2"
    assert len(scene.placements[0].items) == 1
    stack.undo()
    assert scene.placements[0].plate_id == "office-plate"
    assert len(scene.placements[0].items) == 2
    assert "p2" not in scene.plates


def test_set_enclosed_to_open_removes_partitions_and_doors():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(SetOpenEnclosed("z0", enclosed=False))
    assert scene.zones[0].enclosed is False
    assert scene.partitions == []
    assert scene.doors == []
    stack.undo()
    assert scene.zones[0].enclosed is True
    assert len(scene.partitions) == 4
    assert len(scene.doors) == 1


def test_set_open_to_enclosed_adds_door_by_construction():
    scene = _enclosed_scene()
    # start from an open zone
    scene.zones[0].enclosed = False
    scene.zones[0].boundary_partition_ids = []
    scene.partitions = []
    scene.doors = []
    stack = CommandStack(scene)
    stack.execute(SetOpenEnclosed("z0", enclosed=True))
    assert scene.zones[0].enclosed is True
    assert len(scene.partitions) == 4
    assert len(scene.doors) == 1  # invariant held by construction
    validate_invariants(scene)
    stack.undo()
    assert scene.partitions == []
    assert scene.doors == []


def test_move_item_clamps_inside_zone():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    # push the desk far to the right; it must clamp inside the 10x12 zone.
    stack.execute(MoveItem("z0-pl", item_ref=0, dx=100.0, dy=0.0))
    override = scene.placements[0].items[0].transform_override
    assert override is not None
    # desk is 5 wide starting local dx; clamped so right edge <= zone width 10.
    assert override.x + 5.0 <= 10.0 + 1e-6
    stack.undo()
    assert scene.placements[0].items[0].transform_override is None


def test_rotate_item_snaps_to_45():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(RotateItem("z0-pl", item_ref=1, delta=50.0))
    override = scene.placements[0].items[1].transform_override
    assert override.rotation % 45 == 0
    stack.undo()
    assert scene.placements[0].items[1].transform_override is None


def test_delete_item_round_trip():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(DeleteItem("z0-pl", item_ref=0))
    assert scene.placements[0].items[0].deleted is True
    stack.undo()
    assert scene.placements[0].items[0].deleted is False


def test_edit_door_offset_clamps_and_flips_swing():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(EditDoor("z0-d0", offset=999.0, flip_swing=True))
    door = scene.doors[0]
    host = next(p for p in scene.partitions if p.id == door.host_partition_id)
    assert door.offset <= host.length() - door.width + 1e-6
    assert door.swing == "right"
    stack.undo()
    assert scene.doors[0].offset == 3.0
    assert scene.doors[0].swing == "left"


def test_history_is_the_audit_trail():
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(ChangeRoomType("z0", "meeting_room"))
    stack.execute(DeleteItem("z0-pl", item_ref=0))
    assert stack.history() == [
        "change room type of z0 to meeting_room",
        "delete item 0 of z0-pl",
    ]


def test_execute_rolls_back_on_invariant_violation():
    """Enclosing a zone while removing its door would violate invariant 2 — but SetOpenEnclosed adds
    a door. To prove rollback, remove the door via a raw command that leaves the scene invalid."""
    scene = _enclosed_scene()
    stack = CommandStack(scene)

    class DropDoors:
        description = "drop all doors (invalid)"

        def do(self, s):
            self._saved = s.doors
            s.doors = []

        def undo(self, s):
            s.doors = self._saved

    with pytest.raises(SceneError) as exc:
        stack.execute(DropDoors())
    assert exc.value.code == "enclosed_zone_without_door"
    assert len(scene.doors) == 1  # rolled back
    assert stack.history() == []  # not recorded


# ── versioning: fork-to-edit leaves the base alternative immutable ──────────
def test_fork_does_not_mutate_base_scene():
    base = _enclosed_scene()
    design = EditedDesign.fork("alt-1", base)
    design.stack.execute(ChangeRoomType("z0", "meeting_room"))
    assert design.scene.zones[0].room_type == "meeting_room"
    assert base.zones[0].room_type == "private_office"  # base untouched
    assert design.base_alternative_id == "alt-1"


# ── metrics: pure function of the scene ─────────────────────────────────────
def test_metrics_are_deterministic():
    scene = _enclosed_scene()
    assert compute_scene_metrics(scene) == compute_scene_metrics(scene)


def test_metrics_change_after_command():
    scene = _enclosed_scene()
    before = compute_scene_metrics(scene)
    CommandStack(scene).execute(DeleteItem("z0-pl", item_ref=0))  # delete the desk (a seat)
    after = compute_scene_metrics(scene)
    assert after["seats"] == before["seats"] - 1


def test_metrics_program_scoreboard():
    scene = _enclosed_scene()
    metrics = compute_scene_metrics(scene)
    line = next(l for l in metrics["program"]["lines"] if l["room_type"] == "private_office")
    assert line["target"] == 2
    assert line["actual"] == 1


# ── export: round-trips generated entities; underlay passed through ─────────
def _modelspace(data: bytes):
    return ezdxf.read(io.StringIO(data.decode("utf-8"))).modelspace()


def test_scene_to_dxf_passes_through_underlay():
    scene = _enclosed_scene()
    msp = _modelspace(scene_to_dxf(scene))
    walls = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "A-WALL"]
    assert len(walls) >= 1
    shell = walls[0]
    assert shell.closed  # the shell is a closed boundary
    assert len(list(shell.get_points())) == 4  # 4-corner underlay boundary, passed through verbatim


def test_scene_to_dxf_emits_generated_layers():
    scene = _enclosed_scene()
    msp = _modelspace(scene_to_dxf(scene))
    layers = {e.dxf.layer for e in msp.query("LWPOLYLINE")}
    assert "S-PARTITION" in layers
    assert "S-DOOR" in layers
    assert "S-FURN" in layers


def test_scene_to_dxf_furniture_count_matches_live_items():
    scene = _enclosed_scene()
    msp = _modelspace(scene_to_dxf(scene))
    furn = [e for e in msp.query("LWPOLYLINE") if e.dxf.layer == "S-FURN"]
    assert len(furn) == 2  # desk + chair, both live


def test_scene_to_dxf_reflects_delete_and_move():
    """The exported DXF must be the POST-EDIT reality: a deleted item is absent, a moved item sits
    at its new pose (the geometric form of the real=False discipline)."""
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(DeleteItem("z0-pl", item_ref=0))   # delete the desk
    stack.execute(MoveItem("z0-pl", item_ref=1, dx=1.0, dy=1.0))  # move the chair (base local 2,4)

    furn = [e for e in _modelspace(scene_to_dxf(scene)).query("LWPOLYLINE") if e.dxf.layer == "S-FURN"]
    assert len(furn) == 1  # desk gone, chair remains
    xs = [x for x, _ in ((p[0], p[1]) for p in furn[0].get_points())]
    assert min(xs) == pytest.approx(3.0, abs=1e-6)  # chair moved from local x=2 to x=3


def test_scene_to_layout_reflects_delete_and_move():
    """scene_to_layout is the single POST-EDIT projection feeding takeoff/report: a deleted item is
    absent from furniture, a moved item lands at its new world pose."""
    scene = _enclosed_scene()
    stack = CommandStack(scene)
    stack.execute(DeleteItem("z0-pl", item_ref=0))   # delete the desk
    stack.execute(MoveItem("z0-pl", item_ref=1, dx=1.0, dy=1.0))  # move the chair

    layout = scene_to_layout(scene)
    assert [f.category for f in layout.furniture] == ["chair"]  # desk absent
    chair = layout.furniture[0]
    assert (chair.x, chair.y) == pytest.approx((3.0, 5.0))  # base (2,4) + (1,1)


def test_scene_to_layout_projects_walls_and_doors():
    """The projection carries the underlay + generated partitions as walls and the generated door,
    so wall/door quantities in the takeoff are real."""
    layout = scene_to_layout(_enclosed_scene())
    wall_types = {w.type for w in layout.walls}
    assert "perimeter" in wall_types and "drywall" in wall_types
    assert len(layout.doors) == 1


# ── adapter: build a scene from a generated test-fit ────────────────────────
def _plan() -> PlanModel:
    w, h = 60.0, 40.0
    boundary = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    return PlanModel(
        units="feet", sqft_factor=1.0, boundary=boundary,
        gross_area_sf=w * h, core_area_sf=0.0, usable_area_sf=w * h,
        columns=[(30.0, 20.0)], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )


def _instances() -> list[FurnitureInstance]:
    return [
        FurnitureInstance(type="private_office", x=2.0, y=2.0, w=10.0, h=12.0),
        FurnitureInstance(type="desk", model="D9", x=4.0, y=4.0, w=5.0, h=2.5,
                          rotation=0, brand="Steelcase", slotted=True),
        FurnitureInstance(type="workstation", x=30.0, y=5.0, w=6.0, h=5.0),
        FurnitureInstance(type="workstation", x=40.0, y=5.0, w=6.0, h=5.0),
    ]


def test_adapter_builds_valid_scene():
    program = {"headcount": 8, "density_rsf_per_person": 175.0,
               "target_offices": 3, "target_meetings": 1, "target_collaboration": 1}
    scene = scene_from_generated(_plan(), _instances(), program)
    validate_invariants(scene)
    # one enclosed office zone + one open workstation field
    assert any(z.room_type == "private_office" and z.enclosed for z in scene.zones)
    assert any(z.room_type == "open" and not z.enclosed for z in scene.zones)
    # the enclosed office got partitions + a door (invariant 2 by construction)
    assert len(scene.doors) == 1
    # the slotted desk landed in the office's plate; workstations in the open plate
    office_plate = scene.plates["Z0-plate"]
    assert any(i.model == "D9" for i in office_plate.items)


def test_adapter_scene_exports_and_scores():
    scene = scene_from_generated(_plan(), _instances(), None)
    assert scene_to_dxf(scene).startswith(b"  0\nSECTION")
    metrics = compute_scene_metrics(scene)
    assert metrics["seats"] >= 2  # two workstations at least
