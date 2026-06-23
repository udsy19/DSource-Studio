"""Wellbeing-by-Design scoring — the signature Dsource Studio layer.

Scores a generated test-fit across the 8 wellbeing dimensions from the Studio deck
(air, acoustics, biophilia, light, ergonomics, movement, social connection, restoration),
plus an overall 0-100 Wellbeing Score — like the deck's "84" dashboard.

HONEST: several WELL dimensions genuinely depend on data a 2D test-fit can't see (real VOC
levels, planting, IoT air readings). Where that's true we use a documented geometric proxy
and FLAG it in the dimension's `basis` + the notes — we never present a guess as a sensor
reading. What IS derivable from the layout (daylight access, density/enclosure for acoustics,
circulation for movement, collaboration mix for social) is computed for real from geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon

from ..floorplan.dxf_ingest import PlanModel
from ..testfit.layout import TestFit

# WELL-weighted contribution of each dimension to the overall score (sums to 1.0).
WEIGHTS = {
    "light": 0.17, "acoustics": 0.15, "air": 0.13, "ergonomics": 0.12,
    "movement": 0.11, "social": 0.11, "biophilia": 0.11, "restoration": 0.10,
}
DAYLIGHT_REACH_FT = 25.0  # workstations within this of an exterior wall are "daylit"


@dataclass
class DimensionScore:
    key: str
    label: str
    score: int          # 0-100
    basis: str          # how it was derived (and whether modeled/assumed)
    measured: bool      # True = derived from geometry; False = proxy/assumption


@dataclass
class WellbeingScore:
    overall: int
    dimensions: list[DimensionScore] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _clamp(v: float, lo: float, hi: float) -> int:
    """Map v in [lo, hi] linearly to 0-100 (clamped)."""
    if hi == lo:
        return 50
    return int(max(0.0, min(1.0, (v - lo) / (hi - lo))) * 100)


def score_wellbeing(plan: PlanModel, fit: TestFit, density_rsf_per_person: float = 175.0,
                    circulation_factor: float = 0.35) -> WellbeingScore:
    boundary = Polygon(plan.boundary)
    ws = [i for i in fit.instances if i.type == "workstation"]
    n_ws = max(len(ws), 1)
    enclosed = fit.office_count + fit.meeting_count
    social_zones = fit.collab_count + fit.meeting_count
    sf_per_ws = (fit.placeable_area_sf or plan.usable_area_sf) / n_ws

    # 1. Light — share of workstations within daylight reach of an exterior wall (REAL geometry).
    daylit = sum(1 for i in ws if boundary.exterior.distance(
        Point(i.x + i.w / 2, i.y + i.h / 2)) <= DAYLIGHT_REACH_FT) / n_ws
    s_light = max(25, int(daylit * 100))

    # 2. Acoustics — lower open-plan density + more enclosed rooms = quieter (REAL).
    s_acoustics = int(0.7 * _clamp(sf_per_ws, 35, 95) + 0.3 * _clamp(enclosed / n_ws, 0.02, 0.25))

    # 3. Movement — circulation generosity drives walking/standing (REAL, from program).
    s_movement = _clamp(circulation_factor, 0.25, 0.45)

    # 4. Social connection — collaboration + meeting provision vs. workstation count (REAL).
    s_social = _clamp(social_zones / n_ws, 0.02, 0.20)

    # 5. Air quality — area-per-person proxies fresh-air dilution (PROXY; real VOC/CO2 need sensors).
    s_air = _clamp(density_rsf_per_person, 120, 220)

    # 6. Ergonomics — the spec is sit-stand desks + ergonomic task chairs (PROXY from BOM intent).
    s_ergonomics = 82

    # 7. Biophilia — proxy from daylight access + collaboration/green-zone provision (PROXY).
    s_biophilia = int(0.5 * s_light + 0.5 * _clamp(fit.collab_count / n_ws, 0.0, 0.08))

    # 8. Restoration — dedicated quiet/restoration provision; proxied from collab/amenity (PROXY).
    s_restoration = _clamp(fit.collab_count, 0, max(2, n_ws // 25))

    dims = [
        DimensionScore("light", "Natural Light", s_light,
                       f"{int(daylit*100)}% of workstations within {int(DAYLIGHT_REACH_FT)} ft of glazing", True),
        DimensionScore("acoustics", "Acoustics", s_acoustics,
                       f"{sf_per_ws:.0f} sf/workstation, {enclosed} enclosed rooms", True),
        DimensionScore("air", "Air Quality", s_air,
                       f"{density_rsf_per_person:.0f} rsf/person (proxy — VOC/CO2 need sensors)", False),
        DimensionScore("ergonomics", "Ergonomics", s_ergonomics,
                       "sit-stand desks + ergonomic task seating specified (proxy from BOM)", False),
        DimensionScore("movement", "Movement", s_movement,
                       f"{int(circulation_factor*100)}% circulation factor", True),
        DimensionScore("social", "Social Connection", s_social,
                       f"{social_zones} collaboration/meeting zones for {n_ws} workstations", True),
        DimensionScore("biophilia", "Biophilia", s_biophilia,
                       "daylight access + collaboration zones (proxy — planting not modeled)", False),
        DimensionScore("restoration", "Restoration", s_restoration,
                       f"{fit.collab_count} restorative/quiet zones (proxy)", False),
    ]

    overall = round(sum(d.score * WEIGHTS[d.key] for d in dims))
    notes = [
        "Wellbeing Score is computed from the test-fit. Light, acoustics, movement and social "
        "connection are derived from geometry; air, ergonomics, biophilia and restoration use "
        "documented proxies (flagged) until material certifications and IoT sensor data are wired in.",
    ]
    return WellbeingScore(overall=overall, dimensions=dims, notes=notes)
