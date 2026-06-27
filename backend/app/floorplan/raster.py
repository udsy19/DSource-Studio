"""Raster / PDF floor-plan ingestion — recover a `PlanModel` from a JPG/PNG/PDF floor plate.

Qbiq accepts CAD, PDF, and JPEG; the CAD path lives in `dxf_ingest`. This adds raster + PDF via
classical computer vision (OpenCV): binarize, take the largest filled region as the floor-plate
boundary, and treat its interior holes as cores. The output `PlanModel` is drop-in compatible with
the CAD path, so test-fit / alternatives / takeoff / report all work on an image upload.

Honest limits: a raster carries no real-world scale. If the caller supplies `px_per_ft` we convert
to feet and compute areas; otherwise we return pixel-space coordinates with `units="px"`,
`needs_confirmation=True`, and zero area — we never invent a scale. This is a v1 extractor for
reasonably clean plates; a learned model (CubiCasa5K / DeepFloorPlan) is the upgrade path for
messy scans and full room/door/window recognition.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
from shapely.geometry import Polygon

from .dxf_ingest import PlanModel

_MIN_CORE_AREA_FRAC = 0.01  # ignore interior holes smaller than 1% of the plate


def _to_grayscale(content: bytes, filename: str) -> np.ndarray:
    """Decode a PNG/JPG (or the first page of a PDF) into a grayscale image array."""
    if filename.lower().endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pil = pdf.pages[0].to_image(resolution=150).original.convert("L")
        return np.array(pil)
    array = np.frombuffer(content, np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("Could not decode the image — expected PNG, JPG, or PDF.")
    return image


def _approx_polygon(contour: np.ndarray, height: int) -> list[tuple[float, float]]:
    """Simplify a contour to a few points and flip Y so the plan reads as drawn (y-up)."""
    epsilon = 0.01 * cv2.arcLength(contour, closed=True)
    approx = cv2.approxPolyDP(contour, epsilon, closed=True)
    return [(float(p[0][0]), float(height - p[0][1])) for p in approx]


def ingest_raster(content: bytes, filename: str = "", px_per_ft: float | None = None) -> PlanModel:
    gray = _to_grayscale(content, filename)
    height = gray.shape[0]
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("No floor-plate outline found in the image.")

    plate_idx = max(range(len(contours)), key=lambda i: cv2.contourArea(contours[i]))
    plate_area_px = cv2.contourArea(contours[plate_idx])
    boundary = _approx_polygon(contours[plate_idx], height)

    # Interior holes of the plate contour are cores (lift shafts / stairs / risers).
    cores = [
        _approx_polygon(contours[i], height)
        for i in range(len(contours))
        if hierarchy[0][i][3] == plate_idx
        and cv2.contourArea(contours[i]) >= _MIN_CORE_AREA_FRAC * plate_area_px
    ]

    note = "Geometry recovered from a raster image — confirm the outline and scale before use."
    if px_per_ft and px_per_ft > 0:
        boundary = [(x / px_per_ft, y / px_per_ft) for x, y in boundary]
        cores = [[(x / px_per_ft, y / px_per_ft) for x, y in c] for c in cores]
        gross = Polygon(boundary).area
        core_area = sum(Polygon(c).area for c in cores if len(c) >= 3)
        return PlanModel(
            units="ft", sqft_factor=1.0, boundary=boundary,
            gross_area_sf=gross, core_area_sf=core_area, usable_area_sf=gross - core_area,
            cores=cores, columns=[], boundary_source="raster",
            needs_confirmation=True, notes=[note],
        )

    return PlanModel(
        units="px", sqft_factor=0.0, boundary=boundary,
        gross_area_sf=0.0, core_area_sf=0.0, usable_area_sf=0.0,
        cores=cores, columns=[], boundary_source="raster",
        needs_confirmation=True,
        notes=[note, "No scale supplied: coordinates are in pixels. Provide px_per_ft for areas."],
    )
