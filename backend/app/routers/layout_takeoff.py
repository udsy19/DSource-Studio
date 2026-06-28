"""Layout takeoff router — upload a real DWG/DXF, get the Qbiq-grade multi-sheet .xlsx takeoff.

Reads the actual CAD elements (read_cad -> ExtractedLayout), then builds the takeoff workbook
straight from the recovered geometry. No DB, no test-fit generation.
"""

from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..ingestion.cad_reader import read_cad
from ..takeoff.layout_takeoff import build_layout_takeoff

router = APIRouter(prefix="/api/ingest", tags=["takeoff"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/takeoff")
async def layout_to_takeoff(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg CAD file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        layout = read_cad(content, file.filename or "")
    except Exception as exc:  # noqa: BLE001 - surface parse errors at the HTTP boundary
        raise HTTPException(status_code=422, detail=f"Could not read CAD file: {exc}") from exc

    wb = build_layout_takeoff(layout)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="layout-takeoff.xlsx"'},
    )
