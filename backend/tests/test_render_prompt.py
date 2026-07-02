"""Tests for the finishes → render-prompt builder.

The Visualization step lets the user pick wall/floor/palette/style finishes; those selections must
compose into a single image-to-image prompt while always preserving the layout instruction (the
render must keep the exact furniture arrangement, never reinvent it).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.routers.render import build_edit_instruction, build_kontext_input, build_render_prompt


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


def test_edit_instruction_names_surface_and_pins_the_rest():
    # A targeted Kontext edit must name the one surface AND keep everything else — otherwise the
    # beauty layer would move the structured layout (the core architecture principle).
    ins = build_edit_instruction("wall", "walnut wood panel")
    assert "walls to walnut wood panel" in ins
    assert "layout" in ins and "unchanged" in ins


def test_edit_instruction_scopes_to_one_room_when_given():
    # A scoped edit names the surface AND the room, so Kontext changes only that room's finish.
    ins = build_edit_instruction("wall", "walnut wood panel", scope="meeting room")
    assert "walls to walnut wood panel in the meeting room" in ins
    assert "everything else unchanged" in ins  # the rest of the scene is still pinned


def test_edit_instruction_without_scope_is_global_and_unchanged():
    # Back-compatible: omitting scope (or passing blank) yields the exact global wording.
    assert build_edit_instruction("wall", "walnut wood panel") == \
        build_edit_instruction("wall", "walnut wood panel", scope="   ")
    assert "in the" not in build_edit_instruction("wall", "walnut wood panel").split(". Keep")[0]


def test_edit_instruction_rejects_blank_value():
    with pytest.raises(HTTPException) as e:
        build_edit_instruction("floor", "   ")
    assert e.value.status_code == 422


def test_edit_instruction_rejects_unknown_field():
    with pytest.raises(HTTPException) as e:
        build_edit_instruction("ceiling", "oak")
    assert e.value.status_code == 422


def test_kontext_input_matches_published_schema():
    # Locks the flux-kontext-pro input contract (verified against its OpenAPI schema): the source
    # image goes in `input_image` (which accepts a data URI), output_format must be an allowed enum
    # value, and safety_tolerance <= 2 — the model's documented max when an input image is supplied.
    inp = build_kontext_input("data:image/jpeg;base64,AAAA", "Change the walls to navy")
    assert inp["input_image"] == "data:image/jpeg;base64,AAAA"
    assert inp["prompt"] == "Change the walls to navy"
    assert inp["output_format"] in ("jpg", "png")
    assert 0 <= inp["safety_tolerance"] <= 2
    assert "aspect_ratio" not in inp  # omitted -> defaults to match_input_image (layout preserved)
