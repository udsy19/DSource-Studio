"""Program → capacity estimate from usable area (deterministic, from research norms).

Density and circulation numbers come from the Phase-0 research:
  * office density ~150-250 rentable sf/person (we default 175)
  * circulation factor ~25-45% of usable area (we default 0.35 for open plan)
  * modern hybrid program skews ~40% workstations / 60% shared+collaboration

This is the "capacity envelope" the Gate B check validates and the test-fit (Phase 2) will
later fill with real furniture. Everything here is transparent arithmetic, not AI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# default zone mix (fractions of net usable area)
DEFAULT_ZONE_MIX = {
    "workstations": 0.40,
    "private_offices": 0.10,
    "meeting": 0.20,
    "collaboration": 0.15,
    "amenity": 0.15,
}
# typical area per seat (sf) including immediate circulation, by zone
AREA_PER_SEAT = {
    "workstations": 48.0,
    "private_offices": 120.0,
    "meeting": 20.0,
    "collaboration": 25.0,
}


@dataclass
class Program:
    density_rsf_per_person: float = 175.0
    circulation_factor: float = 0.35
    zone_mix: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_ZONE_MIX))


@dataclass
class ZoneEstimate:
    zone: str
    area_sf: float
    seats: int | None


@dataclass
class CapacityEstimate:
    usable_area_sf: float
    net_usable_sf: float
    density_rsf_per_person: float
    circulation_factor: float
    estimated_headcount: int
    zones: list[ZoneEstimate]


def estimate_capacity(usable_area_sf: float, program: Program | None = None) -> CapacityEstimate:
    program = program or Program()
    headcount = int(usable_area_sf / program.density_rsf_per_person) if program.density_rsf_per_person else 0
    net_usable = usable_area_sf * (1 - program.circulation_factor)

    zones: list[ZoneEstimate] = []
    for zone, ratio in program.zone_mix.items():
        area = round(net_usable * ratio, 1)
        per_seat = AREA_PER_SEAT.get(zone)
        seats = int(area / per_seat) if per_seat else None
        zones.append(ZoneEstimate(zone=zone, area_sf=area, seats=seats))

    return CapacityEstimate(
        usable_area_sf=round(usable_area_sf, 1),
        net_usable_sf=round(net_usable, 1),
        density_rsf_per_person=program.density_rsf_per_person,
        circulation_factor=program.circulation_factor,
        estimated_headcount=headcount,
        zones=zones,
    )
