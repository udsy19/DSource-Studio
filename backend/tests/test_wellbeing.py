"""Wellbeing scoring tests — fast (geometry only, no DB/PDF)."""

from pathlib import Path

import pytest

from app.floorplan.dxf_ingest import ingest_dxf
from app.testfit.layout import ProgramSpec, WorkstationSpec, generate_mixed_layout
from app.wellbeing.score import WEIGHTS, score_wellbeing

DXF = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"
pytestmark = pytest.mark.skipif(not DXF.exists(), reason="sample DXF not generated")


def _score():
    plan = ingest_dxf(str(DXF))
    fit = generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())
    return score_wellbeing(plan, fit)


def test_overall_and_dimensions():
    ws = _score()
    assert 0 <= ws.overall <= 100
    assert len(ws.dimensions) == 8
    assert {d.key for d in ws.dimensions} == set(WEIGHTS)
    assert all(0 <= d.score <= 100 for d in ws.dimensions)


def test_some_dimensions_are_measured_not_guessed():
    ws = _score()
    measured = [d.key for d in ws.dimensions if d.measured]
    # light/acoustics/movement/social come from real geometry, not proxies
    assert "light" in measured and "acoustics" in measured
    assert any(not d.measured for d in ws.dimensions)  # proxies are honestly flagged


def test_overall_is_weighted_average():
    ws = _score()
    expected = round(sum(d.score * WEIGHTS[d.key] for d in ws.dimensions))
    assert ws.overall == expected
