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

from app.ingestion.cad_reader import read_cad

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


@pytest.mark.skipif(not os.path.exists(REAL_DWG), reason="real DWG not present")
def test_real_dwg_inventory():
    with open(REAL_DWG, "rb") as f:
        layout = read_cad(f.read(), os.path.basename(REAL_DWG))
    assert layout.units == "ft"
    assert layout.inventory.get("chair", 0) > 50
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
