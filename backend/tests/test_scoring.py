"""Variant scoring + ranking tests — pure, no plan/DB/geometry.

Exercises `score_variants` (composite + ranking + a single recommended) and the Detailed
per-type `_program_match`, which must penalise dropping a requested type even when another type
is overplaced — an aggregate placed/requested ratio would hide exactly that.
"""

import pytest

from app.testfit.detailed import _program_match
from app.testfit.scoring import score_variants


def _variant(id_: str, seats: int, daylight: float, efficiency: float, match: float) -> dict:
    return {
        "id": id_,
        "metrics": {"seats": seats, "daylight_pct": daylight, "efficiency_pct": efficiency},
        "program_match": match,
    }


def test_exactly_one_recommended():
    vs = score_variants([
        _variant("A", 10, 0.5, 0.5, 0.5),
        _variant("B", 20, 0.5, 0.5, 0.5),
        _variant("C", 5, 0.5, 0.5, 0.5),
    ])
    assert sum(1 for v in vs if v["recommended"]) == 1


def test_all_ones_scores_one():
    vs = score_variants([_variant("A", 10, 1.0, 1.0, 1.0)])
    assert vs[0]["score"] == 1.0


def test_all_zeros_scores_zero():
    vs = score_variants([_variant("A", 0, 0.0, 0.0, 0.0)])
    assert vs[0]["score"] == 0.0


def test_seat_yield_is_batch_relative():
    vs = score_variants([_variant("A", 100, 0.0, 0.0, 0.0), _variant("B", 50, 0.0, 0.0, 0.0)])
    a = next(v for v in vs if v["id"] == "A")
    b = next(v for v in vs if v["id"] == "B")
    assert a["score_breakdown"]["seat_yield"] == 1.0
    assert b["score_breakdown"]["seat_yield"] == 0.5


def test_program_match_dominates_when_other_axes_tie():
    vs = score_variants([_variant("A", 10, 0.5, 0.5, 0.9), _variant("B", 10, 0.5, 0.5, 0.2)])
    rec = next(v for v in vs if v["recommended"])
    assert rec["id"] == "A"


def test_ranking_is_stable_on_a_tie():
    """Identical scores -> lowest id wins, regardless of input order (deterministic)."""
    vs = score_variants([_variant("B", 10, 0.5, 0.5, 0.5), _variant("A", 10, 0.5, 0.5, 0.5)])
    rec = next(v for v in vs if v["recommended"])
    assert rec["id"] == "A"


def test_breakdown_keys_and_ranges():
    vs = score_variants([_variant("A", 10, 0.5, 0.5, 0.5)])
    bd = vs[0]["score_breakdown"]
    assert set(bd) == {"program_match", "seat_yield", "daylight", "efficiency"}
    assert all(0.0 <= x <= 1.0 for x in bd.values())


def test_raw_program_match_input_is_folded_not_leaked():
    vs = score_variants([_variant("A", 10, 0.5, 0.5, 0.7)])
    assert "program_match" not in vs[0]  # folded into the breakdown, not left on the payload
    assert vs[0]["score_breakdown"]["program_match"] == 0.7


def test_program_match_penalises_dropped_type_not_aggregate():
    """The required guard: a variant that drops one requested type but overplaces another must
    score lower than one honouring every type. An aggregate sum(placed)/sum(requested) would
    clamp 4/3 -> 1.0 and hide the drop; per-type averaging cannot."""
    requested = {"meeting": 1, "huddle": 2}
    honoured = _program_match({"meeting": 1, "huddle": 2}, requested)
    dropped_one_overplaced_other = _program_match({"meeting": 0, "huddle": 4}, requested)

    assert honoured == 1.0
    assert dropped_one_overplaced_other < honoured
    assert dropped_one_overplaced_other == pytest.approx(0.5)  # mean(0/1, min(1, 4/2)) = mean(0, 1)
