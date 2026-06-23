"""Procurement data model — vendors the dealer can RFQ against.

NEW tables only — this module does NOT modify app/models.py. It reuses the shared
`Base` so `Base.metadata.create_all(bind=engine)` (already called in main.bootstrap)
picks these tables up automatically.

IMPORTANT — SYNTHETIC DATA: the seeded vendors below are FABRICATED placeholders. Real
dealer-vendor relationships (who carries which manufacturer line, negotiated multipliers,
true lead times) are private, deal-specific, and unpublished — that's the core
procurement-data problem. These let the RFQ/PO loop run end-to-end with plausible numbers;
none of them are real companies or real terms.
"""

from __future__ import annotations

from sqlalchemy import Float, Integer, String
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Vendor(Base):
    """A US distributor/dealer-partner that can supply some manufacturer lines.

    price_multiplier multiplies the dealer's net (post list-minus) price, so it expresses how
    this vendor's pricing compares to the dealer's standard discount baseline:
      < 1.0  => better than baseline (deeper effective discount)
      = 1.0  => at baseline
      > 1.0  => worse than baseline (shallower discount / premium)
    carried_manufacturers is a JSON list of manufacturer codes (e.g. ["HMI", "SC"]) matching
    app.models.Manufacturer.code / Product.manufacturer_code.
    """

    __tablename__ = "procurement_vendors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(2))  # US two-letter
    lead_time_days: Mapped[int] = mapped_column(Integer, default=30)
    price_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    carried_manufacturers: Mapped[list[str]] = mapped_column(JSON, default=list)
    synthetic: Mapped[bool] = mapped_column(Integer, default=1)  # flag: NOT a real vendor


# --- SYNTHETIC US vendor fixtures -------------------------------------------------------
# 5 fabricated distributors across US metros. lead_time_days in [10, 60], price_multiplier
# in [0.95, 1.05]. Each carries a different subset of the manufacturer codes seeded in
# app/seed.py (HMI, SC, HAW, KNL, HUM, INT, FRM) so RFQ coverage/ranking varies meaningfully.
SYNTHETIC_VENDORS: list[dict] = [
    {
        "name": "Atlas Contract Furnishings (synthetic)",
        "city": "Chicago", "state": "IL",
        "lead_time_days": 21, "price_multiplier": 0.97,
        "carried_manufacturers": ["HMI", "SC", "KNL", "HUM"],
    },
    {
        "name": "Pacific Workspace Supply (synthetic)",
        "city": "San Jose", "state": "CA",
        "lead_time_days": 35, "price_multiplier": 0.95,
        "carried_manufacturers": ["HMI", "HAW", "INT", "FRM"],
    },
    {
        "name": "Keystone Office Distributors (synthetic)",
        "city": "Philadelphia", "state": "PA",
        "lead_time_days": 14, "price_multiplier": 1.02,
        "carried_manufacturers": ["SC", "KNL", "HAW", "HUM", "INT"],
    },
    {
        "name": "Lone Star Commercial Interiors (synthetic)",
        "city": "Dallas", "state": "TX",
        "lead_time_days": 45, "price_multiplier": 0.98,
        "carried_manufacturers": ["HMI", "SC", "HAW", "KNL", "HUM", "INT", "FRM"],
    },
    {
        "name": "Empire State Furniture Group (synthetic)",
        "city": "Albany", "state": "NY",
        "lead_time_days": 60, "price_multiplier": 1.05,
        "carried_manufacturers": ["HMI", "KNL", "FRM"],
    },
]


def seed_vendors(db) -> int:
    """Idempotently insert the synthetic vendors. Returns the count created.

    Safe to call repeatedly (e.g. from a bootstrap) — matches on vendor name.
    """
    created = 0
    existing = {name for (name,) in db.query(Vendor.name).all()}
    for v in SYNTHETIC_VENDORS:
        if v["name"] in existing:
            continue
        db.add(Vendor(
            name=v["name"], city=v["city"], state=v["state"],
            lead_time_days=v["lead_time_days"], price_multiplier=v["price_multiplier"],
            carried_manufacturers=v["carried_manufacturers"], synthetic=1,
        ))
        created += 1
    db.commit()
    return created
