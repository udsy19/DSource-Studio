"""Alternatives router — upload a floor plate, get 3 scored test-fit options (A/B/C).

Same upload contract as POST /api/testfit (a .dxf/.dwg vector plate + an optional program), but
instead of one layout it returns three distinct ones, each scored on the same space metrics —
the data behind a Space Planning Report. No catalog/quote work here, so no DB dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..floorplan.dxf_ingest import ingest_cad
from ..testfit.alternatives import generate_alternatives
from ..testfit.layout import ProgramSpec

router = APIRouter(prefix="/api/testfit", tags=["alternatives"])


@router.post("/alternatives")
async def generate_testfit_alternatives(
    file: UploadFile = File(...),
    headcount: int | None = Form(None),
    density_rsf_per_person: float = Form(175.0),
):
    if not (file.filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg vector floor plate.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        plan = ingest_cad(content, file.filename or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not parse CAD file: {exc}") from exc

    program = ProgramSpec(
        headcount=headcount if (headcount and headcount > 0) else None,
        density_rsf_per_person=density_rsf_per_person,
    )
    return generate_alternatives(plan, program)
