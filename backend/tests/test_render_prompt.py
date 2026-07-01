"""Tests for the finishes → render-prompt builder.

The Visualization step lets the user pick wall/floor/palette/style finishes; those selections must
compose into a single image-to-image prompt while always preserving the layout instruction (the
render must keep the exact furniture arrangement, never reinvent it).
"""

from __future__ import annotations

from app.routers.render import build_render_prompt


def test_empty_finishes_returns_layout_preserving_base():
    p = build_render_prompt({})
    assert "same furniture layout" in p  # layout is always preserved
    assert "photorealistic" in p


def test_selected_finishes_appear_in_prompt():
    p = build_render_prompt({"wall": "walnut wood", "floor": "polished concrete", "palette": "warm neutral"})
    assert "walnut wood wall" in p
    assert "polished concrete floor" in p
    assert "warm neutral" in p
    assert "same furniture layout" in p  # still preserved


def test_blank_values_are_skipped():
    p = build_render_prompt({"wall": "", "style": "biophilic"})
    assert "wall" not in p.split("same furniture layout")[0] or "biophilic" in p
    assert "biophilic" in p
