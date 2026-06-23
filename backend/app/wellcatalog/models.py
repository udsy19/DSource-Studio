"""WELL / sustainability certification attributes, keyed by catalog SKU.

A NEW table, additive to the read-only Product spine (app/models.py is NOT modified).
We key on `sku` (the SIF part number) and join to Product.sku in queries rather than a
hard FK, so a cert can be authored ahead of / independently of catalog ingestion and a
Product with no cert simply degrades gracefully (ranked lower).

Real-world, these values come from WELL/LEED material reports, manufacturer EPDs
(embodied carbon) and the dealer's lead-time feeds. Here they are ILLUSTRATIVE
synthetic placeholders (see seed.py) — sourcing real data is the catalog-data problem.
"""

from sqlalchemy import Boolean, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# Allowed WELL rating buckets, best -> worst. "none" = no rating on file.
WELL_RATINGS = ("A+", "A", "B", "none")


class ProductCert(Base):
    """Sustainability + WELL compliance facts for a single catalog SKU."""

    __tablename__ = "product_certs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(120), index=True, unique=True)  # joins Product.sku

    well_rating: Mapped[str] = mapped_column(String(8), default="none")  # "A+"|"A"|"B"|"none"
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)       # shorter is better
    low_voc: Mapped[bool] = mapped_column(Boolean, default=False)         # WELL X06 air quality
    recycled_pct: Mapped[float] = mapped_column(Float, default=0.0)       # 0–100 % recycled content
    embodied_carbon_kg: Mapped[float] = mapped_column(Float, default=0.0) # kgCO2e per unit (EPD)
