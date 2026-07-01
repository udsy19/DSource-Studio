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

import math
import re
from collections import Counter

import ezdxf.bbox
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from ..floorplan.dxf_ingest import (
    _INSUNITS_TO_FEET,
    _UNIT_NAME,
    _dwg_to_dxf_bytes,
    _read_dxf_doc,
)
from .schema import Door, ExtractedLayout, FurnitureItem, Room, Wall

# Block-name keyword -> furniture category. Order matters: first match wins, so more specific
# categories are listed before catch-alls. "door" is detected but handled as a Door, not stored
# as furniture (see read_cad).
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("chair", ("task chair", "silq", "series 1", "side chair", "club chair",
               "guest chair", "swivel chair", "conference chair", "seating",
               "chair", "armchair")),  # plain "chair" catches CET specs ("Gesture; Chair, ...")
    ("workstation", ("workstation", "bench")),
    ("desk", ("desk",)),
    ("table", ("conference table", "pedestal", "table")),
    ("sofa", ("sofa", "lounge", "settee", "recliner", "banquette", "ottoman", "pouf")),
    ("stool", ("barstool", "bar stool", "stool")),
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

# Layer-name keyword -> wall type. Checked in order against the upper-cased layer name. A line on
# none of these layers is not a wall (returns "unknown") and is dropped by _read_walls. The "WALL"
# substring intentionally catches every AIA/non-standard variant — A-WALL, I-WALL, WALL, WALLS,
# X-WALL-Y — so the building perimeter is recognised whatever the layer is named.
_WALL_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("GLAZ", "GLASS", "SYSTEM PANEL", "WINDOW"), "glass"),
    (("WALL-PRHT", "HALF"), "half_drywall"),
    (("COLS", "COLUMN", "CORE"), "core"),
    (("WALL", "PARTITION", "PRTN"), "drywall"),
]

# Room-label keyword -> room type (first match wins; checked against the upper-cased label). Types
# are the ones the frontend colour-maps (office/meeting/huddle/reception/collab/kitchen/storage).
_ROOM_TYPE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("OFFICE", "CABIN", "PHONE", "FOCUS"), "office"),
    (("CONFERENCE", "MEETING", "BOARD"), "meeting"),
    (("HUDDLE",), "huddle"),
    (("RECEPTION", "ENTRY", "LOBBY", "WAITING"), "reception"),
    (("COLLAB", "LOUNGE", "BREAK", "CAFE"), "collab"),
    (("PANTRY", "KITCHEN"), "kitchen"),
    (("STORAGE", "SERVER", "IDF", "MDF", "BMS", "UPS", "ELEC", "MECH", "LOCKER",
      "JANITOR", "COMMS", "COPY", "PRINT", "MAIL", "WELLNESS", "MOTHER", "UTIL"), "storage"),
]

_WALL_ENTITY_TYPES = ("LINE", "LWPOLYLINE", "POLYLINE")
_AREA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*SF", re.IGNORECASE)
# Drop polygonize products that are too small to be a room or so large they're the whole sheet.
_MIN_ROOM_SF = 20.0
_MAX_ROOM_SF = 20_000.0


def read_cad(content: bytes, filename: str, extract_outline: bool = True) -> ExtractedLayout:
    """Read a CAD layout. `extract_outline` (default on) flattens each item's real plan geometry for
    true-shape rendering — it's the slow part, so the catalog build turns it OFF (footprint is enough
    for slotting/swapping, and storing outlines for 684 apps would bloat the library to ~400 MB)."""
    if (filename or "").lower().endswith(".dwg"):
        content = _dwg_to_dxf_bytes(content)
    doc = _read_dxf_doc(content)
    msp = doc.modelspace()

    insunits = int(doc.header.get("$INSUNITS", 0) or 0)
    lf = _INSUNITS_TO_FEET.get(insunits, 1.0)
    units = _UNIT_NAME.get(insunits, "unknown")
    notes: list[str] = []

    furniture, doors = _read_inserts(msp, lf, extract_outline)
    walls, wall_lines = _read_walls(msp, lf)
    bounds = _bounds(furniture, walls, doors)
    if _synthesize_perimeter(walls, bounds):
        notes.append(
            "Building perimeter was incomplete in the CAD; synthesized an enclosing perimeter "
            "wall from the outer wall extents (derived, not measured). Confirm before fabrication."
        )

    panels = [f for f in furniture if f.category in ("panel", "mullion")]
    # Rooms must be bounded by the building perimeter too. _synthesize_perimeter appended it to
    # `walls` (not `wall_lines`); without it the open plate edge leaks and every perimeter-adjacent
    # room drops to label-only. Seal it into the room boundaries.
    room_lines = wall_lines + [LineString(w.points) for w in walls if w.type == "perimeter"]
    rooms, room_note = _read_rooms(room_lines, panels, doors, bounds, msp, lf)
    _assign_rooms(furniture, rooms)
    _infer_room_types(rooms, furniture)
    if room_note:
        notes.append(room_note)

    inventory: dict[str, int] = dict(Counter(f.category for f in furniture))
    if doors:
        inventory["door"] = len(doors)

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


def _cet_spec(ins) -> dict[str, str] | None:
    """CET / Steelcase INSERTs carry the product spec as block ATTRIBs — CAPPD (description),
    CAPPN (part number / SKU), CAPMG (manufacturer), CAPPL (list price). Return them when present,
    so an anonymous block (`*C12`) resolves to a real, named, sourceable product."""
    attribs = getattr(ins, "attribs", None)
    if not attribs:
        return None
    a = {str(x.dxf.tag).strip(): str(x.dxf.text).strip() for x in attribs}
    desc = a.get("CAPPD") or a.get("CAPPN")
    if not desc:
        return None
    return {
        "desc": desc,
        "part": a.get("CAPPN") or a.get("PSPN") or "",
        "mfg": a.get("CAPMG") or "",
        "price": a.get("CAPPL") or "",
    }


def _parse_price(raw: str) -> float | None:
    """'$1,409.00' -> 1409.0; blanks/dashes -> None."""
    s = re.sub(r"[^\d.]", "", raw or "")
    try:
        return round(float(s), 2) if s else None
    except ValueError:
        return None


# Real plan geometry: flatten an INSERT into world-coord polylines (recursing nested blocks a few
# levels), so a piece can render as its true shape. Bounded so a heavy block can't bloat the layout.
def _item_outline(ins, lf: float, max_polys: int = 48, max_pts: int = 400) -> list[list[tuple[float, float]]]:
    # Reuse the faithful flattener (handles LINE/LWPOLYLINE/POLYLINE/ARC/CIRCLE/ELLIPSE/SPLINE +
    # nested INSERTs) so curved furniture — round tables, arc-backed chairs, circular stools — keeps
    # its real outline instead of being dropped to a box.
    from ..floorplan.cad_geometry import _entity_paths

    polys: list[list[tuple[float, float]]] = []
    total = 0
    for pts, _layer, _closed in _entity_paths(ins):
        if len(polys) >= max_polys or total >= max_pts:
            break
        ring = [(round(x * lf, 2), round(y * lf, 2)) for (x, y) in pts]
        if len(ring) >= 2:
            polys.append(ring)
            total += len(ring)
    return polys


def _read_inserts(msp, lf: float, extract_outline: bool = True) -> tuple[list[FurnitureItem], list[Door]]:
    furniture: list[FurnitureItem] = []
    doors: list[Door] = []
    leaf_cache: dict[str, float | None] = {}
    for ins in msp.query("INSERT"):
        name = str(ins.dxf.name)
        layer = str(getattr(ins.dxf, "layer", "")).upper()
        # CET/Steelcase: classify + name from the product spec attributes, not the anonymous block.
        spec = _cet_spec(ins)
        label = spec["desc"] if spec else name
        category = _classify_category(label)
        is_door = category == "door" or layer.startswith("A-DOOR") or layer == "DOOR"

        # A MINSERT lays the same block out on a grid; expand to one item per cell so we don't
        # undercount. LibreDWG-converted files usually pre-expand these (mcount == 1).
        rows = int(getattr(ins, "row_count", 1) or 1)
        cols = int(getattr(ins, "col_count", 1) or 1)
        positions = _minsert_positions(ins, rows, cols, lf)

        list_price = _parse_price(spec["price"]) if spec else None
        # real outline only for a single placement (its world coords match that one insert); a
        # MINSERT grid would need per-cell offsets, so those fall back to the footprint symbol.
        outline = _item_outline(ins, lf) if (extract_outline and not is_door and len(positions) == 1) else []

        for (x, y, w, h) in positions:
            rotation = float(getattr(ins.dxf, "rotation", 0.0) or 0.0)
            if is_door:
                leaf = _door_leaf_width(ins, lf, leaf_cache)
                width = round(leaf if leaf is not None else min(w, h), 2)
                doors.append(Door(x=x, y=y, width=width, rotation=rotation))
            else:
                furniture.append(FurnitureItem(
                    category=category,
                    block_name=label,
                    brand=(spec["mfg"] if spec and spec["mfg"] else _extract_brand(label)),
                    model=(spec["part"] if spec and spec["part"] else _extract_model(label)),
                    x=x, y=y, w=w, h=h,
                    rotation=rotation,
                    list_price=list_price,
                    outline=outline,
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


def _door_leaf_width(ins, lf: float, cache: dict[str, float | None]) -> float | None:
    """Door opening width = the block's LOCAL x-extent (in its own coordinate frame, before the
    insert rotation). A door block draws the leaf along local x and its swing arc along local y, so
    the world bbox is swing-inflated and reuse of one block makes every world width identical. The
    local x-extent is the true leaf/opening and differs between a single door and a double door.
    None when the block geometry can't be measured (caller falls back to the smaller world dim)."""
    name = str(ins.dxf.name)
    if name not in cache:
        cache[name] = _block_local_x(ins, lf)
    local_x = cache[name]
    if local_x is None or local_x <= 0.5:
        return None
    xscale = abs(float(getattr(ins.dxf, "xscale", 1.0) or 1.0))
    return local_x * xscale


def _block_local_x(ins, lf: float) -> float | None:
    doc = getattr(ins, "doc", None)
    block = doc.blocks.get(str(ins.dxf.name)) if doc is not None else None
    if block is None:
        return None
    try:
        b = ezdxf.bbox.extents(block)
    except Exception:  # noqa: BLE001 - a degenerate block has no measurable footprint
        return None
    if b.extmin is None or b.extmax is None:
        return None
    width = (b.extmax[0] - b.extmin[0]) * lf
    return width if math.isfinite(width) and width > 0 else None


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
        wall_type = _classify_wall(layer)
        if wall_type == "unknown":
            continue  # not on a wall/partition/glazing/core layer — furniture detail, not a wall
        walls.append(Wall(points=pts, type=wall_type))
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


_PERIM_COVERAGE_MIN = 0.5  # an edge with <50% wall along it isn't a real bounding wall
_PERIM_EDGE_TOL = 1.5  # ft — how far off the extent line a segment may sit and still count


def _synthesize_perimeter(walls: list[Wall], bounds: tuple[float, float, float, float]) -> bool:
    """Guarantee the plate is enclosed. Real exports often leave the building outline on a layer we
    don't read, or as gappy fragments that don't trace a continuous edge — so the 3D/2D show holes
    where the perimeter should be. When the existing walls don't bound their own footprint, append a
    derived rectangular perimeter from the outer wall extents (or the plate when no walls exist).
    Returns True when a perimeter was added so the caller can flag it as derived."""
    outline = _wall_extent(walls) or bounds
    minx, miny, maxx, maxy = outline
    if maxx - minx < 1.0 or maxy - miny < 1.0:
        return False
    if walls and _edges_bounded(walls, outline):
        return False
    walls.append(Wall(
        points=[(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)],
        type="perimeter",
    ))
    return True


def _wall_extent(walls: list[Wall]) -> tuple[float, float, float, float] | None:
    pts = [p for w in walls for p in w.points]
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _edges_bounded(walls: list[Wall], outline: tuple[float, float, float, float]) -> bool:
    minx, miny, maxx, maxy = outline
    segs = [(w.points[i], w.points[i + 1]) for w in walls for i in range(len(w.points) - 1)]
    return min(
        _edge_coverage(segs, 0, miny, minx, maxx),  # bottom
        _edge_coverage(segs, 0, maxy, minx, maxx),  # top
        _edge_coverage(segs, 1, minx, miny, maxy),  # left
        _edge_coverage(segs, 1, maxx, miny, maxy),  # right
    ) >= _PERIM_COVERAGE_MIN


def _edge_coverage(segs, axis: int, level: float, lo: float, hi: float) -> float:
    """Fraction of the [lo, hi] extent edge that has a wall segment running along it. `axis` is the
    edge's running direction (0 = horizontal edge at y=level, 1 = vertical edge at x=level)."""
    span = hi - lo
    if span <= 0:
        return 0.0
    other = 1 - axis
    intervals: list[tuple[float, float]] = []
    for a, b in segs:
        if abs(a[other] - level) <= _PERIM_EDGE_TOL and abs(b[other] - level) <= _PERIM_EDGE_TOL:
            start, end = sorted((a[axis], b[axis]))
            start, end = max(start, lo), min(end, hi)
            if end > start:
                intervals.append((start, end))
    return _union_len(intervals) / span


def _union_len(intervals: list[tuple[float, float]]) -> float:
    if not intervals:
        return 0.0
    intervals.sort()
    total = 0.0
    cur_start, cur_end = intervals[0]
    for start, end in intervals[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            total += cur_end - cur_start
            cur_start, cur_end = start, end
    return total + (cur_end - cur_start)


_WALL_BUF = 0.6  # ft — half-thickness to thicken boundaries into a solid mask (bridges double lines)


def _seg(cx: float, cy: float, length: float, ang: float) -> LineString:
    dx, dy = math.cos(ang) * length / 2, math.sin(ang) * length / 2
    return LineString([(cx - dx, cy - dy), (cx + dx, cy + dy)])


def _panel_segment(p: FurnitureItem) -> LineString:
    """A glass partition / mullion as a boundary segment along its long axis."""
    cx, cy = p.x + p.w / 2, p.y + p.h / 2
    length, axis = (p.w, 0.0) if p.w >= p.h else (p.h, math.pi / 2)
    return _seg(cx, cy, length, math.radians(p.rotation) + axis)


def _door_segment(d: Door) -> LineString:
    """A plug across a door opening, so rooms don't leak through doorways."""
    return _seg(d.x, d.y, max(d.width, 2.0), math.radians(d.rotation))


def _ring(poly: Polygon) -> list[tuple[float, float]]:
    return [(round(x, 2), round(y, 2)) for x, y in poly.exterior.coords]


_GAP_HEAL_FT = 4.0  # extend a wall end up to this far to meet a nearby wall (close partition gaps)


def _heal_wall_gaps(lines: list[LineString], reach_ft: float = _GAP_HEAL_FT) -> list[LineString]:
    """Bridge near-miss wall junctions so gappy partitions actually separate rooms.

    Real CAD partitions often stop a foot or two short of the wall they should meet, leaving a gap
    that lets two rooms merge into one region. For every DANGLING segment end (not already touching
    another wall), extend it along its own direction up to reach_ft to the nearest wall it would
    meet. Ends that already connect are left alone, so nothing over-extends into open-plan space.
    Polylines are split to 2-point segments so each end extends independently."""
    segs: list[LineString] = []
    for ln in lines:
        cs = list(ln.coords)
        for a, b in zip(cs, cs[1:]):
            if a != b:
                segs.append(LineString([a, b]))
    if not segs:
        return list(lines)
    tree = STRtree(segs)

    def extend(i: int, tip: tuple[float, float], inner: tuple[float, float]) -> tuple[float, float]:
        dx, dy = tip[0] - inner[0], tip[1] - inner[1]
        length = math.hypot(dx, dy)
        if length == 0:
            return tip
        ux, uy = dx / length, dy / length
        # Extend outward only until we MEET another wall (never a stub into empty space): cast a ray
        # up to reach_ft and snap to the nearest wall it crosses. A gap of a foot or two at a
        # partition junction closes; an end already sitting on a wall finds it immediately and
        # doesn't move meaningfully. Spurious splits are dropped later by the room area/label filters.
        ray = LineString([tip, (tip[0] + ux * reach_ft, tip[1] + uy * reach_ft)])
        best, best_d = tip, reach_ft + 1.0
        for j in tree.query(ray):
            if j == i:
                continue
            hit = ray.intersection(segs[j])
            if hit.is_empty:
                continue
            pts = [hit] if hit.geom_type == "Point" else [g for g in getattr(hit, "geoms", []) if g.geom_type == "Point"]
            for pt in pts:
                d = math.hypot(pt.x - tip[0], pt.y - tip[1])
                if 0.05 < d < best_d:
                    best, best_d = (pt.x, pt.y), d
        return best

    return [LineString([extend(i, s.coords[0], s.coords[1]), extend(i, s.coords[1], s.coords[0])])
            for i, s in enumerate(segs)]


def _read_rooms(
    wall_lines: list[LineString], panels: list[FurnitureItem], doors: list[Door],
    bounds: tuple[float, float, float, float], msp, lf: float,
) -> tuple[list[Room], str | None]:
    labels = _read_room_labels(msp, lf)
    boundaries = list(_heal_wall_gaps(wall_lines))  # bridge near-miss junctions so rooms separate
    boundaries += [_panel_segment(p) for p in panels]  # glass-walled rooms close on the partitions
    boundaries += [_door_segment(d) for d in doors]  # plug doorways
    boundaries = [b for b in boundaries if b.length > 0.1]

    cells: list[Polygon] = []
    if boundaries:
        # CAD walls are double lines, so polygonizing them finds wall cavities, not rooms. Instead
        # thicken every boundary into a solid mask and subtract from the plate — the negative space
        # IS the rooms. This bridges the double lines and (with door plugs) separates partitioned
        # rooms. Far more robust than polygonize() on gappy real-world linework.
        minx, miny, maxx, maxy = bounds
        plate = box(minx, miny, maxx, maxy)
        mask = unary_union([b.buffer(_WALL_BUF, cap_style=2) for b in boundaries])
        region = plate.difference(mask)
        raw = list(region.geoms) if region.geom_type == "MultiPolygon" else [region]
        edge = plate.exterior
        cells = [
            c for c in raw
            if not c.is_empty and _MIN_ROOM_SF <= c.area <= _MAX_ROOM_SF
            and not c.exterior.intersects(edge)  # the exterior gap touches the plate edge
        ]

    rooms: list[Room] = []
    used: set[int] = set()
    nid = 1
    for (lx, ly, label, area_sf) in labels:
        pt = Point(lx, ly)
        # A label claims the cell it sits in only if the cell's size roughly matches its stated area
        # — else a label dropped in open space (e.g. "PHONE RM · 50 SF") would grab the whole 3000sf
        # field. Mismatches stay label-only; the cell is picked up as an unlabeled room below.
        idx = next(
            (i for i, c in enumerate(cells)
             if i not in used and c.contains(pt)
             and (not area_sf or 0.4 * area_sf <= c.area <= 2.5 * area_sf)),
            None,
        )
        if idx is not None:
            used.add(idx)
            c = cells[idx]
            rooms.append(Room(
                id=f"R-{nid}", label=label, area_sf=area_sf or round(c.area, 1),
                polygon=_ring(c), center=(round(c.centroid.x, 2), round(c.centroid.y, 2)),
                type=_classify_room(label),
            ))
        else:
            rooms.append(Room(
                id=f"R-{nid}", label=label, area_sf=area_sf, polygon=[],
                center=(round(lx, 2), round(ly, 2)), type=_classify_room(label),
            ))
        nid += 1

    # enclosed cells with no label that are clearly rooms (e.g. unlabeled offices)
    for i, c in enumerate(cells):
        if i not in used and c.area >= 60:
            rooms.append(Room(
                id=f"R-{nid}", label=None, area_sf=round(c.area, 1),
                polygon=_ring(c), center=(round(c.centroid.x, 2), round(c.centroid.y, 2)),
                type="unknown",
            ))
            nid += 1

    labeled = sum(1 for r in rooms if r.label)
    closed = sum(1 for r in rooms if r.polygon)
    note = None
    if labeled and closed < labeled:
        note = (
            f"Recovered {closed} closed room boundary(ies); {labeled - closed} labeled room(s) "
            "stayed open (gappy partitions) — kept as label-only. Furniture is assigned to the "
            "nearest room. Confirm boundaries before fabrication."
        )
    return rooms, note


def _room_type_from_furniture(items: list[FurnitureItem]) -> str:
    """Classify a DETECTED room from its furniture mix into the Room vocabulary.

    Deliberately not settings.infer_setting_type: a detected room is often large and can merge
    several spaces, so desk count leads (a desk-heavy floor is an open field even if one sofa
    strayed in) — the opposite priority to that small-single-setting heuristic. First match wins:
    a table ringed by seats is a meeting room; many desks is an open field; a lounge sofa is
    collaboration; one or two desks is a private office."""
    cats = Counter(f.category for f in items)
    desks = cats["desk"] + cats["workstation"]
    seats = cats["chair"] + cats["stool"]
    if cats["table"] >= 1 and seats >= 4 and desks < 2:
        return "meeting"
    if desks >= 2:
        return "open"
    if cats["sofa"] >= 1:
        return "collab"
    if desks >= 1:
        return "office"
    return "collab"


def _infer_room_types(rooms: list[Room], furniture: list[FurnitureItem]) -> None:
    """Give each still-unknown room a functional type from the furniture GEOMETRICALLY inside its
    boundary, so a label-less (or generically-labeled) plan still colour-codes: open field vs
    meeting vs office vs collaboration. Uses polygon containment, not the room_id assignment — that
    falls back to nearest-centre and can dump a whole floor of desks into one small room, which
    would mis-type everything. Rooms already typed from a text label are left untouched; an empty
    enclosed cell stays unknown (drawn neutral) rather than being guessed."""
    centers = [(f, Point(f.x + f.w / 2, f.y + f.h / 2)) for f in furniture]
    for r in rooms:
        if r.type != "unknown" or len(r.polygon) < 3:
            continue
        poly = Polygon(r.polygon)
        items = [f for f, c in centers if poly.contains(c)]
        if items:
            r.type = _room_type_from_furniture(items)


def _assign_rooms(furniture: list[FurnitureItem], rooms: list[Room]) -> None:
    """Tag each furniture item with its room — by boundary containment where a polygon exists,
    else by nearest room centre — so the per-room takeoff is populated even with open boundaries."""
    polys = [(r.id, Polygon(r.polygon)) for r in rooms if len(r.polygon) >= 3]
    centers = [(r.id, r.center) for r in rooms if r.center]
    for f in furniture:
        cx, cy = f.x + f.w / 2, f.y + f.h / 2
        rid = next((rid for rid, poly in polys if poly.contains(Point(cx, cy))), None)
        if rid is None and centers:
            rid = min(centers, key=lambda rc: (rc[1][0] - cx) ** 2 + (rc[1][1] - cy) ** 2)[0]
        f.room_id = rid


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
