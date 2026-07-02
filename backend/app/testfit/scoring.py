"""Composite scoring + ranking for generated test-fit variants.

Each variant already carries `metrics` (compute_metrics) and a caller-supplied `program_match`
in [0,1] — how well it honoured what the user asked (explicit counts) or intended (dial closeness).
This folds those into one auditable composite, ranks the batch, and flags exactly one recommended.

`seat_yield` is BATCH-RELATIVE (a variant's seats over the batch max), so scores are comparable
only WITHIN one generation, never across runs — the UI must not invite cross-run comparison. Every
score ships with its `score_breakdown` so the number is auditable, never a bare decree (mirrors the
metrics' `*_basis` honesty discipline).
"""

from __future__ import annotations

# Composite weights (sum to 1.0). program_match LEADS at half the score — delivering the program
# the user asked for (or intended) is the point; a denser variant that ignores an enclosed brief
# must not out-score a faithful one on packing alone. The rest are quality tie-breakers among
# comparably faithful variants: daylight (wellbeing is first-class here) over seat_yield (density);
# efficiency (placeable/usable) is near-constant per plate, so it barely discriminates.
_W_MATCH = 0.50
_W_DAYLIGHT = 0.20
_W_SEATS = 0.15
_W_EFFICIENCY = 0.15


def score_variants(variants: list[dict]) -> list[dict]:
    """Attach `score`, `score_breakdown`, `recommended` to each variant (mutated in place, returned).

    Every variant needs `metrics` (with `seats`, `daylight_pct`, `efficiency_pct`) and a
    `program_match` float; the raw input is folded into the breakdown and removed. Ranking is
    deterministic — highest score wins, ties broken by lowest `id`, independent of input order.
    Array order is left untouched so callers keep their A/B/C labels meaningful.
    """
    max_seats = max((v["metrics"]["seats"] for v in variants), default=0) or 1
    for v in variants:
        m = v["metrics"]
        breakdown = {
            "program_match": round(float(v.pop("program_match")), 3),
            "seat_yield": round(m["seats"] / max_seats, 3),
            "daylight": round(m["daylight_pct"], 3),
            "efficiency": round(m["efficiency_pct"], 3),
        }
        v["score"] = round(
            _W_MATCH * breakdown["program_match"]
            + _W_SEATS * breakdown["seat_yield"]
            + _W_DAYLIGHT * breakdown["daylight"]
            + _W_EFFICIENCY * breakdown["efficiency"],
            3,
        )
        v["score_breakdown"] = breakdown

    best_id = min(variants, key=lambda v: (-v["score"], v["id"]))["id"]
    for v in variants:
        v["recommended"] = v["id"] == best_id
    return variants
