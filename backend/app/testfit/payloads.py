"""JSON-shape builders for the plan + test-fit, shared by the testfit router and the
alternatives module. Pure (no DB/catalog imports) so metric/alternatives code and their tests
stay free of the router's database dependencies — change a shape here and both callers follow.
"""

from __future__ import annotations

from ..floorplan.dxf_ingest import PlanModel
from .layout import TestFit


def plan_payload(plan: PlanModel) -> dict:
    return {
        "boundary": plan.boundary,
        "cores": plan.cores,
        "columns": plan.columns,
        "gross_area_sf": plan.gross_area_sf,
        "usable_area_sf": plan.usable_area_sf,
        "units": plan.units,
    }


def testfit_payload(fit: TestFit) -> dict:
    return {
        "instances": [
            {"type": i.type, "x": i.x, "y": i.y, "w": i.w, "h": i.h, "rotation": i.rotation}
            for i in fit.instances
        ],
        "workstation_count": fit.workstation_count,
        "office_count": fit.office_count,
        "meeting_count": fit.meeting_count,
        "collab_count": fit.collab_count,
        "placeable_area_sf": fit.placeable_area_sf,
        "program": fit.program,
        "notes": fit.notes,
    }
