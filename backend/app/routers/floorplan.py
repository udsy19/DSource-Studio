"""Floor-plate ingestion router (Phase 1).

Upload a vector CAD floor plate (.dxf) and get back the extracted plan model (boundary,
core, columns, gross/usable area) plus a capacity estimate for a given program. The plan
is returned with `needs_confirmation=true` — a human confirms boundary/scale/columns before
a test-fit trusts it (the qbiq/CubiCasa human-in-the-loop pattern).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..floorplan.capacity import Program, estimate_capacity
from ..floorplan.dxf_ingest import ingest_cad

router = APIRouter(prefix="/api/floorplan", tags=["floorplan"])


@router.post("/ingest")
async def ingest_floorplate(
    file: UploadFile = File(...),
    density_rsf_per_person: float = Form(175.0),
    circulation_factor: float = Form(0.35),
):
    """Parse a .dxf floor plate → plan model + capacity estimate."""
    name = (file.filename or "").lower()
    if not name.endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg vector floor plate (IFC/raster deferred).")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        plan = ingest_cad(content, file.filename or "")
    except Exception as exc:  # noqa: BLE001 - surface parse errors
        raise HTTPException(status_code=422, detail=f"Could not parse DXF: {exc}") from exc

    program = Program(
        density_rsf_per_person=density_rsf_per_person,
        circulation_factor=circulation_factor,
    )
    capacity = estimate_capacity(plan.usable_area_sf, program)

    return {
        "plan": asdict(plan),
        "capacity": asdict(capacity),
        "needs_confirmation": plan.needs_confirmation,
    }
