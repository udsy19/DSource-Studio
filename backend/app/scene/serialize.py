"""JSON boundary for the scene model + the command builder.

The scene is plain dataclasses (see model.py); the editor lives in the browser and drives edits over
HTTP, so this module is the only place that turns a scene into JSON and back, and turns a command
request `{type, ...}` into a `Command`. Keeping (de)serialization here means the model stays a pure
in-process representation with no framework coupling.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from . import commands as cmds
from .model import (
    BaseDoor,
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
)


def scene_to_dict(scene: Scene) -> dict[str, Any]:
    """A scene as a JSON-ready dict (tuples serialize as lists — the reader accepts either)."""
    return asdict(scene)


def _pt(p: Any) -> tuple[float, float]:
    return (float(p[0]), float(p[1]))


def _transform(d: Any) -> Transform:
    d = d or {}
    return Transform(x=float(d.get("x", 0.0)), y=float(d.get("y", 0.0)), rotation=float(d.get("rotation", 0.0)))


def _plate_item(d: dict) -> PlateItem:
    return PlateItem(
        category=d["category"], model=d.get("model"),
        dx=float(d["dx"]), dy=float(d["dy"]), w=float(d["w"]), h=float(d["h"]),
        rotation=float(d.get("rotation", 0.0)),
    )


def plate_from_dict(d: dict) -> Plate:
    return Plate(
        id=d["id"], room_type=d["room_type"], sqft=float(d["sqft"]),
        width_ft=float(d["width_ft"]), height_ft=float(d["height_ft"]),
        capacity=int(d.get("capacity", 0)),
        items=[_plate_item(it) for it in d.get("items", [])],
    )


def _underlay(d: dict) -> Underlay:
    return Underlay(
        boundary=tuple(_pt(p) for p in d.get("boundary", [])),
        cores=tuple(tuple(_pt(p) for p in c) for c in d.get("cores", [])),
        columns=tuple(_pt(p) for p in d.get("columns", [])),
        base_doors=tuple(BaseDoor(**bd) for bd in d.get("base_doors", [])),
    )


def _placement(d: dict) -> Placement:
    return Placement(
        id=d["id"], zone_id=d["zone_id"], plate_id=d["plate_id"],
        transform=_transform(d.get("transform")),
        items=[
            PlacementItem(
                plate_item_ref=int(it["plate_item_ref"]),
                transform_override=_transform(it["transform_override"]) if it.get("transform_override") else None,
                deleted=bool(it.get("deleted", False)),
            )
            for it in d.get("items", [])
        ],
    )


def scene_from_dict(d: dict) -> Scene:
    """Reconstruct a Scene from its JSON dict (the inverse of scene_to_dict)."""
    prog = d.get("program_ref") or {}
    return Scene(
        underlay=_underlay(d.get("underlay", {})),
        zones=[
            Zone(
                id=z["id"], polygon=[_pt(p) for p in z.get("polygon", [])], room_type=z["room_type"],
                enclosed=bool(z.get("enclosed", False)), program_line_ref=z.get("program_line_ref"),
                boundary_partition_ids=list(z.get("boundary_partition_ids", [])),
            )
            for z in d.get("zones", [])
        ],
        partitions=[
            Partition(id=p["id"], segment=(_pt(p["segment"][0]), _pt(p["segment"][1])),
                      generated=bool(p.get("generated", True)))
            for p in d.get("partitions", [])
        ],
        doors=[
            Door(id=dr["id"], host_partition_id=dr["host_partition_id"], offset=float(dr["offset"]),
                 width=float(dr["width"]), swing=dr.get("swing", "left"))
            for dr in d.get("doors", [])
        ],
        placements=[_placement(p) for p in d.get("placements", [])],
        plates={pid: plate_from_dict(pl) for pid, pl in (d.get("plates") or {}).items()},
        program_ref=Program(
            lines=[ProgramLine(room_type=ln["room_type"], target=int(ln["target"]), label=ln.get("label"))
                   for ln in prog.get("lines", [])],
            headcount=prog.get("headcount"),
            density_rsf_per_person=prog.get("density_rsf_per_person"),
        ),
    )


def build_command(req: dict, resolve_plate: Callable[[str], Plate]) -> cmds.Command:
    """Turn a `{type, ...args}` request into a Command. Plate-taking commands carry a `plate_id`
    that is resolved to a real Plate here (so the browser only sends an id, never plate geometry)."""
    t = req.get("type")
    if t == "change_room_type":
        return cmds.ChangeRoomType(zone_id=req["zone_id"], new_type=req["new_type"])
    if t == "swap_plate":
        return cmds.SwapPlate(placement_id=req["placement_id"], plate=resolve_plate(req["plate_id"]))
    if t == "set_open_enclosed":
        plate = resolve_plate(req["plate_id"]) if req.get("plate_id") else None
        return cmds.SetOpenEnclosed(zone_id=req["zone_id"], enclosed=bool(req["enclosed"]), plate=plate)
    if t == "merge_zones":
        plate = resolve_plate(req["merged_plate_id"]) if req.get("merged_plate_id") else None
        return cmds.MergeZones(a_id=req["a_id"], b_id=req["b_id"], merged_plate=plate)
    if t == "move_item":
        return cmds.MoveItem(placement_id=req["placement_id"], item_ref=int(req["item_ref"]),
                             dx=float(req["dx"]), dy=float(req["dy"]))
    if t == "rotate_item":
        return cmds.RotateItem(placement_id=req["placement_id"], item_ref=int(req["item_ref"]),
                               delta=float(req["delta"]))
    if t == "delete_item":
        return cmds.DeleteItem(placement_id=req["placement_id"], item_ref=int(req["item_ref"]))
    if t == "edit_door":
        return cmds.EditDoor(door_id=req["door_id"], offset=req.get("offset"), flip_swing=bool(req.get("flip_swing", False)))
    raise SceneError("unknown_command", f"Unknown command type {t!r}.")
