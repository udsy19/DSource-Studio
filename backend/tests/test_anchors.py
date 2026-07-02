"""Program anchor pins — hard placement constraints (workstream C).

An anchor pins "a room of this type goes HERE" (plan feet). The placer must seat that room containing
the point before free placement; an anchor it cannot satisfy is surfaced honestly in
`unsatisfied_anchors` (never silently dropped) and penalises the variant's program_match. Competing
anchors resolve deterministically. Pure geometry — no DB/catalog/network.
"""

from shapely.geometry import Point, box

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.detailed import Anchor, DetailedProgram, RoomRequest, generate_from_detailed


def _plan() -> PlanModel:
    w, h = 140.0, 90.0
    boundary = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    area = w * h
    return PlanModel(
        units="feet", sqft_factor=1.0, boundary=boundary,
        gross_area_sf=area, core_area_sf=0.0, usable_area_sf=area,
        columns=[], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )


def _offices(alt: dict) -> list[dict]:
    return [i for i in alt["testfit"]["instances"] if i["type"] == "private_office"]


def _contains(room: dict, x: float, y: float) -> bool:
    return box(room["x"], room["y"], room["x"] + room["w"], room["y"] + room["h"]).buffer(1e-6).contains(Point(x, y))


def test_anchored_room_contains_its_point_in_every_variant():
    ax, ay = 45.0, 45.0
    program = DetailedProgram(
        rooms=[RoomRequest(type="office_medium", count=1, placement="flexible")],
        anchors=[Anchor(room_type="office_medium", x=ax, y=ay)],
    )
    result = generate_from_detailed(_plan(), program)
    for alt in result["alternatives"]:
        offices = _offices(alt)
        assert offices, f"variant {alt['id']} placed no office"
        assert any(_contains(o, ax, ay) for o in offices), f"variant {alt['id']} office not on the anchor"
        assert alt["testfit"]["program"]["unsatisfied_anchors"] == []


def test_impossible_anchor_is_surfaced_and_penalised_not_faked():
    # A point inside the 3 ft perimeter setback: no room can contain it and stay in the usable area.
    program = DetailedProgram(
        rooms=[RoomRequest(type="office_medium", count=1, placement="flexible")],
        anchors=[Anchor(room_type="office_medium", x=1.0, y=1.0)],
    )
    result = generate_from_detailed(_plan(), program)
    assert len(result["alternatives"]) == 3  # generation still succeeds
    alt_a = result["alternatives"][0]
    uns = alt_a["testfit"]["program"]["unsatisfied_anchors"]
    assert len(uns) == 1 and uns[0]["room_type"] == "office_medium"
    assert alt_a["testfit"]["program"]["placed"].get("office_medium", 0) == 0  # not backfilled elsewhere
    rec = next(a for a in result["alternatives"] if a["recommended"])
    assert rec["score_breakdown"]["program_match"] < 1.0


def test_competing_anchors_resolve_deterministically():
    # Two office anchors 1 ft apart — both rooms cannot fit without overlap, so exactly one lands.
    program = DetailedProgram(
        rooms=[RoomRequest(type="office_medium", count=2, placement="flexible")],
        anchors=[
            Anchor(room_type="office_medium", x=45.0, y=45.0),
            Anchor(room_type="office_medium", x=46.0, y=45.0),
        ],
    )
    r1 = generate_from_detailed(_plan(), program)
    r2 = generate_from_detailed(_plan(), program)
    assert r1 == r2  # deterministic

    alt = r1["alternatives"][0]
    assert len(_offices(alt)) == 1
    uns = alt["testfit"]["program"]["unsatisfied_anchors"]
    assert len(uns) == 1
    # coord tiebreak: (45,45) sorts before (46,45), so the second anchor is the one that loses.
    assert (uns[0]["x"], uns[0]["y"]) == (46.0, 45.0)


def test_no_anchors_leaves_unsatisfied_empty():
    program = DetailedProgram(rooms=[RoomRequest(type="office_medium", count=2, placement="window")])
    alt = generate_from_detailed(_plan(), program)["alternatives"][0]
    assert alt["testfit"]["program"]["unsatisfied_anchors"] == []
