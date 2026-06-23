"""Phase 0 data model — the dealer-facing data spine.

Single-tenant for the pilot (the dealer IS the user — no cross-dealer routing). Products
are canonical on (manufacturer_code, sku=part number); SIF/pCon imports upsert onto them.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # SIF MC, <=5 chars typically
    name: Mapped[str] = mapped_column(String(120))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("manufacturer_code", "sku", name="uq_mfr_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    manufacturer_code: Mapped[str] = mapped_column(String(8), index=True)
    sku: Mapped[str] = mapped_column(String(120), index=True)  # SIF PN
    name: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(60), default="other", index=True)
    list_price: Mapped[float] = mapped_column(Float, default=0.0)
    price_uom: Mapped[str] = mapped_column(String(20), default="each")
    source: Mapped[str] = mapped_column(String(20), default="seed")  # seed | sif | pcon
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class Discount(Base):
    """Dealer's standard list-minus discount band per manufacturer line."""

    __tablename__ = "discounts"
    manufacturer_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    band: Mapped[float] = mapped_column(Float, default=0.40)  # 0.50 => 50% off list


class DealerSettings(Base):
    """Singleton (id=1) — the dealer's pricing knobs for budgetary quotes."""

    __tablename__ = "dealer_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    name: Mapped[str] = mapped_column(String(200), default="Pilot Dealer")
    default_discount: Mapped[float] = mapped_column(Float, default=0.40)
    install_rate: Mapped[float] = mapped_column(Float, default=0.15)   # % of net merchandise
    freight_rate: Mapped[float] = mapped_column(Float, default=0.03)   # % of net merchandise
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0863)     # on merchandise + freight


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    lines: Mapped[list["ProjectLine"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectLine(Base):
    __tablename__ = "project_lines"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[float] = mapped_column(Float, default=1.0)
    # Optional per-line overrides captured from the source export (e.g. SIF PL / S%).
    list_price_override: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_override: Mapped[float | None] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
