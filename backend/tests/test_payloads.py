"""Plan/fit payload round-trip — a generated version must rebuild into the same PlanModel/TestFit
so its takeoff/IFC export matches what was shown."""

from __future__ import annotations

from app.floorplan.dxf_ingest import PlanModel
from app.testfit.layout import FurnitureInstance, TestFit
from app.testfit.payloads import (
    fit_from_payload,
    plan_from_payload,
    plan_payload,
    testfit_payload as build_testfit_payload,
)


def test_plan_payload_round_trip():
    plan = PlanModel(
        units="ft", sqft_factor=1.0,
        boundary=[(0.0, 0.0), (100.0, 0.0), (100.0, 80.0), (0.0, 80.0)],
        gross_area_sf=8000.0, core_area_sf=500.0, usable_area_sf=7500.0,
        columns=[(10.0, 10.0)], cores=[[(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]],
    )
    back = plan_from_payload(plan_payload(plan))
    assert back.boundary == plan.boundary
    assert back.usable_area_sf == plan.usable_area_sf
    assert back.columns == plan.columns and back.cores == plan.cores
    assert abs(back.core_area_sf - (plan.gross_area_sf - plan.usable_area_sf)) < 1e-6


def test_fit_payload_round_trip():
    fit = TestFit(
        workstation_count=10, office_count=2, meeting_count=1, collab_count=1,
        instances=[FurnitureInstance("workstation", 1.0, 2.0, 3.0, 4.0, 90)],
        placeable_area_sf=5000.0,
    )
    back = fit_from_payload(build_testfit_payload(fit))
    assert back.workstation_count == 10 and back.office_count == 2 and back.collab_count == 1
    assert len(back.instances) == 1
    inst = back.instances[0]
    assert inst.type == "workstation" and inst.rotation == 90 and inst.w == 3.0


def test_sku_fields_round_trip_and_omitted_when_absent():
    """A slotted, SKU-tagged piece carries brand/model/list_price through the payload; a parametric
    instance stays the legacy shape (no SKU keys), so existing payloads are unchanged."""
    fit = TestFit(
        workstation_count=0,
        instances=[
            FurnitureInstance("workstation", 1.0, 2.0, 3.0, 4.0, 0),  # parametric, no SKU
            FurnitureInstance("desk", 5.0, 6.0, 5.0, 2.5, 0,
                              brand="Steelcase", model="OBBORDER05", list_price=1200.0),
        ],
    )
    payload = build_testfit_payload(fit)
    assert set(payload["instances"][0]) == {"type", "x", "y", "w", "h", "rotation"}
    assert payload["instances"][1]["model"] == "OBBORDER05"

    back = fit_from_payload(payload)
    parametric, skued = back.instances
    assert parametric.brand is None and parametric.model is None and parametric.list_price is None
    assert skued.brand == "Steelcase" and skued.model == "OBBORDER05" and skued.list_price == 1200.0
