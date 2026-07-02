"""Space Planning Report — a styled, multi-page PDF deliverable.

Pure rendering: `build_report_pdf(data)` takes a `ReportData` dict (the shape the router
validates) and returns PDF bytes. No I/O, no other modules — the caller supplies everything.

Layout follows the studio aesthetic: warm paper, ink linework, a single terracotta accent,
serif numerals (Times stands in for Fraunces, which isn't a built-in PDF font). Pages:
cover (with an honest QR when a link is supplied), an optional render page (only when a render
image is present), one per alternative (metrics sidebar + to-scale 2D plan), and a comparison
summary (table + seat bars + space-mix breakdown).

Honest data: a missing metric renders as an em-dash, never a fabricated number; the render page
appears only when there is a real render; the QR links to whatever URL the caller supplies and is
labelled for exactly that — it never implies a hosted 3D tour.
"""

from __future__ import annotations

import base64
import binascii
import io
from typing import Iterable

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .palette import ACCENT, INK, INK_2, LINE, MUTED, PAPER
from .qr import draw_qr

# One soft fill per furniture type; all share an ink hairline stroke.
ROOM_FILL = {
    "workstation": HexColor("#DCE3E1"),
    "private_office": HexColor("#EFE2CB"),
    "meeting_room": HexColor("#E9CBBA"),  # terracotta tint
    "collaboration": HexColor("#DCE5D5"),
}
ROOM_LABEL = {
    "workstation": "Workstation",
    "private_office": "Private office",
    "meeting_room": "Meeting room",
    "collaboration": "Collaboration",
}

SERIF = "Times-Roman"
SERIF_BOLD = "Times-Bold"
SANS = "Helvetica"
SANS_BOLD = "Helvetica-Bold"

PAGE = landscape(letter)  # 792 x 612 pt
MARGIN = 46.0
EM_DASH = "—"


def build_report_pdf(data: dict) -> bytes:
    """Render the full report and return PDF bytes."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    width, height = PAGE

    project = data.get("project", {})
    plan = data.get("plan", {})
    alternatives = data.get("alternatives", [])
    render_image = data.get("render_image")
    qr_url = data.get("qr_url")

    _draw_cover(c, width, height, project, plan, qr_url)
    render = _decode_render(render_image)
    if render is not None:
        c.showPage()
        _draw_render_page(c, width, height, project, render)
    for alt in alternatives:
        c.showPage()
        _draw_alternative_page(c, width, height, project, plan, alt)
    c.showPage()
    _draw_summary_page(c, width, height, project, alternatives)

    c.showPage()
    c.save()
    return buf.getvalue()


def _decode_render(render_image) -> ImageReader | None:
    """Turn a data-URL or bare base64 string into an ImageReader; None when absent/undecodable."""
    if not render_image or not isinstance(render_image, str):
        return None
    payload = render_image.split(",", 1)[1] if render_image.startswith("data:") else render_image
    try:
        return ImageReader(io.BytesIO(base64.b64decode(payload)))
    except (binascii.Error, ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# Shared chrome
# ---------------------------------------------------------------------------

def _paper(c: canvas.Canvas, width: float, height: float) -> None:
    c.setFillColor(PAPER)
    c.rect(0, 0, width, height, fill=1, stroke=0)


def _eyebrow(c: canvas.Canvas, x: float, y: float, text: str) -> None:
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y, _spaced(text.upper()))


def _spaced(text: str) -> str:
    # Cheap letter-spacing for eyebrows (built-in fonts have no tracking control).
    return " ".join(text)


def _footer(c: canvas.Canvas, width: float, project: dict, page_label: str) -> None:
    c.setFont(SANS, 7.5)
    c.setFillColor(MUTED)
    left = f"{project.get('client') or 'Client'}  ·  {project.get('building') or ''}".strip(" ·")
    c.drawString(MARGIN, 26, left)
    c.drawRightString(width - MARGIN, 26, page_label)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.line(MARGIN, 36, width - MARGIN, 36)


def _fmt(value, suffix: str = "", decimals: int | None = None) -> str:
    if value is None:
        return EM_DASH
    if isinstance(value, float) and decimals is not None:
        return f"{value:,.{decimals}f}{suffix}"
    if isinstance(value, (int, float)):
        return f"{value:,.0f}{suffix}" if isinstance(value, float) else f"{value:,}{suffix}"
    return f"{value}{suffix}"


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------

def _draw_cover(
    c: canvas.Canvas, width: float, height: float,
    project: dict, plan: dict, qr_url: str | None = None,
) -> None:
    _paper(c, width, height)

    _eyebrow(c, MARGIN, height - 70, "Space Planning Report")

    c.setFillColor(INK)
    c.setFont(SERIF, 46)
    c.drawString(MARGIN, height - 132, project.get("building") or "Untitled Building")

    c.setFont(SERIF, 19)
    c.setFillColor(INK_2)
    c.drawString(MARGIN, height - 166, project.get("client") or "Client")

    # Accent rule under the title block.
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2.4)
    c.line(MARGIN, height - 188, MARGIN + 120, height - 188)

    # Title block — labelled fields, em-dash when absent.
    fields = [
        ("Client / Landlord", project.get("client")),
        ("Building", project.get("building")),
        ("Floor", project.get("floor")),
        ("Design style", project.get("style")),
        ("Gross area", _area(plan.get("gross_area_sf"), plan.get("units"))),
        ("Usable area", _area(plan.get("usable_area_sf"), plan.get("units"))),
    ]
    y = height - 260
    for label, value in fields:
        c.setFont(SANS_BOLD, 7.5)
        c.setFillColor(MUTED)
        c.drawString(MARGIN, y, _spaced(label.upper()))
        c.setFont(SERIF, 16)
        c.setFillColor(INK)
        c.drawString(MARGIN, y - 22, value if value not in (None, "") else EM_DASH)
        y -= 56

    c.setFont(SANS, 8)
    c.setFillColor(MUTED)
    c.drawRightString(width - MARGIN, height - 70, "3 alternatives  ·  A / B / C")

    if qr_url:
        qr_size = 96.0
        qr_x = width - MARGIN - qr_size
        qr_y = 72
        draw_qr(c, qr_url, qr_x, qr_y, qr_size)
        c.setFont(SANS_BOLD, 7.5)
        c.setFillColor(MUTED)
        c.drawString(qr_x, qr_y + qr_size + 8, _spaced("SCAN · OPEN IN DSOURCE"))

    _footer(c, width, project, "Cover")


def _area(value, units: str | None) -> str | None:
    if value is None:
        return None
    unit = "sf" if (units or "").lower() in ("", "feet", "ft", "sf") else (units or "")
    return f"{value:,.0f} {unit}".strip()


# ---------------------------------------------------------------------------
# Render page — the photoreal visualization, contained inside a margin, aspect-correct
# ---------------------------------------------------------------------------

def _draw_render_page(
    c: canvas.Canvas, width: float, height: float, project: dict, render: ImageReader,
) -> None:
    _paper(c, width, height)
    top = height - 64
    _eyebrow(c, MARGIN, top, "Visualization")
    c.setFillColor(INK)
    c.setFont(SERIF, 30)
    c.drawString(MARGIN, top - 32, "Photoreal render")
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2.0)
    c.line(MARGIN, top - 46, MARGIN + 70, top - 46)

    # Fit the image, preserving aspect, inside the region below the title and above the footer.
    region_x0 = MARGIN
    region_y0 = 58
    region_x1 = width - MARGIN
    region_y1 = top - 62
    iw, ih = render.getSize()
    scale = min((region_x1 - region_x0) / iw, (region_y1 - region_y0) / ih)
    draw_w = iw * scale
    draw_h = ih * scale
    img_x = region_x0 + (region_x1 - region_x0 - draw_w) / 2
    img_y = region_y0 + (region_y1 - region_y0 - draw_h) / 2
    c.drawImage(render, img_x, img_y, draw_w, draw_h)
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(img_x, img_y, draw_w, draw_h, fill=0, stroke=1)

    _footer(c, width, project, "Visualization")


# ---------------------------------------------------------------------------
# Alternative page — metrics sidebar + to-scale plan
# ---------------------------------------------------------------------------

SIDEBAR_W = 210.0


def _draw_alternative_page(
    c: canvas.Canvas, width: float, height: float,
    project: dict, plan: dict, alt: dict,
) -> None:
    _paper(c, width, height)
    alt_id = alt.get("id", "?")
    metrics = alt.get("metrics", {}) or {}
    testfit = alt.get("testfit", {}) or {}

    top = height - 64
    _eyebrow(c, MARGIN, top, f"Alternative {alt_id}")
    c.setFillColor(INK)
    c.setFont(SERIF, 30)
    c.drawString(MARGIN, top - 32, f"Option {alt_id}")
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2.0)
    c.line(MARGIN, top - 46, MARGIN + 70, top - 46)

    _metrics_sidebar(c, MARGIN, top - 78, metrics)

    # Plan drawing region: right of the sidebar, above the legend.
    plan_x0 = MARGIN + SIDEBAR_W + 24
    plan_x1 = width - MARGIN
    plan_y0 = 92  # leave room for legend + scale bar
    plan_y1 = top - 8
    _draw_plan(c, plan, testfit, plan_x0, plan_y0, plan_x1, plan_y1)

    _legend(c, plan_x0, 58, _present_types(testfit))
    _footer(c, width, project, f"Alternative {alt_id}")


def _metrics_sidebar(c: canvas.Canvas, x: float, y: float, m: dict) -> None:
    # Hero figure — seats, in the accent. The single most important number on the page.
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y, _spaced("SEATS"))
    c.setFont(SERIF_BOLD, 52)
    c.setFillColor(ACCENT)
    c.drawString(x, y - 50, _fmt(m.get("seats")))

    rows = [
        ("Usable area", _fmt(m.get("usf"), " sf")),
        ("Open-space seats", _fmt(m.get("open_space_seats"))),
        ("Private offices", _fmt(m.get("offices"))),
        ("Conference rooms", _fmt(m.get("conf_rooms"))),
        ("Density", _fmt(m.get("density_sf_per_person"), " sf/person", decimals=0)),
        ("Daylight", _fmt(m.get("daylight_pct"), "%", decimals=0)),
        ("Privacy", _fmt(m.get("privacy_pct"), "%", decimals=0)),
        ("Efficiency", _fmt(m.get("efficiency_pct"), "%", decimals=0)),
    ]
    ry = y - 86
    for label, value in rows:
        c.setStrokeColor(LINE)
        c.setLineWidth(0.6)
        c.line(x, ry + 17, x + SIDEBAR_W - 10, ry + 17)
        c.setFont(SANS, 8)
        c.setFillColor(INK_2)
        c.drawString(x, ry, label)
        c.setFont(SERIF, 13)
        c.setFillColor(INK)
        c.drawRightString(x + SIDEBAR_W - 10, ry - 1, value)
        ry -= 34


def _present_types(testfit: dict) -> list[str]:
    seen: list[str] = []
    for inst in testfit.get("instances", []):
        t = inst.get("type")
        if t and t not in seen:
            seen.append(t)
    return seen


# ---------------------------------------------------------------------------
# Plan drawing — aspect-correct world->page transform, Y flipped to read as a plan
# ---------------------------------------------------------------------------

def _draw_plan(
    c: canvas.Canvas, plan: dict, testfit: dict,
    x0: float, y0: float, x1: float, y1: float,
) -> None:
    boundary = plan.get("boundary") or []
    instances = testfit.get("instances", []) or []

    bbox = _world_bbox(boundary, instances)
    if bbox is None:
        c.setFont(SANS, 9)
        c.setFillColor(MUTED)
        c.drawString(x0, (y0 + y1) / 2, "No plan geometry provided.")
        return
    wx0, wy0, wx1, wy1 = bbox
    world_w = max(wx1 - wx0, 1e-6)
    world_h = max(wy1 - wy0, 1e-6)

    avail_w = x1 - x0
    avail_h = y1 - y0
    scale = min(avail_w / world_w, avail_h / world_h)
    # Centre the drawing in the available region.
    draw_w = world_w * scale
    draw_h = world_h * scale
    off_x = x0 + (avail_w - draw_w) / 2
    off_y = y0 + (avail_h - draw_h) / 2

    def tx(wx: float) -> float:
        return off_x + (wx - wx0) * scale

    def ty(wy: float) -> float:
        # Flip Y: world-up maps to page-up but anchored at the region bottom.
        return off_y + (wy - wy0) * scale

    # Cores (filled) and columns first, under the furniture.
    c.setFillColor(LINE)
    c.setStrokeColor(INK_2)
    c.setLineWidth(0.6)
    for core in plan.get("cores") or []:
        _polygon(c, [(tx(px), ty(py)) for px, py in core], fill=1, stroke=1)
    c.setFillColor(INK_2)
    for col in plan.get("columns") or []:
        cx, cy = col
        r = max(1.4, 0.6 * scale)
        c.circle(tx(cx), ty(cy), r, fill=1, stroke=0)

    # Boundary as ink linework, drawn over fills.
    if boundary:
        c.setStrokeColor(INK)
        c.setLineWidth(1.4)
        _polygon(c, [(tx(px), ty(py)) for px, py in boundary], fill=0, stroke=1, close=True)

    # Furniture instances — filled + stroked rects, coloured by type.
    c.setLineWidth(0.5)
    for inst in instances:
        ix = inst.get("x")
        iy = inst.get("y")
        iw = inst.get("w")
        ih = inst.get("h")
        if None in (ix, iy, iw, ih):
            continue
        c.setFillColor(ROOM_FILL.get(inst.get("type"), HexColor("#E4DED3")))
        c.setStrokeColor(INK)
        c.rect(tx(ix), ty(iy), iw * scale, ih * scale, fill=1, stroke=1)

    _scale_bar(c, x0, y0 - 2, scale)


def _world_bbox(boundary: list, instances: list) -> tuple[float, float, float, float] | None:
    xs: list[float] = []
    ys: list[float] = []
    for px, py in boundary:
        xs.append(px)
        ys.append(py)
    for inst in instances:
        if None in (inst.get("x"), inst.get("y"), inst.get("w"), inst.get("h")):
            continue
        xs.extend([inst["x"], inst["x"] + inst["w"]])
        ys.extend([inst["y"], inst["y"] + inst["h"]])
    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _polygon(c: canvas.Canvas, pts: Iterable[tuple[float, float]],
             fill: int, stroke: int, close: bool = True) -> None:
    pts = list(pts)
    if len(pts) < 2:
        return
    p = c.beginPath()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    if close:
        p.close()
    c.drawPath(p, fill=fill, stroke=stroke)


def _scale_bar(c: canvas.Canvas, x: float, y: float, scale: float) -> None:
    # Pick a round footage that draws to a sensible width, then label it.
    for feet in (5, 10, 20, 25, 50, 100):
        if feet * scale >= 60:
            break
    bar = feet * scale
    c.setStrokeColor(INK)
    c.setLineWidth(1.2)
    c.line(x, y, x + bar, y)
    c.line(x, y - 3, x, y + 3)
    c.line(x + bar, y - 3, x + bar, y + 3)
    c.setFont(SANS, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y - 12, f"0")
    c.drawRightString(x + bar, y - 12, f"{feet} ft")


def _legend(c: canvas.Canvas, x: float, y: float, types: list[str]) -> None:
    if not types:
        return
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y + 14, _spaced("LEGEND"))
    cx = x
    for t in types:
        c.setFillColor(ROOM_FILL.get(t, HexColor("#E4DED3")))
        c.setStrokeColor(INK)
        c.setLineWidth(0.5)
        c.rect(cx, y, 11, 11, fill=1, stroke=1)
        c.setFont(SANS, 8)
        c.setFillColor(INK_2)
        label = ROOM_LABEL.get(t, t)
        c.drawString(cx + 16, y + 2, label)
        cx += 22 + c.stringWidth(label, SANS, 8) + 16


# ---------------------------------------------------------------------------
# Summary — comparison table + bar comparison
# ---------------------------------------------------------------------------

SUMMARY_ROWS = [
    ("Usable area (sf)", "usf", " sf", None),
    ("Seats", "seats", "", None),
    ("Open-space seats", "open_space_seats", "", None),
    ("Private offices", "offices", "", None),
    ("Conference rooms", "conf_rooms", "", None),
    ("Density (sf/person)", "density_sf_per_person", "", 0),
    ("Daylight", "daylight_pct", "%", 0),
    ("Privacy", "privacy_pct", "%", 0),
    ("Efficiency", "efficiency_pct", "%", 0),
]


def _draw_summary_page(
    c: canvas.Canvas, width: float, height: float,
    project: dict, alternatives: list,
) -> None:
    _paper(c, width, height)
    top = height - 64
    _eyebrow(c, MARGIN, top, "Comparison")
    c.setFillColor(INK)
    c.setFont(SERIF, 30)
    c.drawString(MARGIN, top - 32, "Alternatives at a glance")
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2.0)
    c.line(MARGIN, top - 46, MARGIN + 70, top - 46)

    alts = list(alternatives)
    label_w = 220.0
    col_w = 120.0
    table_x = MARGIN
    table_y = top - 86

    # Header row — option ids.
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(table_x, table_y, _spaced("METRIC"))
    for i, alt in enumerate(alts):
        cx = table_x + label_w + i * col_w
        c.setFont(SERIF, 15)
        c.setFillColor(INK)
        c.drawRightString(cx + col_w - 18, table_y - 2, f"Option {alt.get('id', '?')}")
    c.setStrokeColor(INK)
    c.setLineWidth(1.0)
    c.line(table_x, table_y - 12, table_x + label_w + len(alts) * col_w, table_y - 12)

    ry = table_y - 34
    for label, key, suffix, decimals in SUMMARY_ROWS:
        c.setFont(SANS, 9)
        c.setFillColor(INK_2)
        c.drawString(table_x, ry, label)
        values = [(alt.get("metrics", {}) or {}).get(key) for alt in alts]
        best = _best_index(key, values)
        for i, val in enumerate(values):
            cx = table_x + label_w + i * col_w
            c.setFont(SERIF, 13)
            c.setFillColor(ACCENT if i == best else INK)
            c.drawRightString(cx + col_w - 18, ry, _fmt(val, suffix, decimals))
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(table_x, ry - 10, table_x + label_w + len(alts) * col_w, ry - 10)
        ry -= 28

    # Two charts side by side below the table: seat totals (left) and the space-mix split (right).
    charts_y = ry - 24
    gutter = 40.0
    col = (label_w + len(alts) * col_w - gutter) / 2
    _seat_bars(c, table_x, charts_y, col, alts)
    _space_mix_bars(c, table_x + col + gutter, charts_y, col, alts)
    _footer(c, width, project, "Summary")


def _best_index(key: str, values: list) -> int | None:
    """Highlight the strongest option per metric. Lower is better only for density."""
    present = [(i, v) for i, v in enumerate(values) if isinstance(v, (int, float))]
    if not present:
        return None
    lower_is_better = key == "density_sf_per_person"
    return min(present, key=lambda p: p[1])[0] if lower_is_better else max(present, key=lambda p: p[1])[0]


def _seat_bars(c: canvas.Canvas, x: float, y: float, width: float, alts: list) -> None:
    seats = [(alt.get("metrics", {}) or {}).get("seats") for alt in alts]
    nums = [s for s in seats if isinstance(s, (int, float))]
    if not nums:
        return
    peak = max(nums) or 1
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y + 14, _spaced("SEATS"))
    bar_max = max(width - 100, 20)  # leave room for the option label + the value readout
    for i, alt in enumerate(alts):
        s = seats[i]
        by = y - i * 22
        c.setFont(SERIF, 11)
        c.setFillColor(INK)
        c.drawString(x, by - 2, f"Option {alt.get('id', '?')}")
        if not isinstance(s, (int, float)):
            c.setFont(SANS, 8)
            c.setFillColor(MUTED)
            c.drawString(x + 60, by - 2, EM_DASH)
            continue
        w = bar_max * (s / peak)
        c.setFillColor(ACCENT)
        c.rect(x + 60, by - 6, w, 9, fill=1, stroke=0)
        c.setFont(SERIF, 11)
        c.setFillColor(INK_2)
        c.drawString(x + 60 + w + 6, by - 4, _fmt(s))


# Space-mix segments — open-plan seats, private offices, conference rooms — each with its own
# soft fill (reusing the plan legend colours), so the split reads consistently across the report.
_MIX_SEGMENTS = [
    ("open_space_seats", "Open-plan", ROOM_FILL["workstation"]),
    ("offices", "Offices", ROOM_FILL["private_office"]),
    ("conf_rooms", "Conference", ROOM_FILL["meeting_room"]),
]


def _space_mix_bars(c: canvas.Canvas, x: float, y: float, width: float, alts: list) -> None:
    """Per-option stacked bar of the space mix (open seats / offices / conference), by count."""
    c.setFont(SANS_BOLD, 7.5)
    c.setFillColor(MUTED)
    c.drawString(x, y + 14, _spaced("SPACE MIX"))
    bar_max = max(width - 60, 20)
    totals = []
    for alt in alts:
        m = alt.get("metrics", {}) or {}
        totals.append(sum(m.get(k) or 0 for k, _, _ in _MIX_SEGMENTS))
    peak = max(totals) or 1
    for i, alt in enumerate(alts):
        m = alt.get("metrics", {}) or {}
        by = y - i * 22
        c.setFont(SERIF, 11)
        c.setFillColor(INK)
        c.drawString(x, by - 2, f"Option {alt.get('id', '?')}")
        cx = x + 60
        scale = bar_max / peak
        for key, _label, fill in _MIX_SEGMENTS:
            seg = (m.get(key) or 0) * scale
            if seg <= 0:
                continue
            c.setFillColor(fill)
            c.setStrokeColor(INK)
            c.setLineWidth(0.4)
            c.rect(cx, by - 6, seg, 9, fill=1, stroke=1)
            cx += seg
        if totals[i] == 0:
            c.setFont(SANS, 8)
            c.setFillColor(MUTED)
            c.drawString(x + 60, by - 2, EM_DASH)
    # Segment legend under the bars.
    ly = y - len(alts) * 22 - 6
    lx = x
    for _key, label, fill in _MIX_SEGMENTS:
        c.setFillColor(fill)
        c.setStrokeColor(INK)
        c.setLineWidth(0.4)
        c.rect(lx, ly, 9, 9, fill=1, stroke=1)
        c.setFont(SANS, 7.5)
        c.setFillColor(INK_2)
        c.drawString(lx + 13, ly + 1, label)
        lx += 22 + c.stringWidth(label, SANS, 7.5)
