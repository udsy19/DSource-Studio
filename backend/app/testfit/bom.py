"""Per-instance -> catalog-SKU mapping for a test-fit.

Each placed instance type consumes a fixed set of catalog SKUs; meeting rooms additionally
size their chair count from room area (~1 seat / 15 sf, capped). All SKUs are looked up by
`sku` downstream; any missing SKU is skipped gracefully (no 500).

Where a REAL Herman Miller price-book SKU was ingested (base code from the parsed PDF,
source="pricebook") we use it so the line prices off the real HM list price. Otherwise we
keep a synthetic-catalog fallback (source="sif"). Downstream BOM lines carry provenance so
the UI can show which prices are real.
  Real HM base codes ingested & used: AER1 (Aeron task chair, full base $1726) and PX100
  (Plex lounge club chair, $866). The sit-to-stand desk and conference-table price books did
  not parse under the chair-style "Step N." grammar, so desk/table lines stay synthetic.
"""

from __future__ import annotations

from .layout import FurnitureInstance, TestFit

WORKSTATION_SKUS = [
    ("SC-OLOGY-RECT", 1),  # synthetic fallback: desk (HM desk books don't parse)
    ("AER1", 1),           # REAL Herman Miller Aeron task chair (price book)
]
PRIVATE_OFFICE_SKUS = [
    ("HM-RENEW-SS", 1),    # synthetic fallback: sit-to-stand desk
    ("AER1", 1),           # REAL Herman Miller Aeron task chair (price book)
]
MEETING_TABLE_SKU = "HM-EVERYWHERE-6"  # synthetic fallback: conference table (book won't parse)
# REAL Herman Miller Aeron task chair (price book, full base price $1726). We deliberately do
# NOT use the parsed Setu CQN51 here: its starting config came out at $45 because the Setu book's
# base-price step had no captured priced option, so $45 is an incomplete (option-only) figure.
# Aeron parses with its full base, so it's the defensible real meeting-chair price.
MEETING_CHAIR_SKU = "AER1"
COLLAB_SKUS = [
    ("PX100", 1),          # REAL Herman Miller Plex lounge club chair (price book)
    ("KN-RILEY-OTTOMAN", 2),  # synthetic fallback: ottoman (no HM lounge ottoman parsed)
]

_MEETING_SEAT_SF = 15.0
_MEETING_SEAT_CAP = 12


def instance_skus(inst: FurnitureInstance) -> list[tuple[str, int]]:
    """The catalog SKUs (with quantities) a single placed instance consumes."""
    if inst.type == "workstation":
        return list(WORKSTATION_SKUS)
    if inst.type == "private_office":
        return list(PRIVATE_OFFICE_SKUS)
    if inst.type == "meeting_room":
        seats = min(_MEETING_SEAT_CAP, max(2, int((inst.w * inst.h) / _MEETING_SEAT_SF)))
        return [(MEETING_TABLE_SKU, 1), (MEETING_CHAIR_SKU, seats)]
    if inst.type == "collaboration":
        return list(COLLAB_SKUS)
    return []


def sku_demand(fit: TestFit) -> dict[str, int]:
    """Aggregate raw {sku: qty} demand across all placed instances."""
    demand: dict[str, int] = {}
    for inst in fit.instances:
        for sku, qty in instance_skus(inst):
            if qty <= 0:
                continue
            demand[sku] = demand.get(sku, 0) + qty
    return demand
