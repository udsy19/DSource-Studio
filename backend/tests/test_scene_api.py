"""Scene editor HTTP API — the boundary over the semantic scene model.

Covers the JSON round-trip, applying commands (happy path + a plate resolved by id from the real
library + an invariant/unknown rejection surfaced as 422), the metrics scoreboard, and DXF export.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.main import app
from app.scene.model import (
    Door, Partition, Placement, PlacementItem, Plate, PlateItem, Program, ProgramLine,
    Scene, Transform, Underlay, Zone,
)
from app.scene.serialize import scene_from_dict, scene_to_dict
from app.testfit.settings import load_settings

client = TestClient(app)


def _scene() -> Scene:
    poly = [(0.0, 0.0), (10.0, 0.0), (10.0, 12.0), (0.0, 12.0)]
    ring = poly + [poly[0]]
    partitions = [Partition(id=f"z0-p{i}", segment=(ring[i], ring[i + 1])) for i in range(4)]
    plate = Plate(id="plate0", room_type="private_office", sqft=120.0, width_ft=10.0, height_ft=12.0,
                  capacity=1, items=[PlateItem(category="desk", model="D1", dx=1, dy=1, w=5, h=2.5),
                                     PlateItem(category="chair", model="C1", dx=2, dy=4, w=2, h=2)])
    return Scene(
        underlay=Underlay(boundary=((-5.0, -5.0), (25.0, -5.0), (25.0, 25.0), (-5.0, 25.0))),
        zones=[Zone(id="z0", polygon=poly, room_type="private_office", enclosed=True,
                    boundary_partition_ids=[p.id for p in partitions])],
        partitions=partitions,
        doors=[Door(id="z0-d0", host_partition_id="z0-p2", offset=3.0, width=3.0)],
        placements=[Placement(id="z0-pl", zone_id="z0", plate_id="plate0", transform=Transform(),
                              items=[PlacementItem(plate_item_ref=0), PlacementItem(plate_item_ref=1)])],
        plates={"plate0": plate},
        program_ref=Program(lines=[ProgramLine(room_type="private_office", target=2)]),
    )


def test_scene_json_round_trips():
    d = scene_to_dict(_scene())
    assert scene_to_dict(scene_from_dict(d)) == d


def test_metrics_scoreboard():
    r = client.post("/api/scene/metrics", json={"scene": scene_to_dict(_scene())})
    assert r.status_code == 200
    m = r.json()
    assert "seats" in m and "program" in m  # scoreboard present


def test_apply_change_room_type():
    r = client.post("/api/scene/apply", json={
        "scene": scene_to_dict(_scene()),
        "command": {"type": "change_room_type", "zone_id": "z0", "new_type": "meeting_room"},
    })
    assert r.status_code == 200
    zone = r.json()["scene"]["zones"][0]
    assert zone["room_type"] == "meeting_room"


def test_apply_swap_plate_resolves_a_real_library_plate():
    plate_id = next(s.id for s in load_settings() if s.setting_type == "private_office")
    r = client.post("/api/scene/apply", json={
        "scene": scene_to_dict(_scene()),
        "command": {"type": "swap_plate", "placement_id": "z0-pl", "plate_id": plate_id},
    })
    assert r.status_code == 200
    scene = r.json()["scene"]
    assert scene["placements"][0]["plate_id"] == plate_id
    assert plate_id in scene["plates"]  # the resolved plate is embedded in the scene


def test_unknown_command_is_422_with_code():
    r = client.post("/api/scene/apply", json={
        "scene": scene_to_dict(_scene()),
        "command": {"type": "nonsense"},
    })
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "unknown_command"


def test_unknown_zone_command_is_422():
    r = client.post("/api/scene/apply", json={
        "scene": scene_to_dict(_scene()),
        "command": {"type": "change_room_type", "zone_id": "nope", "new_type": "meeting_room"},
    })
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "unknown_zone"


def test_dxf_export():
    r = client.post("/api/scene/dxf", json={"scene": scene_to_dict(_scene())})
    assert r.status_code == 200
    assert len(r.content) > 0
    assert "dxf" in r.headers["content-type"]
