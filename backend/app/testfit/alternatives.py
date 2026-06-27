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
returns. Those builders are replicated here (not imported) so this module — and the metrics
tests that exercise it — stay free of the testfit router's database/catalog imports.
"""

from __future__ import annotations

from ..floorplan.dxf_ingest import PlanModel
from .layout import (
    ProgramSpec,
    TestFit,
    WorkstationSpec,
    generate_mixed_layout,
)
from .metrics import compute_metrics


def _plan_payload(plan: PlanModel) -> dict:
    return {
        "boundary": plan.boundary,
        "cores": plan.cores,
        "columns": plan.columns,
        "gross_area_sf": plan.gross_area_sf,
        "usable_area_sf": plan.usable_area_sf,
        "units": plan.units,
    }


def _testfit_payload(fit: TestFit) -> dict:
    return {
        "instances": [
            {"type": i.type, "x": i.x, "y": i.y, "w": i.w, "h": i.h, "rotation": i.rotation}
            for i in fit.instances
        ],
        "workstation_count": fit.workstation_count,
        "office_count": fit.office_count,
        "meeting_count": fit.meeting_count,
        "collab_count": fit.collab_count,
        "placeable_area_sf": fit.placeable_area_sf,
        "program": fit.program,
        "notes": fit.notes,
    }


def _variants(base: ProgramSpec) -> list[tuple[str, ProgramSpec, WorkstationSpec]]:
    """Build the three (id, program, workstation-spec) parameter sets from a base program.

    Scaling factors are fixed constants (deterministic). Ratios are clamped so an aggressive
    base program can't push a variant past sane bounds.
    """
    return [
        ("A", base, WorkstationSpec()),
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
            WorkstationSpec(width_ft=5.0, depth_ft=4.5),
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
            WorkstationSpec(),
        ),
    ]


def generate_alternatives(
    plan: PlanModel,
    program: ProgramSpec | None = None,
    n: int = 3,
) -> dict:
    """Generate up to `n` (default 3) distinct scored test-fits for one floor plate.

    Each alternative = `generate_mixed_layout` under a varied program/spec, scored by
    `compute_metrics`. Deterministic: identical input -> identical output.
    """
    base = program or ProgramSpec()
    alternatives = []
    for alt_id, prog, spec in _variants(base)[:n]:
        fit = generate_mixed_layout(plan, spec, prog)
        alternatives.append({
            "id": alt_id,
            "testfit": _testfit_payload(fit),
            "metrics": compute_metrics(plan, fit),
        })
    return {"plan": _plan_payload(plan), "alternatives": alternatives}
