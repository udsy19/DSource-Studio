"""Tests for the deterministic CAD element reader.

The unit test builds a synthetic DXF in-memory (no network, no real file) shaped like the real
Revit export — named INSERT blocks on furniture/door layers, a closed rectangle of wall LINEs,
and an A-AREA-IDEN room label — and asserts the recovered furniture, walls, units and inventory.
The final test runs against the user's real DWG only when it is present.
"""

from __future__ import annotations

import io
import os

import ezdxf
import pytest

from shapely.geometry import Point
from shapely.geometry import Polygon as ShapelyPolygon

from app.ingestion.cad_reader import (
    _furniture_hull,
    _planning_polygon,
    clip_to_planning_area,
    read_cad,
)
from app.ingestion.schema import Door, FurnitureItem, Wall

REAL_DWG = "/Users/udsy/Downloads/0414-Sheet - 500 - FURNITURE PLAN.dxf.dwg"


def _synthetic_dxf() -> bytes:
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    # Furniture blocks named like the real export. Each block has a unit-square footprint so its
    # world bbox is predictable after placement.
    for block_name in (
        "Steelcase - Seating - SILQ - Task Chair - Task Chair-649269-Level 06 - Furniture",
        "WORKSTATIONS_BENCH- SINGLE - 5 X 2 FT FT-648372-Level 06 - Furniture",
        "System Panel - Glazed-935260-Level 06 - Furniture",
        "Door - Single - Flush-Level 06 - Furniture",
    ):
        block = doc.blocks.new(name=block_name)
        block.add_lwpolyline([(0, 0), (12, 0), (12, 12), (0, 12)], close=True)  # 1ft sq in inches

    msp.add_blockref("Steelcase - Seating - SILQ - Task Chair - Task Chair-649269-Level 06 - Furniture",
                     (120, 120), dxfattribs={"layer": "I-FURN"})
    msp.add_blockref("Steelcase - Seating - SILQ - Task Chair - Task Chair-649269-Level 06 - Furniture",
                     (140, 120), dxfattribs={"layer": "I-FURN", "rotation": 90})
    msp.add_blockref("WORKSTATIONS_BENCH- SINGLE - 5 X 2 FT FT-648372-Level 06 - Furniture",
                     (200, 200), dxfattribs={"layer": "I-FURN"})
    msp.add_blockref("System Panel - Glazed-935260-Level 06 - Furniture",
                     (60, 60), dxfattribs={"layer": "A-GLAZ-CWMG"})
    msp.add_blockref("Door - Single - Flush-Level 06 - Furniture",
                     (84, 0), dxfattribs={"layer": "A-DOOR"})

    # A closed rectangle of wall LINEs (a 10ft x 8ft room in inches) on a wall layer + one glass run.
    wall_pts = [(0, 0), (120, 0), (120, 96), (0, 96), (0, 0)]
    for a, b in zip(wall_pts, wall_pts[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL-PATT"})
    msp.add_line((0, 0), (0, 96), dxfattribs={"layer": "A-GLAZ-CURT"})

    # Room label as two stacked A-AREA-IDEN texts, like the real file.
    msp.add_text("OFFICE 1", dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((60, 56))
    msp.add_text("120 SF", dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((60, 48))

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def _no_perimeter_dxf() -> bytes:
    """Two short interior wall stubs that do NOT enclose anything — the safety net must add a
    perimeter — plus two door blocks of different leaf width to exercise the door-width fix."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    # Single-leaf door: leaf 36in along local x, swing 48in along local y.
    single = doc.blocks.new(name="Door - Single - Solid")
    single.add_line((0, 0), (36, 0))
    single.add_line((0, 0), (0, 48))
    # Double-leaf door: opening 72in along local x, same 48in swing depth.
    double = doc.blocks.new(name="Door - Double - Glass")
    double.add_line((0, 0), (72, 0))
    double.add_line((0, 0), (0, 48))

    msp.add_blockref("Door - Single - Solid", (200, 200), dxfattribs={"layer": "A-DOOR"})
    msp.add_blockref("Door - Double - Glass", (400, 200),
                     dxfattribs={"layer": "A-DOOR", "rotation": 90})

    # Interior partitions only — no closed outer boundary.
    msp.add_line((100, 100), (300, 100), dxfattribs={"layer": "I-WALL"})
    msp.add_line((100, 300), (300, 300), dxfattribs={"layer": "I-WALL"})

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_perimeter_synthesized_when_walls_do_not_enclose():
    layout = read_cad(_no_perimeter_dxf(), "open.dxf")
    perimeters = [w for w in layout.walls if w.type == "perimeter"]
    assert len(perimeters) == 1
    ring = perimeters[0].points
    assert ring[0] == ring[-1] and len(ring) == 5  # a closed rectangle
    assert any("perimeter" in n.lower() for n in layout.notes)


def test_no_perimeter_added_when_walls_already_enclose():
    # The synthetic fixture's walls form a closed rectangle, so nothing should be synthesized.
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    assert not any(w.type == "perimeter" for w in layout.walls)


def test_door_widths_reflect_leaf_not_swing():
    layout = read_cad(_no_perimeter_dxf(), "open.dxf")
    widths = sorted(round(d.width, 2) for d in layout.doors)
    # Both blocks have a 48in (4ft) swing-inflated world bbox; max(w,h) would make them identical.
    # The leaf (local x-extent) is 3ft and 6ft respectively — they must differ.
    assert widths == pytest.approx([3.0, 6.0])


def test_units_normalized_to_feet():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    assert layout.units == "ft"
    assert layout.source == "cad"


def test_furniture_categories_classified():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    by_cat = {}
    for item in layout.furniture:
        by_cat.setdefault(item.category, []).append(item)
    assert len(by_cat["chair"]) == 2
    assert len(by_cat["workstation"]) == 1
    assert len(by_cat["panel"]) == 1
    # The door block must NOT land in furniture — it's a door.
    assert "door" not in by_cat


def test_brand_and_model_parsed():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    chair = next(f for f in layout.furniture if f.category == "chair")
    assert chair.brand == "Steelcase"
    assert chair.model and "Task Chair" in chair.model
    # The Revit element-id / level suffix must be stripped from the model string.
    assert "Level 06" not in chair.model


def test_coordinates_scaled_to_feet():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    ws = next(f for f in layout.furniture if f.category == "workstation")
    # Placed at inch (200,200) with a 12-inch footprint -> (16.67, 16.67), 1ft x 1ft.
    assert ws.x == pytest.approx(200 / 12, abs=0.1)
    assert ws.w == pytest.approx(1.0, abs=0.1)


def test_walls_classified_from_layer():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    types = {w.type for w in layout.walls}
    assert "drywall" in types  # A-WALL-PATT
    assert "glass" in types    # A-GLAZ-CURT


def test_doors_extracted():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    assert len(layout.doors) == 1
    assert layout.inventory.get("door") == 1


def test_door_flip_defaults_false_and_round_trips():
    # The editor's swing-side toggle rides on Door.flip; it must default off (back-compatible with
    # every layout produced before the field existed) and survive a JSON round-trip.
    assert Door(x=1, y=2, width=3, rotation=90).flip is False
    flipped = Door.model_validate(Door(x=1, y=2, width=3, rotation=90, flip=True).model_dump())
    assert flipped.flip is True


def test_inventory_counts():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    assert layout.inventory["chair"] == 2
    assert layout.inventory["workstation"] == 1
    assert layout.inventory["panel"] == 1


def test_room_recovered_with_label():
    layout = read_cad(_synthetic_dxf(), "synthetic.dxf")
    assert layout.rooms, "expected at least one polygonized room"
    office = next((r for r in layout.rooms if r.label == "OFFICE 1"), None)
    assert office is not None
    assert office.type == "office"
    assert office.area_sf == pytest.approx(120.0)


def _unlabeled_rooms_dxf() -> bytes:
    """A plate split by an interior wall into two UNLABELED rooms (no A-AREA-IDEN text): the left
    holds two benching workstations (reads as an open field), the right a lounge sofa (reads as
    collaboration). Exercises furniture-mix room-type inference for rooms with no text label."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    for block_name, w_in in (
        ("WORKSTATIONS_BENCH- SINGLE - 5 X 2 FT-1-Level 06 - Furniture", 24),
        ("Lounge Sofa - Two Seat-2-Level 06 - Furniture", 48),
    ):
        block = doc.blocks.new(name=block_name)
        block.add_lwpolyline([(0, 0), (w_in, 0), (w_in, w_in), (0, w_in)], close=True)

    # Left room (0..240 in) gets two workstations; right room (240..480 in) gets a sofa.
    msp.add_blockref("WORKSTATIONS_BENCH- SINGLE - 5 X 2 FT-1-Level 06 - Furniture",
                     (60, 100), dxfattribs={"layer": "I-FURN"})
    msp.add_blockref("WORKSTATIONS_BENCH- SINGLE - 5 X 2 FT-1-Level 06 - Furniture",
                     (150, 100), dxfattribs={"layer": "I-FURN"})
    msp.add_blockref("Lounge Sofa - Two Seat-2-Level 06 - Furniture",
                     (330, 100), dxfattribs={"layer": "I-FURN"})

    # Perimeter (40ft x 20ft in inches) + an interior divider at x=240 — no room label text.
    perim = [(0, 0), (480, 0), (480, 240), (0, 240), (0, 0)]
    for a, b in zip(perim, perim[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
    msp.add_line((240, 0), (240, 240), dxfattribs={"layer": "A-WALL"})

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_user_seed_marks_a_room_type():
    # The left cell holds two workstations, so it detects as an open field. A user marker dropped
    # there saying "this is a meeting room" must win — the seed is authoritative.
    seeds = [{"type": "meeting", "label": "Boardroom", "x": 10.0, "y": 10.0}]
    layout = read_cad(_unlabeled_rooms_dxf(), "unlabeled.dxf", user_seeds=seeds)
    marked = [r for r in layout.rooms if r.polygon and r.type == "meeting"]
    assert marked, f"a user 'meeting' marker should produce a meeting room; types were {[r.type for r in layout.rooms]}"
    assert any(r.label == "Boardroom" for r in marked)


def test_unlabeled_room_type_inferred_from_furniture():
    layout = read_cad(_unlabeled_rooms_dxf(), "unlabeled.dxf")
    unlabeled = [r for r in layout.rooms if not r.label and r.polygon]
    assert len(unlabeled) >= 2, f"expected two detected unlabeled rooms, got {len(unlabeled)}"
    types = {r.type for r in unlabeled}
    # No text labels, so type MUST come from the furniture mix — not left at "unknown".
    assert "open" in types, f"two workstations should read as an open field; got {types}"
    assert "collab" in types, f"a sofa should read as collaboration; got {types}"


def _open_edge_rooms_dxf() -> bytes:
    """A building with its TOP edge missing (forces perimeter synthesis) and one interior partition
    splitting it into two labeled rooms. Without sealing the synthesized perimeter into the room
    boundaries, both rooms leak to the open plate edge and drop to label-only — this guards that
    they close once the perimeter is included."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    # 60ft x 40ft in inches, TOP side omitted so the perimeter must be synthesized.
    for a, b in [((0, 0), (720, 0)), ((0, 0), (0, 480)), ((720, 0), (720, 480))]:
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
    msp.add_line((360, 0), (360, 480), dxfattribs={"layer": "A-WALL"})  # interior partition

    # each room is 30ft x 40ft ≈ 1200 sf — the label area must match the geometry (the reader now
    # rejects a label whose stated area is wildly off the cell it sits in).
    for name, x in (("OFFICE A", 180), ("OFFICE B", 540)):
        msp.add_text(name, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 240))
        msp.add_text("1200 SF", dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 216))

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_perimeter_seal_closes_rooms_behind_open_edge():
    layout = read_cad(_open_edge_rooms_dxf(), "open_edge.dxf")
    closed = [r for r in layout.rooms if r.polygon and r.label]
    labels = {r.label for r in closed}
    assert "OFFICE A" in labels and "OFFICE B" in labels, (
        f"both rooms should close once the synthesized perimeter seals the open edge; "
        f"closed labels were {labels}"
    )


def _gapped_partition_dxf() -> bytes:
    """A closed 40x30ft building split by a partition that stops 2ft SHORT of the top wall. Without
    healing the 2ft gap lets both sides merge into one region; the gap-healer extends the dangling
    partition end to the wall so the two rooms separate and close."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    perim = [(0, 0), (480, 0), (480, 360), (0, 360), (0, 0)]  # 40ft x 30ft, closed
    for a, b in zip(perim, perim[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
    # partition rises from the bottom wall but stops 24in (2ft) below the top wall — a real gap.
    msp.add_line((240, 0), (240, 336), dxfattribs={"layer": "A-WALL"})

    # each room is 20ft x 30ft ≈ 600 sf — label area must match the cell (reader rejects mismatches).
    for name, x in (("OFFICE A", 120), ("OFFICE B", 360)):
        msp.add_text(name, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 180))
        msp.add_text("600 SF", dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 156))

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_gap_healing_separates_rooms_across_a_broken_partition():
    layout = read_cad(_gapped_partition_dxf(), "gapped.dxf")
    closed = {r.label for r in layout.rooms if r.polygon and r.label}
    assert "OFFICE A" in closed and "OFFICE B" in closed, (
        f"the 2ft partition gap should be healed so both rooms close; closed labels were {closed}"
    )


def test_planning_polygon_rejects_degenerate():
    # Fewer than three vertices or a zero-area ring is not a usable clip region.
    assert _planning_polygon(None) is None
    assert _planning_polygon([(0.0, 0.0), (1.0, 1.0)]) is None
    assert _planning_polygon([(0.0, 0.0), (2.0, 0.0), (4.0, 0.0)]) is None  # collinear → no area
    assert _planning_polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]) is not None


def test_clip_to_planning_area_drops_elements_outside_polygon():
    # A 10ft x 10ft planning box at the origin. One piece sits inside, one outside; likewise a wall
    # and a door. The clip must keep only the in-box elements — dropped, not hidden.
    area = _planning_polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)])
    assert area is not None
    inside = FurnitureItem(category="chair", block_name="in", brand=None, model=None,
                           x=2.0, y=2.0, w=2.0, h=2.0, rotation=0.0)
    outside = FurnitureItem(category="chair", block_name="out", brand=None, model=None,
                            x=50.0, y=50.0, w=2.0, h=2.0, rotation=0.0)
    walls = [Wall(points=[(1.0, 1.0), (5.0, 5.0)], type="drywall"),   # centroid inside
             Wall(points=[(40.0, 40.0), (60.0, 60.0)], type="drywall")]  # centroid outside
    doors = [Door(x=3.0, y=3.0, width=3.0, rotation=0.0),   # inside
             Door(x=80.0, y=80.0, width=3.0, rotation=0.0)]  # outside
    kept_f, kept_w, kept_d = clip_to_planning_area(area, [inside, outside], walls, doors)
    assert [f.block_name for f in kept_f] == ["in"]
    assert kept_w == [walls[0]]
    assert kept_d == [doors[0]]


def test_planning_area_restricts_read_layout():
    # The unlabeled fixture is a 40ft x 20ft plate: workstations on the left (x≈5–13ft), a sofa on
    # the right (x≈27ft). A planning box over the left half must drop the sofa and keep the desks.
    left_half = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]
    layout = read_cad(_unlabeled_rooms_dxf(), "unlabeled.dxf", planning_area=left_half)
    cats = {f.category for f in layout.furniture}
    assert "sofa" not in cats, f"the right-side sofa is outside the planning area; got {cats}"
    assert layout.inventory.get("workstation", 0) == 2
    assert any("planning area" in n.lower() for n in layout.notes)


def test_keep_walls_skips_gap_healing():
    # Default: the 2ft partition gap is healed, so each room sits in its own wall-bounded region
    # (walls_closed). With keep_walls the gap is left as drawn, so the two labels share one merged
    # region and are split by seed (label_seeded) — proving gap-healing was skipped.
    healed = read_cad(_gapped_partition_dxf(), "gapped.dxf")
    verbatim = read_cad(_gapped_partition_dxf(), "gapped.dxf", keep_walls=True)

    def basis(layout, label):
        return next(r.boundary_basis for r in layout.rooms if r.label == label and r.polygon)

    assert basis(healed, "OFFICE A") == "walls_closed"
    assert basis(healed, "OFFICE B") == "walls_closed"
    assert basis(verbatim, "OFFICE A") == "label_seeded"
    assert basis(verbatim, "OFFICE B") == "label_seeded"


def _service_rooms_dxf() -> bytes:
    """A closed 40x20ft plate split at x=20ft into two labeled cells: a toilet and a stair core —
    exercises WC/restroom and structural-core room typing from the label keywords."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()

    perim = [(0, 0), (480, 0), (480, 240), (0, 240), (0, 0)]  # 40ft x 20ft, closed
    for a, b in zip(perim, perim[1:]):
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL"})
    msp.add_line((240, 0), (240, 240), dxfattribs={"layer": "A-WALL"})  # divider at x=20ft

    for name, x in (("MENS TOILET", 120), ("STAIR CORE", 360)):  # each cell 20ft x 20ft = 400 sf
        msp.add_text(name, dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 120))
        msp.add_text("400 SF", dxfattribs={"layer": "A-AREA-IDEN"}).set_placement((x, 96))

    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_restroom_and_core_typed_from_labels():
    layout = read_cad(_service_rooms_dxf(), "service.dxf")
    by_label = {r.label: r.type for r in layout.rooms if r.label}
    assert by_label.get("MENS TOILET") == "restroom", f"WC/toilet should type as restroom; {by_label}"
    assert by_label.get("STAIR CORE") == "core", f"a stair core should type as core; {by_label}"


@pytest.mark.skipif(not os.path.exists(REAL_DWG), reason="real DWG not present")
def test_real_dwg_inventory():
    with open(REAL_DWG, "rb") as f:
        layout = read_cad(f.read(), os.path.basename(REAL_DWG))
    assert layout.units == "ft"
    assert layout.inventory.get("chair", 0) > 50
    # Label-seeded segmentation: essentially every labeled room closes (was 1 with wall-tracing).
    labeled_closed = [r for r in layout.rooms if r.label and r.polygon]
    assert len(labeled_closed) >= 15, f"expected most labeled rooms to close, only {len(labeled_closed)} did"
    # Every closed room reports how its boundary was derived, with a matching confidence.
    for r in layout.rooms:
        if r.polygon:
            assert r.boundary_basis in ("walls_closed", "label_seeded", "furniture_hull")
            assert 0.0 < r.confidence <= 1.0
    assert layout.inventory.get("workstation", 0) > 50


def _cet_dxf() -> bytes:
    """A Configura CET / Steelcase-style export: an anonymous block (*C1) on A-FURN carrying the
    product spec as CAP* attributes — the form ODA File Converter preserves."""
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 1  # inches
    msp = doc.modelspace()
    blk = doc.blocks.new(name="*C1")
    blk.add_lwpolyline([(0, 0), (24, 0), (24, 24), (0, 24)], close=True)  # 2 ft sq footprint
    ref = msp.add_blockref("*C1", (50, 50), dxfattribs={"layer": "A-FURN"})
    ref.add_attrib("CAPPD", "Steelcase Series 2; Chair-Upholstered back")
    ref.add_attrib("CAPPN", "436UPH")
    ref.add_attrib("CAPMG", "Steelcase")
    text = io.StringIO()
    doc.write(text)
    return text.getvalue().encode("utf-8")


def test_cet_spec_attributes_yield_branded_skutagged_furniture():
    """An anonymous CET block resolves to a real product: category from the description, brand from
    the manufacturer, model from the part number — not the meaningless block name."""
    layout = read_cad(_cet_dxf(), "application.dxf")
    chairs = [f for f in layout.furniture if f.category == "chair"]
    assert len(chairs) == 1, f"expected the CAPPD 'Chair' to classify as a chair, got {layout.inventory}"
    c = chairs[0]
    assert c.brand == "Steelcase"
    assert c.model == "436UPH"
    assert "Series 2" in c.block_name


def test_furniture_hull_is_clipped_to_the_building_envelope():
    """A low-confidence furniture-hull room must not spill past the perimeter. Furniture hugging the
    right wall would, after the +1.5 ft pad, bulge outside x=10; clipping to the envelope pins it in."""
    centers = [(None, Point(x, y)) for x, y in [(6, 2), (9.5, 2), (9.5, 8), (6, 8)]]
    perimeter = ShapelyPolygon([(0, 0), (10, 0), (10, 10), (0, 10)])

    unclipped = _furniture_hull(7.75, 5.0, centers)
    clipped = _furniture_hull(7.75, 5.0, centers, perimeter)

    assert unclipped is not None and unclipped.bounds[2] > 10.0  # would overshoot the wall
    assert clipped is not None
    assert clipped.bounds[2] <= 10.0 + 1e-6  # pinned to the envelope
    assert clipped.within(perimeter.buffer(1e-6))
