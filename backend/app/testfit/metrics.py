"""Space metrics for a generated test-fit — the numbers behind a Qbiq Space Planning Report.

Every value here is DERIVED from the placed geometry (or from the plan the layout was built
on); nothing is invented. Where a value is a ratio of two measured quantities the formula is
stated in `compute_metrics`'s docstring so a human can audit why a number landed where it did.

Daylight reuses the wellbeing engine's perimeter-reach constant (DAYLIGHT_REACH_FT) so the two
layers agree on what "daylit" means instead of each picking its own threshold.
"""

from __future__ import annotations

from shapely.geometry import Point, Polygon, box

from ..floorplan.dxf_ingest import PlanModel
from ..wellbeing.score import DAYLIGHT_REACH_FT
from .layout import TestFit

# A "seat" is a person-position: an open-plan workstation or a single-occupant private office.
# Meeting rooms hold seats too, but the report's `seats` figure counts only assignable desks
# (workstations + offices), matching the contract, so meeting seats are excluded from the count.
_SEAT_TYPES = ("workstation", "private_office")
# Enclosed footprints a seat can sit inside to count as "private".
_ENCLOSED_TYPES = ("private_office", "meeting_room")


def compute_metrics(plan: PlanModel, fit: TestFit) -> dict:
    """Derive the Space-Planning-Report metrics from one test-fit.

    Formulas (all measured, none fabricated):
      * usf                    = plan.usable_area_sf (gross minus service core).
      * seats                  = workstation_count + office_count (assignable desks).
      * open_space_seats       = workstation_count.
      * offices                = office_count.
      * conf_rooms             = meeting_count.
      * density_sf_per_person  = usf / seats   (0 when seats == 0).
      * daylight_pct           = (# seat-centroids within DAYLIGHT_REACH_FT of the boundary
                                  polygon's edge) / seats. Reuses the wellbeing daylight band
                                  (25 ft) so "daylit" means the same thing everywhere.
      * privacy_pct            = (# seat-centroids that fall inside an enclosed room footprint
                                  — private_office or meeting_room) / seats. Open-field
                                  workstations are never inside a room, so this resolves to the
                                  enclosed share of seats (offices), measured geometrically.
      * efficiency_pct         = placeable_area_sf / usable_area_sf — the fraction of usable
                                  area that survives perimeter setback + core + column clearance
                                  and can actually carry furniture (0 when usable == 0).
    """
    boundary = Polygon(plan.boundary)
    seat_instances = [i for i in fit.instances if i.type in _SEAT_TYPES]
    enclosed_polys = [
        box(i.x, i.y, i.x + i.w, i.y + i.h)
        for i in fit.instances
        if i.type in _ENCLOSED_TYPES
    ]

    seats = fit.workstation_count + fit.office_count

    daylit = 0
    private = 0
    for i in seat_instances:
        centroid = Point(i.x + i.w / 2, i.y + i.h / 2)
        if boundary.exterior.distance(centroid) <= DAYLIGHT_REACH_FT:
            daylit += 1
        if any(poly.contains(centroid) for poly in enclosed_polys):
            private += 1

    usf = plan.usable_area_sf
    return {
        "usf": round(usf, 1),
        "seats": seats,
        "open_space_seats": fit.workstation_count,
        "offices": fit.office_count,
        "conf_rooms": fit.meeting_count,
        "density_sf_per_person": round(usf / seats, 1) if seats else 0.0,
        "daylight_pct": round(daylit / seats, 3) if seats else 0.0,
        "privacy_pct": round(private / seats, 3) if seats else 0.0,
        "efficiency_pct": round(fit.placeable_area_sf / usf, 3) if usf else 0.0,
    }
