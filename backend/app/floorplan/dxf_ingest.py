"""Floor-plate ingestion from vector CAD (DXF) — Phase 1 core.

Per the research, vector ingestion (DXF/IFC) is the tractable path; raster/PDF vectorization
is the unsolved, error-prone part and is deferred. Even for vector input we follow the
qbiq/CubiCasa pattern: extract a best-effort plan, then require a HUMAN to confirm the
boundary/scale/columns before anything downstream trusts it (`needs_confirmation`).

What we extract from a DXF:
  * units (DXF header $INSUNITS) → convert areas to square feet
  * exterior boundary  = the largest-area closed polyline
  * service core(s)    = closed polylines fully inside the boundary (subtracted from usable)
  * structural columns = CIRCLE entities (+ block INSERTs on column-ish layers)
  * gross / usable area via Shapely

Open polylines/lines (partitions) are ignored for the boundary. If no closed boundary
polyline exists we fall back to the drawing extents (a coarse gross envelope) and flag it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import ezdxf
from shapely.geometry import Point, Polygon

# DXF $INSUNITS → square-feet conversion factor for an area measured in those units.
_INSUNITS_TO_SQFT = {
    0: 1.0,            # unitless — assume already in feet
    1: 1.0 / 144.0,    # inches → sq ft
    2: 1.0,            # feet
    4: 1.0 / 92903.04, # mm → sq ft
    5: 1.0 / 929.0304, # cm → sq ft
    6: 10.7639104,     # meters → sq ft
}
_UNIT_NAME = {0: "unknown", 1: "inches", 2: "feet", 4: "mm", 5: "cm", 6: "meters"}
# LINEAR unit -> feet. We scale every coordinate by this so downstream engines (layout,
# wellbeing, 3D), which all assume feet, are unit-correct.
_INSUNITS_TO_FEET = {
    0: 1.0,             # unitless — assume feet
    1: 1.0 / 12.0,      # inches
    2: 1.0,             # feet
    4: 1.0 / 304.8,     # mm
    5: 1.0 / 30.48,     # cm
    6: 3.280839895,     # meters
}

_COLUMN_LAYER_HINTS = ("col", "s-col", "column", "struct")


@dataclass
class PlanModel:
    units: str
    sqft_factor: float
    boundary: list[tuple[float, float]]
    gross_area_sf: float
    core_area_sf: float
    usable_area_sf: float
    columns: list[tuple[float, float]] = field(default_factory=list)
    cores: list[list[tuple[float, float]]] = field(default_factory=list)
    boundary_source: str = "polyline"  # polyline | extents
    needs_confirmation: bool = True
    notes: list[str] = field(default_factory=list)


def _closed_polylines(msp) -> list[Polygon]:
    polys: list[Polygon] = []
    for e in msp.query("LWPOLYLINE"):
        if not e.closed:
            continue
        pts = [(p[0], p[1]) for p in e.get_points()]
        if len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 0:
                polys.append(poly)
    for e in msp.query("POLYLINE"):
        try:
            pts = [(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices]
        except Exception:  # noqa: BLE001
            continue
        if getattr(e, "is_closed", False) and len(pts) >= 3:
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 0:
                polys.append(poly)
    return polys


def _columns(msp, boundary: Polygon) -> list[tuple[float, float]]:
    cols: list[tuple[float, float]] = []
    for e in msp.query("CIRCLE"):
        c = (e.dxf.center[0], e.dxf.center[1])
        if boundary is None or boundary.contains(Point(c)):
            cols.append(c)
    for e in msp.query("INSERT"):
        layer = str(getattr(e.dxf, "layer", "")).lower()
        if any(h in layer for h in _COLUMN_LAYER_HINTS):
            c = (e.dxf.insert[0], e.dxf.insert[1])
            if boundary is None or boundary.contains(Point(c)):
                cols.append(c)
    return cols


def ingest_cad(content: bytes, filename: str) -> PlanModel:
    """Ingest a CAD floor plate from DXF or DWG. DWG (binary AutoCAD) is converted to DXF
    first via LibreDWG; everything downstream is format-agnostic."""
    if (filename or "").lower().endswith(".dwg"):
        content = _dwg_to_dxf_bytes(content)
    return ingest_dxf(content)


def _dwg_to_dxf_bytes(dwg: bytes) -> bytes:
    """Convert DWG -> DXF using LibreDWG's dwg2dxf CLI (ezdxf can't read DWG natively).
    Install on macOS with `brew install libredwg`; on Debian/Ubuntu `apt install libredwg-tools`."""
    import os
    import shutil
    import subprocess
    import tempfile

    if shutil.which("dwg2dxf") is None:
        raise RuntimeError(
            "DWG files need a converter. Install LibreDWG (`brew install libredwg` on macOS) — "
            "it provides the dwg2dxf command — then re-upload."
        )
    with tempfile.TemporaryDirectory() as d:
        dwg_path, dxf_path = os.path.join(d, "in.dwg"), os.path.join(d, "out.dxf")
        with open(dwg_path, "wb") as f:
            f.write(dwg)
        subprocess.run(["dwg2dxf", "-o", dxf_path, dwg_path], capture_output=True, text=True, timeout=180)
        if not os.path.exists(dxf_path) or os.path.getsize(dxf_path) == 0:
            raise RuntimeError("dwg2dxf could not convert this DWG (unsupported version?).")
        with open(dxf_path, "rb") as f:
            return f.read()


def ingest_dxf(source: bytes | str) -> PlanModel:
    # Use ezdxf.recover — it auto-detects encoding and tolerates the binary/encoded sections
    # and structure quirks real-world CAD exports contain. Decoding bytes as UTF-8 by hand
    # corrupts such files; recover.read() reads from a binary stream correctly.
    import ezdxf.recover

    if isinstance(source, bytes):
        doc, _auditor = ezdxf.recover.read(io.BytesIO(source))
    else:
        doc, _auditor = ezdxf.recover.readfile(source)
    msp = doc.modelspace()

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    lf = _INSUNITS_TO_FEET.get(insunits, 1.0)   # linear drawing-units -> feet
    units = _UNIT_NAME.get(insunits, "unknown")
    notes: list[str] = []

    polys = _closed_polylines(msp)
    if polys:
        boundary_poly = max(polys, key=lambda p: p.area)
        boundary_source = "polyline"
        cores = [p for p in polys if p is not boundary_poly and boundary_poly.contains(p.centroid)
                 and p.area < boundary_poly.area * 0.5]
    else:
        from ezdxf.bbox import extents as _extents
        box = _extents(msp)
        (minx, miny, _), (maxx, maxy, _) = box.extmin, box.extmax
        boundary_poly = Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)])
        cores = []
        boundary_source = "extents"
        notes.append("No closed boundary polyline found — used drawing extents (coarse; may include title block).")

    columns = _columns(msp, boundary_poly)   # filtered in raw units (consistent with boundary)

    # Normalize ALL geometry to FEET. The layout/wellbeing/3D engines assume feet; leaving
    # coordinates in drawing units (e.g. inches) made the test-fit place ~144x too many desks.
    from shapely.affinity import scale as _affscale
    boundary_poly = _affscale(boundary_poly, xfact=lf, yfact=lf, origin=(0, 0))
    cores = [_affscale(c, xfact=lf, yfact=lf, origin=(0, 0)) for c in cores]
    columns = [(x * lf, y * lf) for (x, y) in columns]

    gross = boundary_poly.area          # already sq ft (coords are feet)
    core_area = sum(c.area for c in cores)
    usable = max(gross - core_area, 0.0)

    notes.append(f"Geometry scaled to feet from drawing units ({units}). "
                 "Confirm boundary, scale and columns before generating a test-fit.")

    return PlanModel(
        units=units, sqft_factor=1.0,
        boundary=[(round(x, 3), round(y, 3)) for x, y in boundary_poly.exterior.coords],
        gross_area_sf=round(gross, 1), core_area_sf=round(core_area, 1),
        usable_area_sf=round(usable, 1),
        columns=[(round(x, 2), round(y, 2)) for x, y in columns],
        cores=[[(round(x, 2), round(y, 2)) for x, y in c.exterior.coords] for c in cores],
        boundary_source=boundary_source, needs_confirmation=True, notes=notes,
    )
