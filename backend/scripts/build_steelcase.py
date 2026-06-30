"""Build the Steelcase settings library (settings.json) from the type-organized plan folders.

One-time/offline batch: distils every application plan into a Setting (folder-derived type, footprint,
SKU-tagged furniture) and writes settings.json next to the library. Reads the converted DXF library
when present (no ODA). Run: `backend/.venv/bin/python scripts/build_steelcase.py`.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.testfit.settings import (  # noqa: E402
    _application_files,
    _settings_dir,
    build_library,
    build_products,
    save_settings,
)


def main() -> None:
    directory = _settings_dir()
    print(f"building from {directory} — {len(_application_files(directory))} application plans", flush=True)
    settings = build_library()
    save_settings(settings)
    products = build_products(settings)
    print("settings:", len(settings), "types:", dict(Counter(s.setting_type for s in settings)), flush=True)
    print("products:", len(products), "by cat:", dict(Counter(p.category for p in products)), flush=True)


if __name__ == "__main__":
    main()
