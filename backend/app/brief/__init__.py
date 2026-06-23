"""Brief → Spec translation layer (Dsource Studio pillar).

Turns a high-level workplace BRIEF (what an HQ would tell you in a kickoff) into a structured
program SPEC the existing test-fit engine can consume. Deterministic heuristics, no LLM call.
"""

from .translate import Brief, translate_brief

__all__ = ["Brief", "translate_brief"]
