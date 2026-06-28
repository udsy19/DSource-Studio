"""Room catalog tests — the Qbiq taxonomy + Detailed consuming it.

Pure geometry on a rectangular plate (mirrors test_detailed.py). Asserts: the catalog exposes the
expected keys with positive footprints + valid instance types; legacy aliases still resolve;
requesting a mix of new room types places the right instance types/sizes (or notes an honest
shortfall); and unknown room types are rejected at validation.
"""

import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.catalog import CATALOG, is_valid_key, lookup, room_spec, valid_keys
from app.testfit.detailed import DetailedProgram, RoomRequest, generate_from_detailed

_VALID_INSTANCE_TYPES = {
    "private_office", "meeting_room", "collaboration", "phone_booth",
    "reception", "kitchen", "wellness", "copy_print", "storage",
}

_EXPECTED_KEYS = {
    "office_exec", "office_large", "office_medium", "office_small", "office_focus",
    "team_2", "team_4", "team_6", "team_8",
    "conf_board", "conf_xl", "conf_large", "conf_medium", "conf_small",
    "huddle", "phone_booth", "focus_room",
    "reception", "kitchen", "wellness", "copy_print", "storage",
}

_LEGACY_KEYS = {"office", "meeting", "huddle", "phone_booth"}


def _plan() -> PlanModel:
    """A large 200 x 120 ft rectangular plate (roomy enough for the big conference rooms)."""
    w, h = 200.0, 120.0
    boundary = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h), (0.0, 0.0)]
    area = w * h
    return PlanModel(
        units="feet", sqft_factor=1.0, boundary=boundary,
        gross_area_sf=area, core_area_sf=0.0, usable_area_sf=area,
        columns=[], cores=[], boundary_source="polyline",
        needs_confirmation=False, notes=[],
    )


def _instances_of(alt: dict, instance_type: str) -> list[dict]:
    return [i for i in alt["testfit"]["instances"] if i["type"] == instance_type]


def test_catalog_has_expected_keys():
    assert set(CATALOG) == _EXPECTED_KEYS


def test_every_entry_has_positive_footprint_and_valid_instance_type():
    for entry in CATALOG.values():
        assert entry.width_ft > 0 and entry.height_ft > 0, entry.key
        assert entry.instance_type in _VALID_INSTANCE_TYPES, entry.key
        assert entry.default_placement in {"window", "core", "flexible"}, entry.key


def test_legacy_aliases_resolve():
    for key in _LEGACY_KEYS:
        assert is_valid_key(key)
    assert valid_keys() >= _LEGACY_KEYS | _EXPECTED_KEYS
    # The old "office"/"meeting" keys map onto real catalog entries.
    assert lookup("office").instance_type == "private_office"
    assert lookup("meeting").instance_type == "meeting_room"


def test_room_spec_carries_instance_type_and_size():
    spec = room_spec("office_exec")
    assert spec.type == "private_office"
    assert (spec.width_ft, spec.depth_ft) == (15.0, 14.0)


def test_mixed_new_types_place_correct_instances():
    program = DetailedProgram(rooms=[
        RoomRequest(type="office_exec", count=2, placement="window"),
        RoomRequest(type="conf_board", count=1, placement="flexible"),
        RoomRequest(type="kitchen", count=1, placement="flexible"),
    ])
    result = generate_from_detailed(_plan(), program)
    alt_a = result["alternatives"][0]

    # Two exec offices -> two private_office instances at 15x14.
    offices = _instances_of(alt_a, "private_office")
    assert len(offices) == 2
    for o in offices:
        assert {round(o["w"]), round(o["h"])} == {15, 14}

    # The boardroom -> one meeting_room at 20x40 (either orientation along the wall).
    boards = _instances_of(alt_a, "meeting_room")
    assert len(boards) == 1
    assert {round(boards[0]["w"]), round(boards[0]["h"])} == {20, 40}

    # The kitchen carries its own amenity instance type at 14x16.
    kitchens = _instances_of(alt_a, "kitchen")
    assert len(kitchens) == 1
    assert {round(kitchens[0]["w"]), round(kitchens[0]["h"])} == {14, 16}

    placed = alt_a["testfit"]["program"]["placed"]
    assert placed["office_exec"] == 2
    assert placed["conf_board"] == 1
    assert placed["kitchen"] == 1


def test_shortfall_noted_per_catalog_key():
    """Far more boardrooms than fit -> fewer placed, honest per-key note, never off-plate."""
    program = DetailedProgram(rooms=[RoomRequest(type="conf_board", count=60, placement="window")])
    result = generate_from_detailed(_plan(), program)
    alt_a = result["alternatives"][0]

    placed = len(_instances_of(alt_a, "meeting_room"))
    assert placed < 60
    assert alt_a["testfit"]["program"]["placed"].get("conf_board", 0) == placed
    assert any("fewer than requested" in n for n in alt_a["testfit"]["notes"])


def test_unknown_type_is_rejected():
    with pytest.raises(ValidationError):
        RoomRequest(type="not_a_room", count=1)


def test_legacy_keys_still_match_through_detailed():
    program = DetailedProgram(rooms=[
        RoomRequest(type="office", count=3, placement="window"),
        RoomRequest(type="meeting", count=1, placement="core"),
    ])
    result = generate_from_detailed(_plan(), program)
    alt_a = result["alternatives"][0]
    assert len(_instances_of(alt_a, "private_office")) == 3
    assert len(_instances_of(alt_a, "meeting_room")) == 1
    assert alt_a["testfit"]["program"]["placed"]["office"] == 3
