"""Raster ingest: recover a PlanModel from a synthetic floor-plate image (no model download)."""

from __future__ import annotations

import cv2
import numpy as np

from app.floorplan.raster import ingest_raster


def _plate_png() -> bytes:
    """A 300x200 px filled plate with a 60x60 px core hole, on white — the classic clean plate."""
    img = np.full((300, 400), 255, np.uint8)
    cv2.rectangle(img, (50, 50), (350, 250), 0, thickness=-1)  # plate 300x200 px
    cv2.rectangle(img, (180, 120), (240, 180), 255, thickness=-1)  # core hole 60x60 px
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


def test_recovers_rectangular_boundary_and_core():
    plan = ingest_raster(_plate_png(), "plate.png", px_per_ft=10.0)
    assert 4 <= len(plan.boundary) <= 8  # a rectangle simplifies to ~4 corners
    assert len(plan.cores) == 1  # the interior hole is the core


def test_area_uses_supplied_scale():
    # 300x200 px at 10 px/ft -> 30ft x 20ft = 600 sf; core 60x60 px -> 6ft x 6ft = 36 sf.
    plan = ingest_raster(_plate_png(), "plate.png", px_per_ft=10.0)
    assert plan.units == "ft"
    assert abs(plan.gross_area_sf - 600.0) < 30.0
    assert abs(plan.usable_area_sf - 564.0) < 40.0
    assert plan.usable_area_sf < plan.gross_area_sf  # core subtracted


def test_no_scale_is_flagged_not_faked():
    plan = ingest_raster(_plate_png(), "plate.png")  # no px_per_ft
    assert plan.units == "px"
    assert plan.needs_confirmation is True
    assert plan.gross_area_sf == 0.0  # never invents a scale
    assert any("pixel" in n.lower() for n in plan.notes)
