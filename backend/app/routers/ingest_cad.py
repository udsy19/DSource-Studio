"""CAD element-reader route — upload a real DWG/DXF, get the structured ExtractedLayout.

This is the deterministic "read the actual design" path: walls, doors, rooms and the full
furniture inventory are recovered from layers and named blocks (see ingestion.cad_reader).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..ingestion.cad_reader import read_cad
from ..ingestion.schema import ExtractedLayout

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _parse_seeds(seeds: str | None) -> list[dict] | None:
    """User-dropped room markers, sent as a JSON array of {type, label, x, y} (feet, +y up). These
    become extra segmentation seeds so the user can say 'the IT room is here', overriding detection."""
    if not seeds:
        return None
    try:
        parsed = json.loads(seeds)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="`seeds` must be valid JSON.")
    if not isinstance(parsed, list):
        raise HTTPException(status_code=422, detail="`seeds` must be a JSON array.")
    out: list[dict] = []
    for s in parsed:
        if isinstance(s, dict) and "x" in s and "y" in s:
            out.append({"type": s.get("type"), "label": s.get("label"), "x": s["x"], "y": s["y"]})
    return out or None


@router.post("/cad", response_model=ExtractedLayout)
async def ingest_cad_elements(
    file: UploadFile = File(...), seeds: str | None = Form(None)
) -> ExtractedLayout:
    name = (file.filename or "").lower()
    if not name.endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg CAD file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        return read_cad(content, file.filename or "", user_seeds=_parse_seeds(seeds))
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - surface parse errors at the HTTP boundary
        raise HTTPException(status_code=422, detail=f"Could not read CAD file: {exc}") from exc
