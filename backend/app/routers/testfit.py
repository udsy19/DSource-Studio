"""Test-fit router (Phase 2). Upload a .dxf floor plate -> generate a MIXED test-fit.

Chains Phase 1 (floor-plate ingest) -> Phase 2 (placement): the dealer uploads a plate and a
program, and gets back placed instances (workstations + private offices + meeting rooms +
collaboration lounges) with geometry, plus (on /quote) a per-type BOM and budgetary quote.

Both endpoints return the same `plan` + `testfit` geometry contract so a frontend can render
the plan; /quote additionally returns `bom` + `quote`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..floorplan.dxf_ingest import PlanModel, ingest_cad
from ..ingest import service
from ..models import Product
from ..pricing.engine import DealerRates, QuoteLineInput, compute_quote
from ..testfit.layout import ProgramSpec, TestFit, WorkstationSpec, generate_mixed_layout
from ..wellbeing.score import score_wellbeing

router = APIRouter(prefix="/api/testfit", tags=["testfit"])


# --- BOM mapping -------------------------------------------------------------
# Each instance type -> the catalog SKUs it consumes. Chair counts for meeting rooms are
# computed per-instance from room area (~1 seat / 15 sf, capped). All SKUs are looked up by
# `sku`; any missing SKU is skipped gracefully (no 500).
#
# Where a REAL Herman Miller price-book SKU was ingested (base code from the parsed PDF,
# source="pricebook") we use it so the line prices off the real HM list price. Otherwise we
# keep a synthetic-catalog fallback (source="sif"). Each BOM line carries provenance (`real`,
# `source`) so the UI can show which prices are real.
#   Real HM base codes ingested & used: AER1 (Aeron task chair, full base $1726) and PX100
#   (Plex lounge club chair, $866). The sit-to-stand desk and conference-table price books did
#   not parse under the chair-style "Step N." grammar, so desk/table lines stay on the
#   synthetic fallback.
WORKSTATION_SKUS = [
    ("SC-OLOGY-RECT", 1),  # synthetic fallback: desk (HM desk books don't parse)
    ("AER1", 1),           # REAL Herman Miller Aeron task chair (price book)
]
PRIVATE_OFFICE_SKUS = [
    ("HM-RENEW-SS", 1),    # synthetic fallback: sit-to-stand desk
    ("AER1", 1),           # REAL Herman Miller Aeron task chair (price book)
]
MEETING_TABLE_SKU = "HM-EVERYWHERE-6"  # synthetic fallback: conference table (book won't parse)
# REAL Herman Miller Aeron task chair (price book, full base price $1726). We deliberately do
# NOT use the parsed Setu CQN51 here: its starting config came out at $45 because the Setu book's
# base-price step had no captured priced option, so $45 is an incomplete (option-only) figure.
# Aeron parses with its full base, so it's the defensible real meeting-chair price.
MEETING_CHAIR_SKU = "AER1"
COLLAB_SKUS = [
    ("PX100", 1),          # REAL Herman Miller Plex lounge club chair (price book)
    ("KN-RILEY-OTTOMAN", 2),  # synthetic fallback: ottoman (no HM lounge ottoman parsed)
]

_MEETING_SEAT_SF = 15.0
_MEETING_SEAT_CAP = 12


def _plan_payload(plan: PlanModel) -> dict:
    return {
        "boundary": plan.boundary,
        "cores": plan.cores,
        "columns": plan.columns,
        "gross_area_sf": plan.gross_area_sf,
        "usable_area_sf": plan.usable_area_sf,
        "units": plan.units,
    }


def _testfit_payload(fit: TestFit) -> dict:
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


def _sku_demand(fit: TestFit) -> dict[str, int]:
    """Aggregate raw {sku: qty} demand across all placed instances."""
    demand: dict[str, int] = {}

    def add(sku: str, qty: int) -> None:
        if qty <= 0:
            return
        demand[sku] = demand.get(sku, 0) + qty

    for inst in fit.instances:
        if inst.type == "workstation":
            for sku, q in WORKSTATION_SKUS:
                add(sku, q)
        elif inst.type == "private_office":
            for sku, q in PRIVATE_OFFICE_SKUS:
                add(sku, q)
        elif inst.type == "meeting_room":
            seats = min(_MEETING_SEAT_CAP, max(2, int((inst.w * inst.h) / _MEETING_SEAT_SF)))
            add(MEETING_TABLE_SKU, 1)
            add(MEETING_CHAIR_SKU, seats)
        elif inst.type == "collaboration":
            for sku, q in COLLAB_SKUS:
                add(sku, q)
    return demand


def _build_bom_and_quote(db: Session, fit: TestFit):
    """Resolve SKU demand against the catalog -> BOM lines + budgetary quote.

    Missing SKUs are skipped (recorded in `skipped`) rather than 500-ing.
    """
    demand = _sku_demand(fit)
    settings = service.get_settings(db)
    rates = DealerRates(settings.install_rate, settings.freight_rate, settings.tax_rate)

    bom: list[dict] = []
    lines: list[QuoteLineInput] = []
    skipped: list[str] = []
    for sku, qty in demand.items():
        product = db.query(Product).filter(Product.sku == sku).first()
        if product is None:
            skipped.append(sku)
            continue
        category = service.infer_category(product.name)
        # Provenance: a line is REAL when its price came from a parsed manufacturer price book.
        is_real = product.source == "pricebook"
        bom.append({
            "type": category,
            "sku": product.sku,
            "name": product.name,
            "manufacturer_code": product.manufacturer_code,
            "qty": qty,
            "unit_list": product.list_price,
            "real": is_real,
            "source": product.source,
        })
        band = service.resolve_discount(db, product.manufacturer_code, settings, None)
        lines.append(QuoteLineInput(
            product_id=product.id, manufacturer_code=product.manufacturer_code,
            sku=product.sku, name=product.name, qty=qty,
            unit_list=product.list_price, discount_band=band,
        ))

    bom.sort(key=lambda b: b["sku"])
    quote = compute_quote(lines, rates)
    quote_payload = {
        "subtotal_list": quote.subtotal_list,
        "net_merchandise": quote.net_merchandise,
        "install": quote.install,
        "freight": quote.freight,
        "tax": quote.tax,
        "total": quote.total,
        "is_budgetary": quote.is_budgetary,
    }
    return bom, quote_payload, skipped


def _parse_plan(content: bytes, filename: str = "") -> PlanModel:
    try:
        return ingest_cad(content, filename)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not parse CAD file: {exc}") from exc


def _spec_and_program(
    desk_width_ft: float, desk_depth_ft: float, aisle_ft: float,
    perimeter_setback_ft: float, column_clearance_ft: float,
    headcount: int | None, density_rsf_per_person: float,
) -> tuple[WorkstationSpec, ProgramSpec]:
    spec = WorkstationSpec(
        width_ft=desk_width_ft, depth_ft=desk_depth_ft, aisle_ft=aisle_ft,
        perimeter_setback_ft=perimeter_setback_ft, column_clearance_ft=column_clearance_ft,
    )
    program = ProgramSpec(
        headcount=headcount if (headcount and headcount > 0) else None,
        density_rsf_per_person=density_rsf_per_person,
    )
    return spec, program


def _wellbeing_payload(plan: PlanModel, fit: TestFit, density: float) -> dict:
    ws = score_wellbeing(plan, fit, density_rsf_per_person=density)
    return {
        "overall": ws.overall,
        "dimensions": [
            {"key": d.key, "label": d.label, "score": d.score, "basis": d.basis, "measured": d.measured}
            for d in ws.dimensions
        ],
        "notes": ws.notes,
    }


@router.post("")
async def generate_testfit(
    file: UploadFile = File(...),
    desk_width_ft: float = Form(6.0),
    desk_depth_ft: float = Form(5.0),
    aisle_ft: float = Form(3.0),
    perimeter_setback_ft: float = Form(3.0),
    column_clearance_ft: float = Form(1.5),
    headcount: int | None = Form(None),
    density_rsf_per_person: float = Form(175.0),
):
    if not (file.filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg vector floor plate.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    plan = _parse_plan(content, file.filename or "")

    spec, program = _spec_and_program(
        desk_width_ft, desk_depth_ft, aisle_ft, perimeter_setback_ft,
        column_clearance_ft, headcount, density_rsf_per_person,
    )
    fit = generate_mixed_layout(plan, spec, program)

    return {
        "plan": _plan_payload(plan),
        "testfit": _testfit_payload(fit),
        "wellbeing": _wellbeing_payload(plan, fit, density_rsf_per_person),
        "bom": None,
        "quote": None,
        "needs_confirmation": True,
    }


@router.post("/quote")
async def testfit_to_quote(
    file: UploadFile = File(...),
    desk_width_ft: float = Form(6.0),
    desk_depth_ft: float = Form(5.0),
    aisle_ft: float = Form(3.0),
    perimeter_setback_ft: float = Form(3.0),
    column_clearance_ft: float = Form(1.5),
    headcount: int | None = Form(None),
    density_rsf_per_person: float = Form(175.0),
    db: Session = Depends(get_db),
):
    """The full loop: floor plate -> mixed test-fit -> per-type BOM -> budgetary quote, using
    the catalog's real prices + the dealer's discount bands."""
    if not (file.filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg vector floor plate.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    plan = _parse_plan(content, file.filename or "")

    spec, program = _spec_and_program(
        desk_width_ft, desk_depth_ft, aisle_ft, perimeter_setback_ft,
        column_clearance_ft, headcount, density_rsf_per_person,
    )
    fit = generate_mixed_layout(plan, spec, program)
    if not fit.instances:
        raise HTTPException(status_code=422, detail="Test-fit placed no instances.")

    bom, quote_payload, skipped = _build_bom_and_quote(db, fit)
    testfit_payload = _testfit_payload(fit)
    if skipped:
        testfit_payload["notes"] = list(testfit_payload["notes"]) + [
            f"Skipped catalog SKUs not found: {skipped}."
        ]

    return {
        "plan": _plan_payload(plan),
        "testfit": testfit_payload,
        "wellbeing": _wellbeing_payload(plan, fit, density_rsf_per_person),
        "bom": bom,
        "quote": quote_payload,
        "needs_confirmation": True,
    }
