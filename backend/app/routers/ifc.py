"""IFC export router — upload a floor plate, get an IFC4 BIM model of the test-fit.

Same input contract as `/api/testfit/quote` (CAD file + program params); chains floor-plate
ingest -> mixed test-fit -> IFC authoring, and streams the .ifc back. IFC is the open-standard
deliverable (a native .rvt would need paid Autodesk Platform Services).
"""

from __future__ import annotations

import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..ifc.service import build_ifc
from ..testfit.layout import generate_mixed_layout
from .testfit import _parse_plan, _spec_and_program

router = APIRouter(prefix="/api/testfit", tags=["ifc"])


@router.post("/ifc")
async def testfit_to_ifc(
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
    if not fit.instances:
        raise HTTPException(status_code=422, detail="Test-fit placed no instances.")

    data = build_ifc(plan, fit, project_name=(file.filename or "DSource Studio"))
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/x-step",
        headers={"Content-Disposition": 'attachment; filename="model.ifc"'},
    )
