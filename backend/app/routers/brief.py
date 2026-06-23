"""Brief → Spec router (Dsource Studio "AI-Powered Brief Translation + Spec & Optimisation").

POST /api/brief/translate takes a high-level workplace Brief and returns:
  * `program`   — a ProgramSpec-compatible payload that drives the existing test-fit engine
                  (same field names as app.testfit.layout.ProgramSpec — splat-compatible).
  * `spec_sheet`— derived seat/area targets, the WELL checklist, and code/ADA clearances.
  * `warnings`  — internal conflicts (over-capacity, WELL-vs-density) flagged before placement.

Deterministic heuristics (no LLM, no DB). Register in app/main.py to expose it (see the README of
this pillar); not registered here to avoid editing main.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..brief.translate import Brief, translate_brief

router = APIRouter(prefix="/api/brief", tags=["brief"])


@router.post("/translate")
def translate(brief: Brief) -> dict:
    """Translate a high-level brief into {program, spec_sheet, warnings}.

    The returned `program` is shaped exactly like ProgramSpec, so a caller can chain it straight
    into the test-fit: `generate_mixed_layout(plan, program=ProgramSpec(**result["program"]))`.
    """
    return translate_brief(brief)
