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

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..ingestion.schema import ExtractedLayout

# Setting types align with the generator's enclosed-room instance types so slotting matches by
# equality. "open" is a workstation field — kept OUT of room slotting (the open plan stays as-is).
SLOTTABLE_TYPES = ("private_office", "meeting_room", "collaboration")


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


def build_setting(layout: ExtractedLayout, setting_id: str) -> Setting | None:
    """Distil one application ExtractedLayout into a Setting (None when it carries no furniture).

    The footprint is the furniture bounding box; each item's pose is stored relative to that box's
    min-corner so the setting can be dropped at any room origin.
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
        )
        for f in items
    ]
    return Setting(
        id=setting_id,
        setting_type=infer_setting_type(furniture, sqft),
        sqft=sqft, width_ft=width_ft, height_ft=height_ft, furniture=furniture,
    )


def _settings_dir() -> Path:
    """Directory holding the application DWGs + the built settings.json (env or repo default)."""
    env = os.environ.get("STEELCASE_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "data" / "steelcase"


def _settings_path() -> Path:
    return _settings_dir() / "settings.json"


def build_library(steelcase_dir: Path | None = None) -> list[Setting]:
    """Ingest every application DWG/DXF in the directory into Settings (skips files with no
    furniture). Reads from `steelcase_dir` or $STEELCASE_DIR / the repo default. Offline-only —
    `read_cad` is imported lazily so the runtime path never pulls the CAD stack."""
    from ..ingestion.cad_reader import read_cad

    directory = steelcase_dir or _settings_dir()
    settings: list[Setting] = []
    for path in sorted(directory.glob("*")):
        if path.suffix.lower() not in (".dwg", ".dxf"):
            continue
        setting = build_setting(read_cad(path.read_bytes(), path.name), path.stem)
        if setting is not None:
            settings.append(setting)
    return settings


def save_settings(settings: list[Setting], path: Path | None = None) -> Path:
    target = path or _settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps([asdict(s) for s in settings], indent=2))
    return target


def load_settings(path: Path | None = None) -> list[Setting]:
    """Read the built library, or [] when it's absent — so the engine degrades to parametric."""
    source = path or _settings_path()
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
