"""Deterministic CAD element reader — DWG/DXF -> ExtractedLayout.

This is the "read the actual design" path: instead of generating a test-fit, we parse a real
Revit/AutoCAD export and recover its walls, doors, rooms, and full furniture inventory by
reading layers and named block (INSERT) entities. Brand/model live in the block name; room
labels live in TEXT/MTEXT on the area-identifier layer; wall character lives in the layer name.

All coordinates are normalized to FEET (+y up) per the ExtractedLayout contract. Nothing is
fabricated: when a value can't be determined it is left null and the layout is flagged
(`needs_confirmation`) with an explaining note.
"""

from __future__ import annotations

import io
import math
import re
from collections import Counter

import ezdxf.bbox
import ezdxf.recover
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from ..floorplan.dxf_ingest import (
    _INSUNITS_TO_FEET,
    _UNIT_NAME,
    _dwg_to_dxf_bytes,
)
from .schema import Door, ExtractedLayout, FurnitureItem, Room, Wall

# Block-name keyword -> furniture category. Order matters: first match wins, so more specific
# categories are listed before catch-alls. "door" is detected but handled as a Door, not stored
# as furniture (see read_cad).
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("chair", ("task chair", "silq", "series 1", "side chair", "club chair",
               "guest chair", "swivel chair", "conference chair", "seating")),
    ("workstation", ("workstation", "bench")),
    ("desk", ("desk",)),
    ("table", ("conference table", "pedestal", "table")),
    ("sofa", ("sofa", "lounge", "settee", "recliner", "banquette")),
    ("stool", ("barstool", "stool")),
    ("tv", ("flat_screen", "tv", "screen")),
    ("mullion", ("mullion",)),  # glazing framing — not a glass panel; kept out of the panel count
    ("panel", ("system panel", "glazed")),
    ("storage", ("cabinet", "cupbd", "storage", "credenza", "locker", "drawers")),
    ("planter", ("planter", "plant")),
    ("door", ("door",)),
]

# Brand name -> canonical spelling. Matched case-insensitively against the block name.
_BRANDS: list[tuple[str, str]] = [
    ("steelcase", "Steelcase"),
    ("hermanmiller", "Herman Miller"),
    ("herman miller", "Herman Miller"),
    ("emeco", "Emeco"),
    ("knoll", "Knoll"),
    ("haworth", "Haworth"),
]

# Layer-name keyword -> wall type. Checked in order against the upper-cased layer name.
_WALL_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("GLAZ", "GLASS", "SYSTEM PANEL"), "glass"),
    (("WALL-PRHT", "HALF"), "half_drywall"),
    (("COLS", "COLUMN", "CORE"), "core"),
    (("WALL",), "drywall"),
]

# Room-label keyword -> room type.
_ROOM_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("OFFICE",), "office"),
    (("CONFERENCE", "MEETING"), "meeting"),
    (("HUDDLE",), "huddle"),
    (("RECEPTION",), "reception"),
    (("BREAK", "COLLAB"), "open"),
]

_WALL_ENTITY_TYPES = ("LINE", "LWPOLYLINE", "POLYLINE")
_AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*SF", re.IGNORECASE)
# Drop polygonize products that are too small to be a room or so large they're the whole sheet.
_MIN_ROOM_SF = 20.0
_MAX_ROOM_SF = 20_000.0


def read_cad(content: bytes, filename: str) -> ExtractedLayout:
    if (filename or "").lower().endswith(".dwg"):
        content = _dwg_to_dxf_bytes(content)
    doc, _auditor = ezdxf.recover.read(io.BytesIO(content))
    msp = doc.modelspace()

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    lf = _INSUNITS_TO_FEET.get(insunits, 1.0)
    units = _UNIT_NAME.get(insunits, "unknown")
    notes: list[str] = []

    furniture, doors = _read_inserts(msp, lf)
    walls, wall_lines = _read_walls(msp, lf)
    rooms, room_note = _read_rooms(wall_lines, msp, lf)
    if room_note:
        notes.append(room_note)

    inventory: dict[str, int] = dict(Counter(f.category for f in furniture))
    if doors:
        inventory["door"] = len(doors)

    bounds = _bounds(furniture, walls, doors)

    notes.append(
        f"Read deterministically from CAD layers/blocks; geometry scaled to feet from "
        f"drawing units ({units}). Confirm walls/rooms before downstream use."
    )

    return ExtractedLayout(
        source="cad",
        units="ft",
        bounds=bounds,
        walls=walls,
        doors=doors,
        rooms=rooms,
        furniture=furniture,
        inventory=inventory,
        needs_confirmation=True,
        notes=notes,
    )


def _read_inserts(msp, lf: float) -> tuple[list[FurnitureItem], list[Door]]:
    furniture: list[FurnitureItem] = []
    doors: list[Door] = []
    for ins in msp.query("INSERT"):
        name = str(ins.dxf.name)
        layer = str(getattr(ins.dxf, "layer", "")).upper()
        category = _classify_category(name)
        is_door = category == "door" or layer.startswith("A-DOOR") or layer == "DOOR"

        # A MINSERT lays the same block out on a grid; expand to one item per cell so we don't
        # undercount. LibreDWG-converted files usually pre-expand these (mcount == 1).
        rows = int(getattr(ins, "row_count", 1) or 1)
        cols = int(getattr(ins, "col_count", 1) or 1)
        positions = _minsert_positions(ins, rows, cols, lf)

        for (x, y, w, h) in positions:
            rotation = float(getattr(ins.dxf, "rotation", 0.0) or 0.0)
            if is_door:
                doors.append(Door(x=x, y=y, width=max(w, h), rotation=rotation))
            else:
                furniture.append(FurnitureItem(
                    category=category,
                    block_name=name,
                    brand=_extract_brand(name),
                    model=_extract_model(name),
                    x=x, y=y, w=w, h=h,
                    rotation=rotation,
                ))
    return furniture, doors


def _minsert_positions(ins, rows: int, cols: int, lf: float) -> list[tuple[float, float, float, float]]:
    """Return (min_x, min_y, w, h) in feet for each cell the INSERT/MINSERT occupies."""
    try:
        box = ezdxf.bbox.extents([ins])
    except Exception:  # noqa: BLE001 - a degenerate block has no usable footprint
        return []
    if box.extmin is None or box.extmax is None:
        return []
    corners = (box.extmin[0], box.extmin[1], box.extmax[0], box.extmax[1])
    if not all(math.isfinite(v) for v in corners):
        return []  # an empty/degenerate block has no usable footprint — don't fabricate one
    base_x, base_y = box.extmin[0] * lf, box.extmin[1] * lf
    w = (box.extmax[0] - box.extmin[0]) * lf
    h = (box.extmax[1] - box.extmin[1]) * lf

    if rows <= 1 and cols <= 1:
        return [(base_x, base_y, w, h)]

    row_sp = float(getattr(ins.dxf, "row_spacing", 0.0) or 0.0) * lf
    col_sp = float(getattr(ins.dxf, "col_spacing", 0.0) or 0.0) * lf
    return [
        (base_x + c * col_sp, base_y + r * row_sp, w, h)
        for r in range(rows)
        for c in range(cols)
    ]


def _classify_category(name: str) -> str:
    n = name.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(k in n for k in keywords):
            return category
    return "other"


def _extract_brand(name: str) -> str | None:
    n = name.lower()
    for needle, canonical in _BRANDS:
        if needle in n:
            return canonical
    return None


def _extract_model(name: str) -> str | None:
    """Best-effort model: the first descriptive segment of the block name, with the trailing
    Revit element-id / level suffix (`-935254-Level 06 - Furniture`) stripped. Null when nothing
    descriptive remains."""
    cleaned = re.sub(r"-\d+-Level\s+\d+.*$", "", name, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"-V\d+-Level\s+\d+.*$", "", cleaned, flags=re.IGNORECASE).strip()
    segment = cleaned.split(" - ")[-1].strip(" -")
    return segment or None


def _read_walls(msp, lf: float) -> tuple[list[Wall], list[LineString]]:
    walls: list[Wall] = []
    lines: list[LineString] = []
    for entity in msp.query(" ".join(_WALL_ENTITY_TYPES)):
        pts = _entity_points(entity, lf)
        if len(pts) < 2:
            continue
        layer = str(getattr(entity.dxf, "layer", "")).upper()
        walls.append(Wall(points=pts, type=_classify_wall(layer)))
        lines.append(LineString(pts))
    return walls, lines


def _entity_points(entity, lf: float) -> list[tuple[float, float]]:
    kind = entity.dxftype()
    if kind == "LINE":
        s, e = entity.dxf.start, entity.dxf.end
        return [(s[0] * lf, s[1] * lf), (e[0] * lf, e[1] * lf)]
    if kind == "LWPOLYLINE":
        return [(p[0] * lf, p[1] * lf) for p in entity.get_points()]
    if kind == "POLYLINE":
        try:
            return [(v.dxf.location[0] * lf, v.dxf.location[1] * lf) for v in entity.vertices]
        except Exception:  # noqa: BLE001 - skip a malformed vertex chain
            return []
    return []


def _classify_wall(layer: str) -> str:
    for keywords, wall_type in _WALL_TYPE_KEYWORDS:
        if any(k in layer for k in keywords):
            return wall_type
    return "unknown"


def _read_rooms(wall_lines: list[LineString], msp, lf: float) -> tuple[list[Room], str | None]:
    labels = _read_room_labels(msp, lf)
    if not wall_lines:
        return [], "No wall geometry to polygonize — rooms not recovered."

    # unary_union NODES the wall lines at their intersections; polygonize needs noded input to
    # close cells. Without it gappy/overlapping CAD lines yield no rooms.
    noded = unary_union(wall_lines)
    candidates = [
        p for p in polygonize(noded)
        if _MIN_ROOM_SF <= p.area <= _MAX_ROOM_SF
    ]

    rooms: list[Room] = []
    used_labels: set[int] = set()
    next_id = 1
    for poly in candidates:
        label, area_sf = _label_for_polygon(poly, labels, used_labels)
        rooms.append(Room(
            id=f"R-{next_id}",
            label=label,
            area_sf=area_sf,
            polygon=[(round(x, 2), round(y, 2)) for x, y in poly.exterior.coords],
            type=_classify_room(label),
        ))
        next_id += 1

    # Surface any room label that no polygon enclosed (gappy partitions don't close every cell),
    # so the room list isn't blind to a space we positively read from the drawing.
    unplaced = [labels[i] for i in range(len(labels)) if i not in used_labels]
    for (lx, ly, label, area_sf) in unplaced:
        rooms.append(Room(
            id=f"R-{next_id}", label=label, area_sf=area_sf,
            polygon=[], type=_classify_room(label),
        ))
        next_id += 1

    note: str | None = None
    if unplaced:
        note = (
            f"Polygonized {len(candidates)} room cell(s) from wall lines but {len(unplaced)} "
            "labeled room(s) had no closed boundary (gappy partitions) — emitted with empty "
            "polygons. Rooms need manual confirmation."
        )
    elif not candidates:
        note = "Wall lines did not polygonize into closed rooms (gappy partitions)."
    return rooms, note


def _read_room_labels(msp, lf: float) -> list[tuple[float, float, str | None, float | None]]:
    """Pair each '<NN> SF' area text with its room-name text. In these Revit exports the name and
    the area are two separate TEXT/MTEXT entities stacked vertically on A-AREA-IDEN, so we anchor
    on the area text and attach the nearest non-area label."""
    area_texts: list[tuple[float, float, float]] = []
    name_texts: list[tuple[float, float, str]] = []
    for entity in msp.query("TEXT MTEXT"):
        layer = str(getattr(entity.dxf, "layer", "")).upper()
        raw = entity.text if entity.dxftype() == "MTEXT" else entity.dxf.text
        text = str(raw).strip()
        if not text:
            continue
        is_area_layer = "AREA-IDEN" in layer or "A-AREA" in layer
        m = _AREA_RE.fullmatch(text)
        p = entity.dxf.insert
        x, y = p[0] * lf, p[1] * lf
        if m:
            area_texts.append((x, y, float(m.group(1))))
        elif is_area_layer:
            name_texts.append((x, y, text))

    labels: list[tuple[float, float, str | None, float | None]] = []
    for ax, ay, area_sf in area_texts:
        name = _nearest_name(ax, ay, name_texts)
        labels.append((ax, ay, name, area_sf))
    return labels


def _nearest_name(ax: float, ay: float, name_texts: list[tuple[float, float, str]]) -> str | None:
    best: tuple[float, str] | None = None
    for nx, ny, name in name_texts:
        d = (nx - ax) ** 2 + (ny - ay) ** 2
        if best is None or d < best[0]:
            best = (d, name)
    # The name sits within a few feet of the area text; reject a far-away false pairing.
    if best is not None and best[0] <= 36.0:
        return best[1]
    return None


def _label_for_polygon(
    poly: Polygon,
    labels: list[tuple[float, float, str | None, float | None]],
    used: set[int],
) -> tuple[str | None, float | None]:
    for i, (lx, ly, name, area_sf) in enumerate(labels):
        if i in used:
            continue
        if poly.contains(Point(lx, ly)):
            used.add(i)
            return name, area_sf
    return None, None


def _classify_room(label: str | None) -> str:
    if not label:
        return "unknown"
    upper = label.upper()
    for keywords, room_type in _ROOM_TYPE_KEYWORDS:
        if any(k in upper for k in keywords):
            return room_type
    return "unknown"


def _bounds(
    furniture: list[FurnitureItem], walls: list[Wall], doors: list[Door]
) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for f in furniture:
        xs.extend([f.x, f.x + f.w])
        ys.extend([f.y, f.y + f.h])
    for w in walls:
        xs.extend(p[0] for p in w.points)
        ys.extend(p[1] for p in w.points)
    for d in doors:
        xs.append(d.x)
        ys.append(d.y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2))
