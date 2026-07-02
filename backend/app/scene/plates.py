"""Bridge the derived Steelcase plate library (testfit.settings) to the scene's Plate contract.

The scene references plates by id and needs the `Plate` shape (model.Plate) for swap/re-fit; the
library stores them as `Setting`s. This adapts one to the other and exposes the two lookups the
router needs: resolve one plate by id, and pick the plates that fit a zone (the Layouts panel).
"""

from __future__ import annotations

from ..testfit.settings import Setting, load_settings, settings_for
from .model import Plate, PlateItem, SceneError


def plate_from_setting(s: Setting) -> Plate:
    """A library Setting → the scene's Plate. `setting_type` IS the scene room_type vocabulary
    (private_office/meeting_room/collaboration/open); items are already posed relative to the
    footprint min-corner, which is the placement origin the scene uses."""
    return Plate(
        id=s.id, room_type=s.setting_type, sqft=s.sqft,
        width_ft=s.width_ft, height_ft=s.height_ft, capacity=s.capacity,
        items=[
            PlateItem(category=f.category, model=f.model, dx=f.dx, dy=f.dy, w=f.w, h=f.h, rotation=f.rotation)
            for f in s.furniture
        ],
    )


def resolve_plate(plate_id: str) -> Plate:
    """Look up a plate by id from the library (raises SceneError if it's not a known plate)."""
    for s in load_settings():
        if s.id == plate_id:
            return plate_from_setting(s)
    raise SceneError("unknown_plate", f"No plate {plate_id!r} in the library.")


def pick_plates(room_type: str, max_w: float, max_h: float) -> list[Plate]:
    """Plates of `room_type` that fit within `max_w × max_h` in either orientation — the Layouts
    panel for a selected zone. Ordered largest-first by settings_for (best use of the footprint)."""
    return [plate_from_setting(s) for s in settings_for(load_settings(), room_type, max_w, max_h)]
