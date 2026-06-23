"""BRIEF → SPEC translation (the "AI-Powered Brief Translation + Spec & Optimisation" pillar).

A real HQ kickoff brief is high-level prose: "we're a 220-person collaborative product org, we
want a Gold WELL outcome, ADA throughout, this is the Acme brand floor." This module turns that
into a *structured program spec* that the existing procedural test-fit engine
(`app.testfit.layout.ProgramSpec` / `derive_program`) can consume directly, PLUS a human-readable
SPEC SHEET (derived seat/area targets, WELL checklist, code clearances) and a list of WARNINGS
that flag internal conflicts before a single desk is placed.

DESIGN STANCE (matches the rest of the codebase): everything here is transparent, deterministic
heuristics, NOT an LLM call. The "AI" is the encoded domain logic — work-style → zone-mix maps,
WELL-target → checklist maps, and capacity arithmetic — all auditable and unit-testable. US/USD,
imperial units (rsf, sf, inches) throughout.

The three outputs of `translate_brief`:
  * `program`   — a ProgramSpec-compatible dict (same field names) → drives the test-fit.
  * `spec_sheet`— derived targets: total seats, per-zone target sf, WELL checklist, code clearances.
  * `warnings`  — conflicts (over-capacity vs a stated usable area; WELL target vs density; etc.).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Heuristic constants (sourced from the same Phase-0 norms used elsewhere in the codebase:
# app/floorplan/capacity.py and app/testfit/layout.py). Kept here so this module owns its own
# numbers and never imports/mutates files it doesn't own.
# ---------------------------------------------------------------------------

# Work-style → zone mix. Ratios are ProgramSpec-compatible (workstation/private_office/meeting/
# collaboration). They intentionally do NOT sum to 1.0: the leftover is shared/amenity/circulation,
# exactly as ProgramSpec treats them (the workstation field fills "whatever interior is left").
#   focus         — heads-down work: MORE workstations + private offices, FEWER meeting/collab.
#   collaborative — team work: FEWER workstations/offices, MORE meeting + collaboration.
#   hybrid        — the modern default, balanced (mirrors ProgramSpec's own defaults).
WORK_STYLE_MIX: dict[str, dict[str, float]] = {
    "focus": {
        "workstation_ratio": 0.55,
        "private_office_ratio": 0.18,
        "meeting_ratio": 0.10,
        "collaboration_ratio": 0.07,
    },
    "hybrid": {
        "workstation_ratio": 0.40,
        "private_office_ratio": 0.10,
        "meeting_ratio": 0.20,
        "collaboration_ratio": 0.15,
    },
    "collaborative": {
        "workstation_ratio": 0.28,
        "private_office_ratio": 0.05,
        "meeting_ratio": 0.32,
        "collaboration_ratio": 0.28,
    },
}

# Per-seat / per-zone area programming norms (sf), aligned with app/floorplan/capacity.py.
AREA_PER_SEAT = {
    "workstations": 48.0,
    "private_offices": 120.0,
    "meeting": 20.0,
    "collaboration": 25.0,
}
SEATS_PER_MEETING_ROOM = 6.0      # ~6 seats / meeting room (matches derive_program)
SEATS_PER_COLLAB_ZONE = 6.0       # ~6 people / collaboration lounge cluster

DEFAULT_DENSITY_RSF = 175.0       # typical modern office (matches ProgramSpec default)
DAYLIGHT_REACH_FT = 25.0          # workstations within this of glazing are "daylit" (wellbeing)

# WELL targets in ascending stringency. We attach a checklist whose bar rises with the tier; the
# 8 dimensions referenced are the same 8 the wellbeing scorer uses (light, acoustics, air,
# ergonomics, movement, social, biophilia, restoration).
WELL_TARGETS = ["none", "certified", "silver", "gold", "platinum"]
# Minimum daylight access (% of workstations within DAYLIGHT_REACH_FT of glazing) implied by tier.
WELL_DAYLIGHT_MIN = {
    "none": 0.0, "certified": 0.55, "silver": 0.65, "gold": 0.75, "platinum": 0.85,
}
# Max density (rsf/person) that still leaves room to HIT the daylight target at each tier. Denser
# plans push desks deep into the core, away from glazing — so a high WELL tier + high density is a
# conflict we warn about. (Looser tiers tolerate denser plans.)
WELL_DENSITY_CEILING_RSF = {
    "none": 0.0, "certified": 130.0, "silver": 150.0, "gold": 170.0, "platinum": 200.0,
}


# ---------------------------------------------------------------------------
# Input model — what an HQ would actually specify in a brief.
# ---------------------------------------------------------------------------

class Brief(BaseModel):
    """A high-level workplace brief. Everything an HQ states up front; we derive the rest."""

    headcount: int = Field(..., gt=0, description="People to seat in this space.")
    work_style: Literal["focus", "collaborative", "hybrid"] = Field(
        "hybrid", description="Primary way the org works → maps to a zone mix.")
    target_density_rsf_per_person: float = Field(
        DEFAULT_DENSITY_RSF, gt=0,
        description="Target rentable sf per person (US norm ~150-250; default 175).")
    well_target: Literal["none", "certified", "silver", "gold", "platinum"] = Field(
        "none", description="WELL Building Standard outcome target → drives the WELL checklist.")
    require_ada: bool = Field(
        True, description="Require ADA-compliant clearances/route in the spec sheet.")
    usable_area_sf: Optional[float] = Field(
        None, gt=0, description="If known, the usable area of the plate (sf) — enables capacity warnings.")
    notes: Optional[str] = Field(None, description="Free-text brief notes / requirements.")
    brand: Optional[str] = Field(None, description="Tenant/brand name for the spec sheet header.")


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def _program_from_brief(brief: Brief) -> dict:
    """Map the brief to a ProgramSpec-compatible dict (identical field names to ProgramSpec).

    The returned dict can be splatted straight into `ProgramSpec(**program)` so it drives the
    existing test-fit engine with no adapter.
    """
    mix = WORK_STYLE_MIX[brief.work_style]
    return {
        "headcount": int(brief.headcount),
        "density_rsf_per_person": float(brief.target_density_rsf_per_person),
        "workstation_ratio": mix["workstation_ratio"],
        "private_office_ratio": mix["private_office_ratio"],
        "meeting_ratio": mix["meeting_ratio"],
        "collaboration_ratio": mix["collaboration_ratio"],
    }


def _zone_targets(program: dict) -> dict:
    """Derived per-zone seat/room and target-sf programming (mirrors derive_program arithmetic)."""
    hc = program["headcount"]

    ws_seats = round(hc * program["workstation_ratio"])
    office_seats = round(hc * program["private_office_ratio"])
    meeting_seats = round(hc * program["meeting_ratio"])
    collab_seats = round(hc * program["collaboration_ratio"])

    # Rooms (not seats) for meeting/collab — same convention as derive_program.
    meeting_rooms = max(0, round(meeting_seats / SEATS_PER_MEETING_ROOM))
    collab_zones = max(0, round(collab_seats / SEATS_PER_COLLAB_ZONE))

    return {
        "total_seats": int(ws_seats + office_seats + meeting_seats + collab_seats),
        "workstations": {
            "seats": int(ws_seats),
            "target_sf": round(ws_seats * AREA_PER_SEAT["workstations"], 1),
        },
        "private_offices": {
            "rooms": int(office_seats),  # 1 person / private office
            "target_sf": round(office_seats * AREA_PER_SEAT["private_offices"], 1),
        },
        "meeting": {
            "rooms": int(meeting_rooms),
            "seats": int(meeting_seats),
            "target_sf": round(meeting_seats * AREA_PER_SEAT["meeting"], 1),
        },
        "collaboration": {
            "zones": int(collab_zones),
            "seats": int(collab_seats),
            "target_sf": round(collab_seats * AREA_PER_SEAT["collaboration"], 1),
        },
    }


def _well_checklist(well_target: str) -> list[dict]:
    """WELL checklist items implied by the target, tied to the 8 wellbeing dimensions.

    Each tier is cumulative-stricter: 'none' yields an empty checklist; higher tiers raise
    thresholds and add dimensions. Items are auditable spec lines, not a guess.
    """
    if well_target == "none":
        return []

    tier_idx = WELL_TARGETS.index(well_target)
    daylight_min = WELL_DAYLIGHT_MIN[well_target]
    items: list[dict] = []

    # light — daylight access threshold rises with tier.
    items.append({
        "dimension": "light",
        "requirement": f"Daylight access: >={int(daylight_min * 100)}% of workstations within "
                       f"{int(DAYLIGHT_REACH_FT)} ft of glazing",
        "tier": well_target,
    })
    # air — fresh-air dilution / filtration intent.
    items.append({
        "dimension": "air",
        "requirement": "Enhanced ventilation + MERV-13 filtration; low-VOC finishes specified",
        "tier": well_target,
    })
    # ergonomics — sit-stand + ergonomic seating (matches wellbeing BOM intent).
    items.append({
        "dimension": "ergonomics",
        "requirement": "Sit-stand desks + ergonomic task seating at 100% of workstations",
        "tier": well_target,
    })
    # movement — circulation / active-design intent (always present from certified up).
    items.append({
        "dimension": "movement",
        "requirement": "Active-design circulation: generous walkable spine, visible/accessible stairs",
        "tier": well_target,
    })

    # silver+ adds acoustic separation and social provision.
    if tier_idx >= WELL_TARGETS.index("silver"):
        items.append({
            "dimension": "acoustics",
            "requirement": "Acoustic separation: enclosed rooms STC>=45; open-plan NRC>=0.80 ceilings",
            "tier": well_target,
        })
        items.append({
            "dimension": "social",
            "requirement": "Social connection: dedicated collaboration/meeting zones per neighborhood",
            "tier": well_target,
        })

    # gold+ adds biophilia provision and restoration space — the stricter bar vs 'none'/'certified'.
    if tier_idx >= WELL_TARGETS.index("gold"):
        items.append({
            "dimension": "biophilia",
            "requirement": "Biophilia provision: interior planting + natural materials; views to nature",
            "tier": well_target,
        })
        items.append({
            "dimension": "restoration",
            "requirement": "Restoration: dedicated quiet/wellness/respite room(s) per floor",
            "tier": well_target,
        })

    # platinum tightens biophilia coverage further.
    if tier_idx >= WELL_TARGETS.index("platinum"):
        items.append({
            "dimension": "biophilia",
            "requirement": "Biophilia (platinum): planting in every neighborhood; circadian lighting",
            "tier": well_target,
        })

    return items


def _code_clearances(brief: Brief) -> list[dict]:
    """Code/ADA clearances implied by the brief. ADA route + egress when require_ada is set."""
    clearances: list[dict] = [
        # Egress is code regardless of ADA; we always state it.
        {"code": "egress", "requirement": "Maintain rated egress paths; 44 in min corridor at exits"},
    ]
    if brief.require_ada:
        clearances.extend([
            {"code": "ada_route",
             "requirement": "Accessible route >=36 in clear width (32 in min at doorways)"},
            {"code": "ada_turning",
             "requirement": "60 in turning circle / T-turn at accessible rooms & dead-ends"},
            {"code": "ada_clearance",
             "requirement": "Accessible workstation/desk clearances; reach ranges 15-48 in"},
        ])
    return clearances


def translate_brief(brief: Brief) -> dict:
    """Translate a Brief into {program, spec_sheet, warnings}.

    `program` is ProgramSpec-compatible (same field names) → feed it straight to the test-fit.
    `spec_sheet` is the derived, human-readable program: seat/area targets, WELL checklist, code
    clearances. `warnings` flags internal conflicts before placement.
    """
    program = _program_from_brief(brief)
    zones = _zone_targets(program)
    well = _well_checklist(brief.well_target)
    clearances = _code_clearances(brief)

    warnings: list[str] = []

    # --- Capacity conflict: headcount × density vs a stated usable area -------------------------
    # If the HQ told us the plate size, the program simply may not fit. headcount × density is the
    # rentable area the program *demands*; compare it to what's available.
    required_sf = brief.headcount * brief.target_density_rsf_per_person
    if brief.usable_area_sf is not None and required_sf > brief.usable_area_sf:
        over = required_sf - brief.usable_area_sf
        fits = int(brief.usable_area_sf / brief.target_density_rsf_per_person)
        warnings.append(
            f"Over-capacity: {brief.headcount} people @ {brief.target_density_rsf_per_person:.0f} "
            f"rsf/person needs ~{required_sf:,.0f} sf but only {brief.usable_area_sf:,.0f} sf is "
            f"usable (short ~{over:,.0f} sf). Plate fits ~{fits} people at this density — reduce "
            f"headcount or increase density target."
        )

    # --- WELL vs density conflict ----------------------------------------------------------------
    # A high WELL tier implies a daylight-access floor; a too-dense plan pushes desks away from
    # glazing and makes that floor unreachable. Flag when target density is below the tier ceiling.
    ceiling = WELL_DENSITY_CEILING_RSF.get(brief.well_target, 0.0)
    if ceiling and brief.target_density_rsf_per_person < ceiling:
        warnings.append(
            f"WELL/daylight conflict: '{brief.well_target}' implies "
            f">={int(WELL_DAYLIGHT_MIN[brief.well_target] * 100)}% daylight access, but "
            f"{brief.target_density_rsf_per_person:.0f} rsf/person is denser than the "
            f"~{ceiling:.0f} rsf/person needed to keep workstations near glazing — daylight "
            f"target likely unmet. Loosen density or lower the WELL target."
        )

    # --- Mild density sanity (US norm ~150-250 rsf/person) ---------------------------------------
    if brief.target_density_rsf_per_person < 100:
        warnings.append(
            f"Density {brief.target_density_rsf_per_person:.0f} rsf/person is very high-density "
            f"(US norm ~150-250); expect cramped circulation and acoustic strain."
        )

    spec_sheet = {
        "brand": brief.brand,
        "work_style": brief.work_style,
        "headcount": brief.headcount,
        "target_density_rsf_per_person": brief.target_density_rsf_per_person,
        "required_program_sf": round(required_sf, 1),
        "usable_area_sf": brief.usable_area_sf,
        "zone_mix": {
            "workstation_ratio": program["workstation_ratio"],
            "private_office_ratio": program["private_office_ratio"],
            "meeting_ratio": program["meeting_ratio"],
            "collaboration_ratio": program["collaboration_ratio"],
        },
        "total_seats": zones["total_seats"],
        "zones": {
            "workstations": zones["workstations"],
            "private_offices": zones["private_offices"],
            "meeting": zones["meeting"],
            "collaboration": zones["collaboration"],
        },
        "well_target": brief.well_target,
        "well_checklist": well,
        "code_clearances": clearances,
        "currency": "USD",
        "units": "imperial",
        "notes": brief.notes,
    }

    return {"program": program, "spec_sheet": spec_sheet, "warnings": warnings}
