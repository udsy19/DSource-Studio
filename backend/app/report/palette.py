"""Warm-paper palette for the PDF deliverables — the single source of the report's colour tokens.

Mirrors the frontend design tokens (warm paper, ink linework, one terracotta accent). Shared by the
report pages and the QR block so every deliverable draws from one palette, never a divergent copy.
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor

PAPER = HexColor("#FAF7F2")
INK = HexColor("#1C1A17")
INK_2 = HexColor("#4A453E")
MUTED = HexColor("#8A8278")
LINE = HexColor("#D9D2C6")
ACCENT = HexColor("#C0613B")  # terracotta — the single accent
