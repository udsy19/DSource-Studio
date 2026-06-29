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


# ODA File Converter (Open Design Alliance) handles DWGs that LibreDWG mangles — notably Configura
# CET / Steelcase exports, whose anonymous blocks LibreDWG truncates (breaking INSERT->definition
# links). Prefer ODA when present, fall back to LibreDWG. Set ODA_FILE_CONVERTER to override the path.
def _find_oda_converter() -> str | None:
    import os
    import shutil

    candidates = [
        os.environ.get("ODA_FILE_CONVERTER", ""),
        "/Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter",
        "/Applications/ODA File Converter.app/Contents/MacOS/ODAFileConverter",
        shutil.which("ODAFileConverter") or "",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def _dwg_to_dxf_with_oda(oda: str, dwg: bytes) -> bytes:
    """ODA batch-converts a folder, so stage the DWG in its own input dir and read the DXF back.
    Args: in-dir, out-dir, output-version, output-type, recurse, audit, [input-filter].

    ODA is a Qt GUI app. Prefer launching it via `open -g` (background, no focus steal / window
    flash); if that path produces nothing, fall back to invoking the binary directly (which works
    but grabs focus). Either way the result is cached by the caller, so it runs at most once per
    file."""
    import glob
    import os
    import subprocess
    import tempfile

    oda_args = ["ACAD2018", "DXF", "0", "1", "*.DWG"]
    app = oda.split("/Contents/MacOS/")[0] if "/Contents/MacOS/" in oda else ""

    with tempfile.TemporaryDirectory() as ind, tempfile.TemporaryDirectory() as outd:
        with open(os.path.join(ind, "in.dwg"), "wb") as f:
            f.write(dwg)

        def _out() -> str | None:
            outs = glob.glob(os.path.join(outd, "*.dxf")) + glob.glob(os.path.join(outd, "*.DXF"))
            return outs[0] if outs and os.path.getsize(outs[0]) > 0 else None

        cmds = []
        if app.endswith(".app"):  # background launch, no window steal
            cmds.append(["open", "-g", "-W", "-a", app, "--args", ind, outd, *oda_args])
        cmds.append([oda, ind, outd, *oda_args])  # direct call — always works, grabs focus

        for cmd in cmds:
            try:
                subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            except Exception:  # noqa: BLE001 - try the next launch strategy
                continue
            if _out():
                break

        out = _out()
        if not out:
            raise RuntimeError("ODA File Converter produced no DXF.")
        with open(out, "rb") as f:
            return f.read()


def _dwg_to_dxf_bytes(dwg: bytes) -> bytes:
    """Cached DWG -> DXF. Converting launches an external converter (ODA), so cache the result by
    content hash under ~/.cache/dsource/dwg — each unique DWG converts exactly ONCE, ever, so the
    converter never re-launches for a file already seen."""
    import hashlib
    import pathlib

    key = hashlib.sha256(dwg).hexdigest()
    cache_dir = pathlib.Path.home() / ".cache" / "dsource" / "dwg"
    cached = cache_dir / f"{key}.dxf"
    try:
        if cached.exists() and cached.stat().st_size > 0:
            return cached.read_bytes()
    except OSError:
        pass

    dxf = _convert_dwg_to_dxf(dwg)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(dxf)
    except OSError:  # a read-only cache dir must not break conversion
        pass
    return dxf


def _convert_dwg_to_dxf(dwg: bytes) -> bytes:
    """Convert DWG -> DXF (ezdxf can't read DWG natively). Prefer ODA File Converter (handles CET/
    Steelcase exports); fall back to LibreDWG's dwg2dxf (`brew install libredwg`)."""
    import os
    import shutil
    import subprocess
    import tempfile

    oda = _find_oda_converter()
    if oda:
        try:
            return _dwg_to_dxf_with_oda(oda, dwg)
        except Exception:  # noqa: BLE001 - ODA failed; try LibreDWG before giving up
            pass

    if shutil.which("dwg2dxf") is None:
        raise RuntimeError(
            "DWG files need a converter. Install ODA File Converter, or LibreDWG "
            "(`brew install libredwg` on macOS) which provides dwg2dxf — then re-upload."
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


def _read_dxf_doc(dxf: bytes):
    """Parse DXF bytes into an ezdxf doc, ROBUSTLY. Real-world exports split two ways: some are read
    only by the strict `ezdxf.readfile` (which `recover` silently drops to an empty modelspace — e.g.
    Steelcase application plans), others only by `ezdxf.recover` (which tolerates the binary/encoded
    sections + malformed group codes that break the strict reader). Try both from a temp file and
    keep whichever yields the most modelspace entities."""
    import os
    import tempfile

    import ezdxf
    import ezdxf.recover

    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tf:
        tf.write(dxf)
        path = tf.name
    try:
        best = None
        best_n = -1
        for reader in (lambda: ezdxf.readfile(path), lambda: ezdxf.recover.readfile(path)[0]):
            try:
                doc = reader()
                n = sum(1 for _ in doc.modelspace())
            except Exception:  # noqa: BLE001 - one reader failing is expected; the other may work
                continue
            if n > best_n:
                best, best_n = doc, n
        if best is None:
            raise RuntimeError("Could not parse the DXF with either ezdxf reader (readfile/recover).")
        return best
    finally:
        os.unlink(path)


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
