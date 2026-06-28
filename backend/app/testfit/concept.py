"""Concept-mode generative space planning — Qbiq's "Concept" inputs -> 3 test-fit variants.

A user describes a simple PROGRAM with four high-level dials (planning style, desk type, desk
size, seat distribution) instead of the engine's low-level specs. This module maps that program
onto the existing `ProgramSpec` + `WorkstationSpec`, then drives the EXISTING alternatives engine
so the concept sets the base layout and the three A/B/C variants spread around it.

Nothing here invents geometry or counts — it only translates the four dials into the specs the
procedural layout engine already consumes. Deterministic: same program -> same output.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..floorplan.dxf_ingest import PlanModel
from .alternatives import generate_alternatives
from .layout import ProgramSpec, WorkstationSpec

# Base private-office share per planning style, BEFORE the seat-distribution dial scales it.
# Traditional plates are closed-office heavy, modern are open-plan heavy, cowork sits between.
_STYLE_OFFICE_BASE = {
    "traditional": 0.30,
    "cowork": 0.15,
    "modern": 0.06,
}


class ConceptProgram(BaseModel):
    """The four Qbiq Concept dials a user sets (plus desk geometry split into width/depth)."""

    planning_style: str = Field("modern", pattern="^(traditional|modern|cowork)$")
    desk_type: str = Field("workstations", pattern="^(workstations|benchings)$")
    desk_width_cm: int = Field(140, gt=0)
    desk_depth_cm: int = Field(70, gt=0)
    closed_ratio: float = Field(0.2, ge=0.0, le=1.0)


def concept_to_specs(concept: ConceptProgram, plan: PlanModel) -> tuple[ProgramSpec, WorkstationSpec]:
    """Translate the Concept program into the engine's (ProgramSpec, WorkstationSpec).

    Office share:
      planning_style picks a base private-office ratio (traditional 0.30 > cowork 0.15 > modern
      0.06). `closed_ratio` (the Seat Distribution, the user's share of seats in closed offices)
      scales that base around its mid-point of 0.2: ratio = base * (closed_ratio / 0.2), clamped
      to [0, 0.4] so the layout stays sane. So a higher closed_ratio always yields more offices,
      and for the same closed_ratio traditional yields more offices than modern.

    Desk geometry (cm -> ft, /30.48):
      width = desk_width_cm/30.48, depth = desk_depth_cm/30.48. `benchings` are shared long runs,
      so each desk position occupies a wider footprint than an individual `workstation` desk of the
      same nominal width — we widen benching desks by 1.4x to express the shared run. `plan` is
      accepted for symmetry with the engine's plan-driven derivation; office counts derive from
      headcount inside `derive_program`, so the plate only enters there.
    """
    base_office = _STYLE_OFFICE_BASE[concept.planning_style]
    office_ratio = min(0.4, max(0.0, base_office * (concept.closed_ratio / 0.2)))

    program = ProgramSpec(private_office_ratio=office_ratio)

    spec = WorkstationSpec.from_desk_cm(
        concept.desk_width_cm, concept.desk_depth_cm, benching=concept.desk_type == "benchings"
    )

    return program, spec


def generate_from_concept(plan: PlanModel, concept: ConceptProgram, n: int = 3) -> dict:
    """Build base specs from the Concept program, then return `n` scored A/B/C variants.

    Delegates to the existing `generate_alternatives` so the concept sets the base and the
    variants spread around it. Same `AlternativesResult` dict shape as /api/testfit/alternatives.
    """
    program, spec = concept_to_specs(concept, plan)
    return generate_alternatives(plan, program=program, n=n, spec=spec)
