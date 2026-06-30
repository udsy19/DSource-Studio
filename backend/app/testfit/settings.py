"""Steelcase settings library — real, SKU-tagged furnished rooms as generator building blocks.

A Steelcase "application" DWG (Private Office, Conference Room, Workstation pod, …) is a complete,
professionally-designed room. `read_cad` already turns one into an `ExtractedLayout` whose furniture
carries category/brand/model(SKU)/list_price + footprint. This module distils that into a `Setting`:
a `setting_type` + footprint + furniture posed RELATIVE to the footprint's min-corner, so the
generator can drop a real room at any program-room origin instead of leaving a parametric box.

The library is built offline (`build_library`) from a directory of application DWGs and persisted to
a gitignored JSON; at runtime `load_settings()` reads it (or returns [] when absent, so the engine
degrades to the parametric path with no library present).
"""

from __future__ import annotations

import bisect
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..ingestion.schema import ExtractedLayout

# Setting types align with the generator's enclosed-room instance types so slotting matches by
# equality. "open" is a workstation field — kept OUT of room slotting (the open plan stays as-is).
SLOTTABLE_TYPES = ("private_office", "meeting_room", "collaboration")

# Steelcase library folders (and manifest setting_types) -> our generator setting_type. The library
# is organized by Steelcase's own categories, which are far more reliable than inferring from the
# (often sparse) furniture mix. Anything unmapped falls back to furniture-mix inference.
_TYPE_MAP = {
    "private-office": "private_office",
    "focus-room": "private_office",
    "work-from-home": "private_office",
    "meeting-spaces": "meeting_room",
    "classrooms-learning": "meeting_room",
    "workstations": "open",
    "cafe": "collaboration",
    "open-touchdown": "collaboration",
    "respite-wellbeing-spaces": "collaboration",
    "support-spaces": "collaboration",
    "outdoor": "collaboration",
}


def _folder_type(folder_name: str) -> str | None:
    """Map a Steelcase library folder name to a generator setting_type (None when unmapped)."""
    return _TYPE_MAP.get(folder_name.strip().lower())


@dataclass
class SettingFurniture:
    """One piece of a setting, posed relative to the setting footprint's min-corner."""

    category: str
    brand: str | None
    model: str | None
    list_price: float | None
    dx: float
    dy: float
    w: float
    h: float
    rotation: float
    # real plan geometry as polylines relative to the setting min-corner (empty = footprint only),
    # so a slotted/swapped piece can render its true shape at any target origin.
    outline: list[list[tuple[float, float]]] = field(default_factory=list)


@dataclass
class Setting:
    id: str
    setting_type: str
    sqft: float
    width_ft: float
    height_ft: float
    furniture: list[SettingFurniture] = field(default_factory=list)


def infer_setting_type(furniture: list[SettingFurniture], sqft: float) -> str:
    """Coarsely classify a furnished room from its furniture mix + footprint.

    Order matters (first match wins): a lounge (sofa) reads as collaboration; a table ringed by
    >=4 seats is a meeting room; >=2 desks with no table is an open workstation field; a single
    desk is a private office (small offices sit well under ~150 sf). Everything else falls back to
    collaboration. `sqft` is accepted so the heuristic can be refined per band without callers
    changing; today it only documents why a lone desk reads as a private office.
    """
    cats = Counter(f.category for f in furniture)
    desks = cats["desk"] + cats["workstation"]
    seats = cats["chair"] + cats["stool"]
    tables = cats["table"]
    sofas = cats["sofa"]

    if sofas >= 1:
        return "collaboration"
    if tables >= 1 and seats >= 4:
        return "meeting_room"
    if desks >= 2:
        return "open"
    if desks >= 1:
        return "private_office"
    return "collaboration"


def build_setting(layout: ExtractedLayout, setting_id: str, setting_type: str | None = None) -> Setting | None:
    """Distil one application ExtractedLayout into a Setting (None when it carries no furniture).

    The footprint is the furniture bounding box; each item's pose is stored relative to that box's
    min-corner so the setting can be dropped at any room origin. `setting_type`, when given (from the
    Steelcase library folder), overrides furniture-mix inference.
    """
    items = layout.furniture
    if not items:
        return None

    minx = min(f.x for f in items)
    miny = min(f.y for f in items)
    maxx = max(f.x + f.w for f in items)
    maxy = max(f.y + f.h for f in items)
    width_ft = round(maxx - minx, 2)
    height_ft = round(maxy - miny, 2)
    sqft = round(width_ft * height_ft, 1)

    furniture = [
        SettingFurniture(
            category=f.category, brand=f.brand, model=f.model, list_price=f.list_price,
            dx=round(f.x - minx, 2), dy=round(f.y - miny, 2),
            w=round(f.w, 2), h=round(f.h, 2), rotation=round(f.rotation, 1),
            # outline is world-coord; re-base to the setting min-corner so it travels with the piece
            outline=[[(round(px - minx, 2), round(py - miny, 2)) for (px, py) in ring] for ring in f.outline],
        )
        for f in items
    ]
    return Setting(
        id=setting_id,
        setting_type=setting_type or infer_setting_type(furniture, sqft),
        sqft=sqft, width_ft=width_ft, height_ft=height_ft, furniture=furniture,
    )


@dataclass
class Product:
    """One unique furniture SKU across the library — a swap alternative for a piece of that category."""

    category: str
    brand: str | None
    model: str | None
    list_price: float | None
    w: float
    h: float
    outline: list[list[tuple[float, float]]] = field(default_factory=list)


def build_products(settings: list[Setting]) -> list[Product]:
    """Distinct REAL furniture SKUs across all settings — the pool of item-swap alternatives, each
    with a representative size + geometry. Only spec'd items (a model/SKU) are products; un-spec'd
    CET sub-parts (category 'other', no model) are construction geometry, not swappable furniture."""
    seen: dict[tuple, Product] = {}
    for s in settings:
        for f in s.furniture:
            if not f.model:  # no SKU -> a sub-part, not a catalog product
                continue
            key = (f.brand or "", f.model, f.category)
            if key not in seen:
                # a $0 CET spec means "no standalone price", not free — normalize to None so it reads
                # as unpriced everywhere (never fabricate a price).
                price = f.list_price if (f.list_price or 0) > 0 else None
                seen[key] = Product(
                    category=f.category, brand=f.brand, model=f.model, list_price=price,
                    w=f.w, h=f.h, outline=f.outline,
                )
    return list(seen.values())


def settings_for(settings: list[Setting], setting_type: str, max_w: float, max_h: float,
                 tol: float = 0.5) -> list[Setting]:
    """Settings of `setting_type` whose footprint fits within (max_w, max_h) — room-swap alternatives,
    largest first (best fill of the room)."""
    fit = [
        s for s in settings
        if s.setting_type == setting_type and s.width_ft <= max_w + tol and s.height_ft <= max_h + tol
    ]
    return sorted(fit, key=lambda s: s.sqft, reverse=True)


def products_for(products: list[Product], category: str) -> list[Product]:
    """Item-swap alternatives for a category — substantial priced pieces first, unpriced last (so
    nominal $1 CET placeholders don't lead the list)."""
    return sorted(
        (p for p in products if p.category == category),
        key=lambda p: (p.list_price is None, -(p.list_price or 0.0)),
    )


def _settings_dir() -> Path:
    """Directory holding the application plans (in type subfolders) + the built settings.json.
    $STEELCASE_DIR overrides; otherwise prefer the converted `steelcase-dxf/` library (read directly,
    no ODA conversion needed), then the raw `steelcase/` DWGs, then data/steelcase."""
    env = os.environ.get("STEELCASE_DIR")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parents[3]
    for candidate in (root / "steelcase-dxf", root / "steelcase", root / "data" / "steelcase"):
        if candidate.exists():
            return candidate
    return root / "data" / "steelcase"


def _settings_path() -> Path:
    return _settings_dir() / "settings.json"


# ── per-SKU real geometry ──────────────────────────────────────────────────
# The Steelcase product-model library (one DXF per SKU under 3d-models-cad/<Category>/<SKU>.dxf)
# lets a slotted/swapped piece render its TRUE plan shape instead of a footprint box.
_MIN_BASE = 6  # shortest shared prefix we'll accept as the same product family
_symbol_paths: dict[str, Path] | None = None
_symbol_keys: list[str] | None = None


def _models_dir() -> Path:
    """Root of the per-SKU product geometry (DXF preferred, the converted library)."""
    root = Path(__file__).resolve().parents[3]
    return root / "steelcase-dxf" / "3d-models-cad"


def _symbol_index() -> dict[str, Path]:
    """SKU (file stem) -> product DXF path, walked once. Empty when the library isn't present."""
    global _symbol_paths
    if _symbol_paths is None:
        models = _models_dir()
        _symbol_paths = {p.stem: p for p in models.rglob("*.dxf")} if models.exists() else {}
    return _symbol_paths


def _resolve_symbol(sku: str) -> Path | None:
    """Find a product model for a SKU. A configured CET part number (e.g. 419A000) often isn't an
    exact file name but extends or trims the base symbolCode in the library (419A000B2 / COTO96).
    Resolve, in order: exact; a base symbol that is a prefix of the SKU; the shortest indexed variant
    that extends the SKU. Require >= _MIN_BASE shared chars so unrelated products never match."""
    global _symbol_keys
    idx = _symbol_index()
    if sku in idx:
        return idx[sku]
    if len(sku) < _MIN_BASE:
        return None
    for n in range(len(sku) - 1, _MIN_BASE - 1, -1):  # trim trailing option chars -> base symbol
        if sku[:n] in idx:
            return idx[sku[:n]]
    if _symbol_keys is None:
        _symbol_keys = sorted(idx.keys())
    i = bisect.bisect_left(_symbol_keys, sku)  # closest indexed variant that extends the SKU
    best = None
    while i < len(_symbol_keys) and _symbol_keys[i].startswith(sku):
        if best is None or len(_symbol_keys[i]) < len(best):
            best = _symbol_keys[i]
        i += 1
    return idx[best] if best else None


def symbol_outline(sku: str, max_polys: int = 120) -> dict | None:
    """Real plan outline (polylines in feet, re-based to the shape's min-corner) + size for one SKU,
    or None when the SKU has no product model. Reuses the faithful DXF flattener."""
    path = _resolve_symbol(sku)
    if path is None:
        return None
    from ..floorplan.cad_geometry import extract_geometry

    geo = extract_geometry(path.read_bytes(), path.name, max_paths=max_polys)
    paths, b = geo["paths"], geo["bounds"]
    if not paths or not b:
        return None
    minx, miny = b["minx"], b["miny"]
    outline = [[(round(x - minx, 2), round(y - miny, 2)) for (x, y) in p["pts"]] for p in paths]
    return {"outline": outline, "w": round(b["maxx"] - minx, 2), "h": round(b["maxy"] - miny, 2)}


def _application_files(directory: Path) -> list[tuple[Path, str | None]]:
    """The application-plan files to ingest, paired with their folder-derived type. Walks the type
    subfolders (skipping the 3d-models-cad product library — tens of thousands of per-SKU files that
    are geometry, not plans) plus any loose top-level files (flat dir -> type inferred)."""
    files: list[tuple[Path, str | None]] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_dir():
            if entry.name == "3d-models-cad":
                continue
            stype = _folder_type(entry.name)
            files += [(p, stype) for p in sorted(entry.glob("*")) if p.suffix.lower() in (".dwg", ".dxf")]
        elif entry.suffix.lower() in (".dwg", ".dxf"):
            files.append((entry, None))
    return files


def build_library(steelcase_dir: Path | None = None) -> list[Setting]:
    """Ingest every application plan in the library into Settings, taking each setting_type from its
    Steelcase folder when recognized (else inferring). Skips files with no furniture; one bad file
    never aborts the build. Offline-only — `read_cad` is imported lazily so the runtime never pulls
    the CAD stack. Outline is off: footprint is enough for slotting/swap (real geometry comes per-SKU
    from the model library), and per-item outlines for the whole library would bloat settings.json."""
    from ..ingestion.cad_reader import read_cad

    settings: list[Setting] = []
    for path, stype in _application_files(steelcase_dir or _settings_dir()):
        try:
            layout = read_cad(path.read_bytes(), path.name, extract_outline=False)
        except Exception:  # noqa: BLE001 - one bad file shouldn't abort the whole library build
            continue
        setting = build_setting(layout, path.stem, setting_type=stype)
        if setting is not None:
            settings.append(setting)
    return settings


def save_settings(settings: list[Setting], path: Path | None = None) -> Path:
    target = path or _settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([asdict(s) for s in settings], indent=2))
    return target


_settings_cache: list[Setting] | None = None


def _read_settings(source: Path) -> list[Setting]:
    if not source.exists():
        return []
    return [
        Setting(
            id=s["id"], setting_type=s["setting_type"], sqft=s["sqft"],
            width_ft=s["width_ft"], height_ft=s["height_ft"],
            furniture=[SettingFurniture(**f) for f in s["furniture"]],
        )
        for s in json.loads(source.read_text())
    ]


def load_settings(path: Path | None = None) -> list[Setting]:
    """Read the built library, or [] when it's absent — so the engine degrades to parametric.

    The default-path read is cached process-wide (the library is built offline + read-only at
    runtime), so each generate/iterate doesn't re-read and re-parse settings.json from disk. An
    explicit `path` (tests) bypasses the cache."""
    global _settings_cache
    if path is not None:
        return _read_settings(path)
    if _settings_cache is None:
        _settings_cache = _read_settings(_settings_path())
    return _settings_cache
