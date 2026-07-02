"""Three test-fit alternatives (A/B/C) — the Qbiq "we return 3 layouts" behaviour.

Qbiq hands the client three distinct furnished layouts scored on the SAME metrics so they can
trade off open vs. enclosed, density vs. privacy. We reproduce that by running the existing
procedural layout engine three times with deterministically varied program parameters, then
scoring each with `compute_metrics`. No randomness: the same plan always yields the same three.

The three flavours, derived by scaling the base program:
  A — Balanced   : the program as given (or the engine defaults).
  B — Open plan  : denser (lower rsf/person), fewer enclosed rooms, smaller desks, more collab.
  C — Enclosed   : more private offices + meeting rooms, lower density, less collab.

`plan` and each alternative's `testfit` use the exact dict shapes the /api/testfit endpoint
returns, via the shared `payloads` builders (DB-free) so this module — and the metrics tests
that exercise it — stay free of the testfit router's database/catalog imports.
"""

from __future__ import annotations

from ..floorplan.dxf_ingest import PlanModel
from .layout import (
    ProgramSpec,
    WorkstationSpec,
    generate_mixed_layout,
)
from .metrics import compute_metrics
from .payloads import plan_payload, testfit_payload
from .scoring import score_variants


def _privacy_match(privacy_pct: float, target: float) -> float:
    """Dial-intent fidelity for dial-driven variants: how close the variant's enclosed-occupant
    share lands to the target the program implied. 1.0 at target, falling to 0 a half off it."""
    return 1.0 - min(1.0, abs(privacy_pct - target) / 0.5)


def _variants(
    base: ProgramSpec, base_spec: WorkstationSpec
) -> list[tuple[str, ProgramSpec, WorkstationSpec]]:
    """Build the three (id, program, workstation-spec) parameter sets from a base program + spec.

    Scaling factors are fixed constants (deterministic). Ratios are clamped so an aggressive
    base program can't push a variant past sane bounds. The base WorkstationSpec carries the
    desk geometry (width/depth) so an upstream caller (e.g. the Concept program) sees its desk
    size flow into every variant; only variant B tightens the desk to express "denser open plan".
    """
    from dataclasses import replace

    return [
        ("A", base, base_spec),
        (
            "B",
            ProgramSpec(
                headcount=base.headcount,
                density_rsf_per_person=base.density_rsf_per_person * 0.8,
                workstation_ratio=base.workstation_ratio,
                private_office_ratio=base.private_office_ratio * 0.5,
                meeting_ratio=base.meeting_ratio * 0.75,
                collaboration_ratio=base.collaboration_ratio * 1.3,
            ),
            replace(base_spec, width_ft=base_spec.width_ft * 0.85, depth_ft=base_spec.depth_ft * 0.9),
        ),
        (
            "C",
            ProgramSpec(
                headcount=base.headcount,
                density_rsf_per_person=base.density_rsf_per_person * 1.2,
                workstation_ratio=base.workstation_ratio,
                private_office_ratio=min(0.4, base.private_office_ratio * 2.2),
                meeting_ratio=base.meeting_ratio * 1.4,
                collaboration_ratio=base.collaboration_ratio * 0.7,
            ),
            base_spec,
        ),
    ]


def generate_alternatives(
    plan: PlanModel,
    program: ProgramSpec | None = None,
    n: int = 3,
    spec: WorkstationSpec | None = None,
    target_privacy: float | None = None,
) -> dict:
    """Generate up to `n` (default 3) distinct scored, ranked test-fits for one floor plate.

    Each alternative = `generate_mixed_layout` under a varied program/spec, scored by
    `compute_metrics` then ranked by `score_variants`. `target_privacy` is the enclosed-occupant
    share the program intends (the Concept dial passes its `closed_ratio`); when omitted it falls
    back to the base program's private-office ratio. Deterministic: identical input -> identical
    output. `spec` sets the base desk geometry the variants spread around.
    """
    base = program or ProgramSpec()
    base_spec = spec or WorkstationSpec()
    target = target_privacy if target_privacy is not None else base.private_office_ratio
    alternatives = []
    for alt_id, prog, spec in _variants(base, base_spec)[:n]:
        fit = generate_mixed_layout(plan, spec, prog)
        metrics = compute_metrics(plan, fit)
        alternatives.append({
            "id": alt_id,
            "testfit": testfit_payload(fit),
            "metrics": metrics,
            "program_match": _privacy_match(metrics["privacy_pct"], target),
        })
    score_variants(alternatives)
    return {"plan": plan_payload(plan), "alternatives": alternatives}
