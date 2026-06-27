"""Quantity-takeoff router — upload a floor plate, get a multi-sheet .xlsx bill of materials.

Same input contract as `/api/testfit/quote` (CAD file + program params); chains
floor-plate ingest -> mixed test-fit -> takeoff workbook, and streams the xlsx back.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..takeoff.service import build_takeoff_workbook
from ..testfit.layout import generate_mixed_layout
from .testfit import _parse_plan, _spec_and_program

router = APIRouter(prefix="/api/testfit", tags=["takeoff"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/takeoff")
async def testfit_to_takeoff(
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

    wb = build_takeoff_workbook(db, plan, fit)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="quantity-takeoff.xlsx"'},
    )
