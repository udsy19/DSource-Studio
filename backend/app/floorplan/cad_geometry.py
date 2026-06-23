"""Faithful CAD geometry extraction — render the ACTUAL drawing, not a generated test-fit.

Flattens every drawable entity in a DXF/DWG (lines, polylines, arcs, circles, and the
geometry inside block INSERTs — i.e. the real furniture) into 2D polylines in FEET, with the
source layer. This structured geometry drives both the 2D viewer (draw the paths) and the 3D
viewer (extrude walls tall, furniture/other low). Block INSERTs are exploded via
`virtual_entities()` so the chairs/desks already drawn in a furniture plan come through.
"""

from __future__ import annotations

import io

import ezdxf
import ezdxf.recover
from ezdxf import path as ezpath

from .dxf_ingest import _INSUNITS_TO_FEET, _UNIT_NAME, _dwg_to_dxf_bytes

# entity types we flatten directly; INSERT is exploded; TEXT/DIMENSION/HATCH are skipped
_DRAW_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}
_FLATTEN = 1.0  # flattening tolerance in drawing units
_WALL_HINTS = ("wall", "partition", "wll", "a-wall", "glaz")


def _entity_paths(e, depth: int = 0) -> list[tuple]:
    out: list[tuple] = []
    t = e.dxftype()
    if t == "INSERT" and depth < 5:
        try:
            for ve in e.virtual_entities():
                out.extend(_entity_paths(ve, depth + 1))
        except Exception:  # noqa: BLE001
            pass
        return out
    if t not in _DRAW_TYPES:
        return out
    try:
        p = ezpath.make_path(e)
        pts = [(v.x, v.y) for v in p.flattening(_FLATTEN)]
        if len(pts) >= 2:
            out.append((pts, str(getattr(e.dxf, "layer", "0")), bool(p.is_closed)))
    except Exception:  # noqa: BLE001
        pass
    return out


def extract_geometry(content: bytes, filename: str, max_paths: int = 14000) -> dict:
    if (filename or "").lower().endswith(".dwg"):
        content = _dwg_to_dxf_bytes(content)
    if isinstance(content, bytes):
        doc, _ = ezdxf.recover.read(io.BytesIO(content))
    else:
        doc, _ = ezdxf.recover.readfile(content)
    msp = doc.modelspace()

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    lf = _INSUNITS_TO_FEET.get(insunits, 1.0)

    raw: list[tuple] = []
    for e in msp:
        raw.extend(_entity_paths(e))
        if len(raw) >= max_paths:
            break
    truncated = len(raw) >= max_paths

    paths: list[dict] = []
    layers: dict[str, int] = {}
    minx = miny = 1e18
    maxx = maxy = -1e18
    for pts, layer, closed in raw:
        fpts = [[round(x * lf, 2), round(y * lf, 2)] for (x, y) in pts]
        for x, y in fpts:
            minx, miny = min(minx, x), min(miny, y)
            maxx, maxy = max(maxx, x), max(maxy, y)
        is_wall = any(k in layer.lower() for k in _WALL_HINTS)
        layers[layer] = layers.get(layer, 0) + 1
        paths.append({"pts": fpts, "layer": layer, "closed": closed, "wall": is_wall})

    bounds = (
        {"minx": round(minx, 1), "miny": round(miny, 1), "maxx": round(maxx, 1), "maxy": round(maxy, 1)}
        if paths else None
    )
    return {
        "units": _UNIT_NAME.get(insunits, "unknown"),
        "path_count": len(paths),
        "truncated": truncated,
        "layers": layers,
        "bounds": bounds,
        "paths": paths,
    }
