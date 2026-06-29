"""ExtractedLayout — the normalized element model every ingestion path produces.

CAD (deterministic, layers+blocks), vector PDF, and raster (ML/CV) all converge on this one shape,
so the 2D plan, the 3D scene, the inventory, and every deliverable read from a single source. All
coordinates are in FEET, with +x right and +y up (plan convention); the renderer flips y for screen.
"""

from __future__ import annotations

from pydantic import BaseModel


class Wall(BaseModel):
    points: list[tuple[float, float]]  # a polyline of (x, y) in feet
    type: str  # drywall | half_drywall | glass | core | perimeter | door | unknown


class Door(BaseModel):
    x: float
    y: float
    width: float  # door-length, feet
    rotation: float  # degrees


class Room(BaseModel):
    id: str  # stable unique id (e.g. "R-12" or the OCR'd room number)
    label: str | None  # "OFFICE 1", "HUDDLE", ... when known
    area_sf: float | None
    polygon: list[tuple[float, float]]  # closed boundary in feet (may be empty if walls don't close)
    center: tuple[float, float] | None = None  # anchor for the label — polygon centroid or label point
    type: str  # office | meeting | open | huddle | reception | core | circulation | unknown


class FurnitureItem(BaseModel):
    """One placed element. (x, y) is the world-space bounding-box MIN corner; (w, h) its size in
    feet; the renderer draws the piece's footprint at that box, rotated about its center."""

    category: str  # chair | desk | workstation | table | sofa | stool | tv | storage | planter | panel | other
    block_name: str  # raw source name (carries brand/model for CAD)
    brand: str | None
    model: str | None  # part number / SKU where the drawing carries it (CET CAPPN)
    x: float
    y: float
    w: float
    h: float
    rotation: float  # degrees
    room_id: str | None = None  # the room this item belongs to (by boundary or nearest centre)
    list_price: float | None = None  # manufacturer list price where the spec carries it (CET CAPPL), for the BOM
    # real plan geometry — world-coord polylines from the source block, so the piece can render as
    # its true shape instead of a category symbol/box. Empty when only a footprint is known.
    outline: list[list[tuple[float, float]]] = []


class ExtractedLayout(BaseModel):
    source: str  # cad | vector_pdf | raster
    units: str  # always "ft" once normalized (or "px" if a raster has no scale)
    bounds: tuple[float, float, float, float]  # min_x, min_y, max_x, max_y
    walls: list[Wall] = []
    doors: list[Door] = []
    rooms: list[Room] = []
    furniture: list[FurnitureItem] = []
    inventory: dict[str, int] = {}  # category -> count (the at-a-glance bill of components)
    needs_confirmation: bool = True
    notes: list[str] = []
