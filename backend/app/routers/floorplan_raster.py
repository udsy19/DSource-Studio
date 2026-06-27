"""Raster/PDF floor-plan ingest router — upload a JPG/PNG/PDF plate, get a PlanModel.

The image counterpart to `/api/floorplan/ingest` (CAD). Returns the plan with
`needs_confirmation=true`; a human confirms the recovered outline and scale before downstream use.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..floorplan.raster import ingest_raster

router = APIRouter(prefix="/api/floorplan", tags=["floorplan"])

_RASTER_EXT = (".png", ".jpg", ".jpeg", ".pdf")


@router.post("/ingest-raster")
async def ingest_raster_plate(
    file: UploadFile = File(...),
    px_per_ft: float | None = Form(None),
):
    if not (file.filename or "").lower().endswith(_RASTER_EXT):
        raise HTTPException(status_code=422, detail="Expected a .png, .jpg, or .pdf floor plate.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        plan = ingest_raster(content, file.filename or "", px_per_ft=px_per_ft)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"plan": asdict(plan), "needs_confirmation": plan.needs_confirmation}
