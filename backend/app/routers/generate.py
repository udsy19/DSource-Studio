"""Concept-mode generate router — upload a floor plate + a 4-dial PROGRAM, get 3 test-fit options.

The Qbiq "Concept" flow: instead of the engine's low-level specs, the user sets planning style,
desk type, desk size, and seat distribution. We ingest the CAD plate, translate the program via
`generate_from_concept`, and return the same `AlternativesResult` shape as /api/testfit/alternatives.
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..floorplan.dxf_ingest import ingest_cad
from ..testfit.concept import ConceptProgram, generate_from_concept

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate")
async def generate(
    file: UploadFile = File(...),
    planning_style: str = Form("modern"),
    desk_type: str = Form("workstations"),
    desk_width_cm: int = Form(140),
    desk_depth_cm: int = Form(70),
    closed_ratio: float = Form(0.2),
):
    if not (file.filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg vector floor plate.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")

    try:
        concept = ConceptProgram(
            planning_style=planning_style,
            desk_type=desk_type,
            desk_width_cm=desk_width_cm,
            desk_depth_cm=desk_depth_cm,
            closed_ratio=closed_ratio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid concept program: {exc}") from exc

    try:
        plan = ingest_cad(content, file.filename or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not parse CAD file: {exc}") from exc

    return generate_from_concept(plan, concept)
