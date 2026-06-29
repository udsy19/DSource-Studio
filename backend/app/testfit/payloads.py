"""JSON-shape builders for the plan + test-fit, shared by the testfit router and the
alternatives module. Pure (no DB/catalog imports) so metric/alternatives code and their tests
stay free of the router's database dependencies — change a shape here and both callers follow.
"""

from __future__ import annotations

from ..floorplan.dxf_ingest import PlanModel
from .layout import FurnitureInstance, TestFit


def plan_payload(plan: PlanModel) -> dict:
    return {
        "boundary": plan.boundary,
        "cores": plan.cores,
        "columns": plan.columns,
        "gross_area_sf": plan.gross_area_sf,
        "usable_area_sf": plan.usable_area_sf,
        "units": plan.units,
    }


def _instance_payload(i: FurnitureInstance) -> dict:
    """Serialize one instance; SKU fields appear only when present so parametric instances (and
    the existing payload shape) are unchanged."""
    d = {"type": i.type, "x": i.x, "y": i.y, "w": i.w, "h": i.h, "rotation": i.rotation}
    if i.brand is not None:
        d["brand"] = i.brand
    if i.model is not None:
        d["model"] = i.model
    if i.list_price is not None:
        d["list_price"] = i.list_price
    return d


def testfit_payload(fit: TestFit) -> dict:
    return {
        "instances": [_instance_payload(i) for i in fit.instances],
        "workstation_count": fit.workstation_count,
        "office_count": fit.office_count,
        "meeting_count": fit.meeting_count,
        "collab_count": fit.collab_count,
        "placeable_area_sf": fit.placeable_area_sf,
        "program": fit.program,
        "notes": fit.notes,
    }


def plan_from_payload(d: dict) -> PlanModel:
    """Rebuild a PlanModel from a `plan_payload` dict — so a generated version can be exported
    without re-running ingestion. core_area is recovered as gross − usable."""
    gross = float(d.get("gross_area_sf", 0.0))
    usable = float(d.get("usable_area_sf", gross))
    return PlanModel(
        units=d.get("units", "ft"),
        sqft_factor=1.0,
        boundary=[(float(x), float(y)) for x, y in d.get("boundary", [])],
        gross_area_sf=gross,
        core_area_sf=max(0.0, gross - usable),
        usable_area_sf=usable,
        columns=[(float(x), float(y)) for x, y in d.get("columns", [])],
        cores=[[(float(x), float(y)) for x, y in core] for core in d.get("cores", [])],
    )


def fit_from_payload(d: dict) -> TestFit:
    """Rebuild a TestFit from a `testfit_payload` dict — the inverse of testfit_payload."""
    return TestFit(
        workstation_count=int(d.get("workstation_count", 0)),
        office_count=int(d.get("office_count", 0)),
        meeting_count=int(d.get("meeting_count", 0)),
        collab_count=int(d.get("collab_count", 0)),
        instances=[
            FurnitureInstance(
                type=i["type"], x=float(i["x"]), y=float(i["y"]),
                w=float(i["w"]), h=float(i["h"]), rotation=int(i.get("rotation", 0)),
                brand=i.get("brand"), model=i.get("model"),
                list_price=float(i["list_price"]) if i.get("list_price") is not None else None,
            )
            for i in d.get("instances", [])
        ],
        placeable_area_sf=float(d.get("placeable_area_sf", 0.0)),
    )
