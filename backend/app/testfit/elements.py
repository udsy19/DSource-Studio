"""Element extraction — count the real components in a generated test-fit.

Aggregates placed instances into the furniture, space, and construction counts a client reads off
a plan ("how many chairs, tables, walls, huddle spaces") — the Qbiq-style component breakdown.
Uses the same per-instance furniture rules as the BOM/takeoff, so the counts reconcile with them.
"""

from __future__ import annotations

from ..floorplan.dxf_ingest import PlanModel
from .bom import _MEETING_SEAT_CAP, _MEETING_SEAT_SF
from .layout import FurnitureInstance, TestFit

_ENCLOSED = {"private_office", "meeting_room", "collaboration"}


def _meeting_seats(inst: FurnitureInstance) -> int:
    return min(_MEETING_SEAT_CAP, max(2, int((inst.w * inst.h) / _MEETING_SEAT_SF)))


def extract_elements(plan: PlanModel, fit: TestFit) -> dict:
    chairs = desks = tables = sofas = ottomans = 0
    for inst in fit.instances:
        if inst.type == "workstation":
            desks += 1
            chairs += 1
        elif inst.type == "private_office":
            desks += 1
            chairs += 1
        elif inst.type == "meeting_room":
            tables += 1
            chairs += _meeting_seats(inst)
        elif inst.type == "collaboration":
            sofas += 1
            ottomans += 2

    enclosed = sum(1 for i in fit.instances if i.type in _ENCLOSED)
    perimeter_walls = len(plan.boundary)
    room_partitions = 4 * enclosed  # four sides per enclosed room (offices, meeting, huddle)

    return {
        "furniture": {
            "chairs": chairs,
            "desks": desks,
            "tables": tables,
            "sofas": sofas,
            "ottomans": ottomans,
        },
        "spaces": {
            "workstations": fit.workstation_count,
            "private_offices": fit.office_count,
            "meeting_rooms": fit.meeting_count,
            "huddle_spaces": fit.collab_count,
        },
        "construction": {
            "perimeter_walls": perimeter_walls,
            "room_partitions": room_partitions,
            "walls": perimeter_walls + room_partitions,
        },
    }
