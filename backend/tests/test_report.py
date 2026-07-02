"""The Space Planning Report renders a valid 5-page PDF from a ReportData payload.

Deterministic, no network. Page count is asserted by counting `/Type /Page` objects in the
raw PDF (avoids adding a pypdf test dependency).
"""

from app.report.service import build_report_pdf

# A 1x1 PNG (transparent), the smallest thing ImageReader can decode — for the render-page tests.
_TINY_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _count_pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ")


def _instances() -> list[dict]:
    # A handful of each type laid out on a 60x40 ft grid (world feet).
    out: list[dict] = []
    for col in range(4):
        out.append({"type": "workstation", "x": 5 + col * 6, "y": 5, "w": 5, "h": 4, "rotation": 0})
    out.append({"type": "private_office", "x": 5, "y": 22, "w": 10, "h": 10, "rotation": 0})
    out.append({"type": "private_office", "x": 17, "y": 22, "w": 10, "h": 10, "rotation": 0})
    out.append({"type": "meeting_room", "x": 32, "y": 22, "w": 14, "h": 12, "rotation": 0})
    out.append({"type": "collaboration", "x": 32, "y": 5, "w": 14, "h": 10, "rotation": 0})
    return out


def _metrics(seats: int, offices: int) -> dict:
    return {
        "usf": 2400.0,
        "seats": seats,
        "open_space_seats": seats - offices,
        "offices": offices,
        "conf_rooms": 2,
        "density_sf_per_person": 2400.0 / max(seats, 1),
        "daylight_pct": 72.0,
        "privacy_pct": 48.0,
        "efficiency_pct": 85.0,
    }


def _report_data() -> dict:
    return {
        "project": {
            "client": "Meridian Estates",
            "building": "Two Harbour Square",
            "style": "Warm minimal",
            "floor": "Level 11",
        },
        "plan": {
            "boundary": [[0, 0], [60, 0], [60, 40], [0, 40]],
            "cores": [[[24, 16], [36, 16], [36, 28], [24, 28]]],
            "columns": [[15, 12], [45, 12], [15, 30], [45, 30]],
            "gross_area_sf": 2600.0,
            "usable_area_sf": 2400.0,
            "units": "feet",
        },
        "alternatives": [
            {"id": "A", "testfit": {"instances": _instances()}, "metrics": _metrics(48, 2)},
            {"id": "B", "testfit": {"instances": _instances()}, "metrics": _metrics(56, 1)},
            {"id": "C", "testfit": {"instances": _instances()}, "metrics": _metrics(40, 4)},
        ],
    }


def test_returns_pdf_bytes():
    pdf = build_report_pdf(_report_data())
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


def test_has_five_pages():
    pdf = build_report_pdf(_report_data())
    # cover + 3 alternatives + summary
    assert _count_pages(pdf) == 5


def test_render_page_added_only_when_present():
    without = build_report_pdf(_report_data())
    with_render = build_report_pdf({**_report_data(), "render_image": _TINY_PNG})
    # The render page appears (cover + render + 3 alternatives + summary), only when a render exists.
    assert _count_pages(with_render) == _count_pages(without) + 1 == 6


def test_undecodable_render_is_skipped_not_faked():
    data = {**_report_data(), "render_image": "data:image/png;base64,not-base64!!!"}
    pdf = build_report_pdf(data)
    # Bad image never crashes and never adds a blank page — the report degrades honestly.
    assert pdf.startswith(b"%PDF")
    assert _count_pages(pdf) == 5


def test_qr_url_renders_without_error():
    pdf = build_report_pdf({**_report_data(), "qr_url": "https://dsource.app/p/two-harbour"})
    assert pdf.startswith(b"%PDF")
    assert _count_pages(pdf) == 5  # the QR sits on the cover, adding no page


def test_missing_metric_renders_em_dash():
    data = _report_data()
    data["alternatives"][0]["metrics"]["seats"] = None
    pdf = build_report_pdf(data)
    # Still renders without fabricating a number.
    assert pdf.startswith(b"%PDF")
