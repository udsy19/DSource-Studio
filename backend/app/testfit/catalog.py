"""Room catalog for Detailed-mode space planning — Qbiq's room taxonomy with realistic sizes.

A single source of truth mapping a user-facing room TYPE (catalog key) to:
  - the underlying PLACEMENT instance type the packers + downstream metrics understand
    (`private_office`, `meeting_room`, `collaboration`, `phone_booth`, or an amenity type),
  - a realistic footprint in FEET (width x height), and
  - a sensible default placement preference (window / core / flexible).

Detailed (`detailed.py`) consumes this: a RoomRequest names a catalog key; the engine looks the
key up here to get the RoomSpec footprint + instance type, then hands it to the EXISTING placement
packers (`place_perimeter_rooms` / `place_interior_rooms`) unchanged.

INSTANCE TYPES — why several catalog keys share one:
  Many keys are size variants of the same physical room. `office_exec`, `office_large`,
  `office_medium`, `office_small`, `office_focus` and all team offices are placed as
  `private_office` (an enclosed seat). Every conference size is a `meeting_room`. The packers and
  the metrics (seat / enclosed / daylight) reason about the instance type, not the catalog key —
  so a 9x10 office and a 15x14 exec office both count as one private office, which is correct.
  Amenities (reception, kitchen, wellness, copy/print, storage) are enclosed support rooms that are
  NOT seats and NOT privacy offices, so each carries its own instance type — they render and place
  like any room but stay out of the seat/enclosed metrics, which is honest.

The legacy 4 keys (`office`, `meeting`, `huddle`, `phone_booth`) remain as aliases so the existing
frontend + tests keep working.
"""

from __future__ import annotations

from dataclasses import dataclass

from .rooms import RoomSpec


@dataclass(frozen=True)
class CatalogEntry:
    key: str
    label: str
    instance_type: str  # what the packers place + metrics count
    width_ft: float
    height_ft: float
    default_placement: str  # window | core | flexible


# Ordered so the largest of each family is queued first when placement uses request order.
_ENTRIES: list[CatalogEntry] = [
    # --- Private offices (size variants -> private_office, perimeter/window by default) ---
    CatalogEntry("office_exec", "Executive office", "private_office", 15.0, 14.0, "window"),
    CatalogEntry("office_large", "Large office", "private_office", 12.0, 12.0, "window"),
    CatalogEntry("office_medium", "Medium office", "private_office", 10.0, 12.0, "window"),
    CatalogEntry("office_small", "Small office", "private_office", 9.0, 10.0, "window"),
    CatalogEntry("office_focus", "Focus office", "private_office", 7.0, 8.0, "flexible"),
    # --- Team offices (sized by headcount -> private_office) ---
    CatalogEntry("team_2", "2-person team office", "private_office", 10.0, 12.0, "window"),
    CatalogEntry("team_4", "4-person team office", "private_office", 13.0, 14.0, "window"),
    CatalogEntry("team_6", "6-person team office", "private_office", 15.0, 16.0, "flexible"),
    CatalogEntry("team_8", "8-person team office", "private_office", 16.0, 18.0, "flexible"),
    # --- Conference / meeting (size variants -> meeting_room, flexible) ---
    CatalogEntry("conf_board", "Boardroom", "meeting_room", 20.0, 40.0, "flexible"),
    CatalogEntry("conf_xl", "Extra-large conference", "meeting_room", 16.0, 28.0, "flexible"),
    CatalogEntry("conf_large", "Large conference", "meeting_room", 15.0, 22.0, "flexible"),
    CatalogEntry("conf_medium", "Medium conference", "meeting_room", 14.0, 16.0, "flexible"),
    CatalogEntry("conf_small", "Small meeting room", "meeting_room", 12.0, 14.0, "flexible"),
    # --- Collaboration / small enclosed ---
    CatalogEntry("huddle", "Huddle room", "collaboration", 8.0, 8.0, "flexible"),
    CatalogEntry("phone_booth", "Phone booth", "phone_booth", 4.0, 4.0, "flexible"),
    CatalogEntry("focus_room", "Focus room", "private_office", 7.0, 8.0, "flexible"),
    # --- Amenities (enclosed support rooms; own instance types, not seats) ---
    CatalogEntry("reception", "Reception", "reception", 12.0, 16.0, "window"),
    CatalogEntry("kitchen", "Kitchen / pantry", "kitchen", 14.0, 16.0, "flexible"),
    CatalogEntry("wellness", "Wellness / mother's room", "wellness", 8.0, 10.0, "core"),
    CatalogEntry("copy_print", "Copy / print", "copy_print", 6.0, 8.0, "core"),
    CatalogEntry("storage", "Storage / IT room", "storage", 8.0, 10.0, "core"),
]

# Aliases keep the legacy frontend + tests working: old key -> canonical catalog key.
_ALIASES: dict[str, str] = {
    "office": "office_medium",  # legacy 10x12 private office
    "meeting": "conf_small",    # legacy 12x14-ish meeting room
    "pantry": "kitchen",
    "mothers_room": "wellness",
    "it_room": "storage",
}

CATALOG: dict[str, CatalogEntry] = {e.key: e for e in _ENTRIES}


def resolve_key(key: str) -> str:
    """Map an alias to its canonical catalog key (identity for real keys)."""
    return _ALIASES.get(key, key)


def is_valid_key(key: str) -> bool:
    return resolve_key(key) in CATALOG


def lookup(key: str) -> CatalogEntry:
    """Catalog entry for a key or alias. Raises KeyError on an unknown key."""
    return CATALOG[resolve_key(key)]


def room_spec(key: str) -> RoomSpec:
    """Footprint a packer consumes: instance type + width + depth (height feeds the wall depth)."""
    e = lookup(key)
    return RoomSpec(type=e.instance_type, width_ft=e.width_ft, depth_ft=e.height_ft)


def valid_keys() -> set[str]:
    """All accepted RoomRequest type strings — canonical keys plus legacy aliases."""
    return set(CATALOG) | set(_ALIASES)
