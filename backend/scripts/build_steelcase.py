"""Build the Steelcase settings library (settings.json) from the type-organized DWG folders.

One-time/offline batch: converts every application DWG (cached) and distils it into a Setting with
its folder-derived type, footprint, and SKU-tagged furniture. Prints progress so a long run is
observable. Run: `backend/.venv/bin/python scripts/build_steelcase.py`.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.cad_reader import read_cad  # noqa: E402
from app.testfit.settings import (  # noqa: E402
    _folder_type,
    _settings_dir,
    build_products,
    build_setting,
    save_settings,
)


def main() -> None:
    directory = _settings_dir()
    files = [p for p in sorted(directory.rglob("*")) if p.suffix.lower() in (".dwg", ".dxf")]
    print(f"building from {directory} — {len(files)} files", flush=True)
    settings = []
    t0 = time.time()
    for i, path in enumerate(files, 1):
        stype = _folder_type(path.parent.name)
        try:
            layout = read_cad(path.read_bytes(), path.name, extract_outline=False)
            setting = build_setting(layout, path.stem, setting_type=stype)
            if setting is not None:
                settings.append(setting)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {path.name}: {str(exc)[:60]}", flush=True)
        if i % 25 == 0:
            print(f"  {i}/{len(files)} ({time.time() - t0:.0f}s)", flush=True)
    save_settings(settings)
    products = build_products(settings)
    print("DONE", flush=True)
    print("settings:", len(settings), "types:", dict(Counter(s.setting_type for s in settings)), flush=True)
    print("products:", len(products), "by cat:", dict(Counter(p.category for p in products)), flush=True)


if __name__ == "__main__":
    main()
