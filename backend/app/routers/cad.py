"""CAD viewer — render the user's ACTUAL drawing (not a generated test-fit).

/api/cad/svg      -> faithful 2D render of the whole drawing as SVG (ezdxf drawing add-on).
/api/cad/geometry -> flattened 2D paths in feet (walls + furniture) for the 3D extrusion view.

Both accept .dxf or .dwg (DWG converted via LibreDWG).
"""

from __future__ import annotations

import io

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..floorplan.cad_geometry import extract_geometry
from ..floorplan.dxf_ingest import _dwg_to_dxf_bytes

router = APIRouter(prefix="/api/cad", tags=["cad"])


def _accept(filename: str) -> None:
    if not (filename or "").lower().endswith((".dxf", ".dwg")):
        raise HTTPException(status_code=422, detail="Expected a .dxf or .dwg file.")


def _render_svg(content: bytes, filename: str) -> str:
    import ezdxf.recover
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing import svg
    from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration
    from ezdxf.addons.drawing.layout import Page

    if (filename or "").lower().endswith(".dwg"):
        content = _dwg_to_dxf_bytes(content)
    doc, _ = ezdxf.recover.read(io.BytesIO(content))
    msp = doc.modelspace()

    ctx = RenderContext(doc)
    backend = svg.SVGBackend()
    try:
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE)
    except Exception:  # noqa: BLE001 - older ezdxf
        cfg = Configuration()
    Frontend(ctx, backend, config=cfg).draw_layout(msp)
    return backend.get_string(Page(0, 0))


@router.post("/svg")
async def cad_svg(file: UploadFile = File(...)):
    _accept(file.filename or "")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        return {"svg": _render_svg(content, file.filename or ""), "filename": file.filename}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not render CAD: {exc}") from exc


@router.post("/geometry")
async def cad_geometry(file: UploadFile = File(...)):
    _accept(file.filename or "")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    try:
        return extract_geometry(content, file.filename or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Could not extract geometry: {exc}") from exc
