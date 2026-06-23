"""Generate a realistic office floor-plate DXF fixture (real DXF format).

This is a TEST FIXTURE for the floor-plate ingester, authored to mirror how a real CAD
export is structured — geometry on named layers, real-world units (feet) — so the ingester
exercises real extraction logic (pick the exterior boundary among several closed polylines,
subtract the core, count structural columns, ignore partition noise). The ingester parses
externally-authored CAD DXFs identically; drop a real .dxf into data/floorplans/ to use one.

Layout (feet): an L-shaped 8,100 sf plate (9,600 rect minus a 50x30 notch), a 600 sf
service core, 8 structural columns, and a few interior partition lines as noise.
"""

from pathlib import Path

import ezdxf

OUT = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"

# L-shaped exterior boundary (feet). Area = 120*80 - 50*30 = 8100 sf.
BOUNDARY = [(0, 0), (120, 0), (120, 50), (70, 50), (70, 80), (0, 80)]
# Service core (elevators/restrooms) — a 30x20 = 600 sf hole in usable area.
CORE = [(15, 15), (45, 15), (45, 35), (15, 35)]
# 8 structural columns on a ~30 ft grid, all inside the boundary and outside the core.
COLUMNS = [(60, 40), (90, 40), (110, 40), (60, 65), (30, 45), (100, 25), (110, 25), (30, 65)]
COLUMN_RADIUS = 0.75
# Interior partition segments (noise the boundary detector must ignore — open lines).
PARTITIONS = [((70, 50), (70, 0)), ((45, 35), (45, 80)), ((0, 50), (70, 50))]


def build() -> None:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 2  # 2 = feet
    msp = doc.modelspace()
    for name, color in [("A-WALL", 7), ("A-CORE", 3), ("S-COLS", 1), ("A-WALL-PART", 8)]:
        if name not in doc.layers:
            doc.layers.add(name, color=color)

    msp.add_lwpolyline(BOUNDARY, close=True, dxfattribs={"layer": "A-WALL"})
    msp.add_lwpolyline(CORE, close=True, dxfattribs={"layer": "A-CORE"})
    for (x, y) in COLUMNS:
        msp.add_circle((x, y), COLUMN_RADIUS, dxfattribs={"layer": "S-COLS"})
    for a, b in PARTITIONS:
        msp.add_line(a, b, dxfattribs={"layer": "A-WALL-PART"})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(OUT)
    print(f"wrote {OUT}  (boundary 8100 sf, core 600 sf, {len(COLUMNS)} columns)")


if __name__ == "__main__":
    build()
