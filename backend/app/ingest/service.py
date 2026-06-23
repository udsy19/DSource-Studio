"""Ingest service: normalize parsed SIF/pCon -> upsert catalog, build projects, resolve pricing.

Format-agnostic: both the SIF parser and the pCon adapter emit SifFile/SifLineItem, so this
layer never cares which tool the dealer exported from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..models import DealerSettings, Discount, Manufacturer, Product, Project, ProjectLine
from ..pricing.engine import DealerRates, QuoteLineInput
from .sif import SifFile, SifLineItem

_CATEGORY_KEYWORDS: list[tuple[str, str]] = [
    ("seating", r"chair|stool|seat|sofa|lounge"),
    ("desking", r"desk|workstation|benching|sit-?stand|height.?adjust"),
    ("tables", r"table|conference|huddle|cafe"),
    ("storage", r"storage|cabinet|pedestal|locker|credenza|shelv|tower"),
    ("pods", r"pod|booth|phone room|focus room|framery"),
    ("flooring", r"carpet|tile|floor|rug"),
]


def infer_category(name: str) -> str:
    text = (name or "").lower()
    for cat, pattern in _CATEGORY_KEYWORDS:
        if re.search(pattern, text):
            return cat
    return "other"


def resolve_manufacturer(db: Session, code: str, name_hint: str = "") -> str:
    """Ensure a Manufacturer row exists; return its code. Names are best-effort."""
    code = (code or "UNK").strip()[:8] or "UNK"
    m = db.get(Manufacturer, code)
    if m is None:
        db.add(Manufacturer(code=code, name=(name_hint or code).strip()[:120]))
    return code


@dataclass
class IngestResult:
    title: str
    items_read: int
    created: int
    updated: int
    matched: int
    warnings: list[str]


def upsert_catalog(db: Session, sif: SifFile, source: str) -> IngestResult:
    created = updated = matched = 0
    for it in sif.items:
        code = resolve_manufacturer(db, it.manufacturer_code, it.manufacturer_code)
        product = (
            db.query(Product)
            .filter(Product.manufacturer_code == code, Product.sku == it.part_number)
            .first()
        )
        if product is None:
            db.add(Product(
                manufacturer_code=code, sku=it.part_number, name=it.description,
                category=infer_category(it.description), list_price=it.list_price,
                source=source,
            ))
            created += 1
        else:
            changed = False
            if it.list_price and it.list_price != product.list_price:
                product.list_price = it.list_price
                changed = True
            if it.description and it.description != product.name:
                product.name = it.description
                changed = True
            updated += changed
            matched += not changed
    db.commit()
    return IngestResult(
        title=sif.title, items_read=len(sif.items),
        created=created, updated=updated, matched=matched, warnings=sif.warnings,
    )


@dataclass
class PriceBookProductResult:
    base_code: str
    name: str
    configured_part_number: str
    starting_list_price: float
    step_count: int
    option_count: int
    product_id: int
    status: str  # created | updated | matched


def upsert_price_book(db: Session, book, manufacturer_code: str,
                      source: str = "pricebook") -> tuple[list[PriceBookProductResult], list[str]]:
    """Load a parsed manufacturer price book into the catalog.

    Each base model becomes one catalog product priced at its 'starting configuration'
    (cheapest option per step) — a real part number + real list price.
    """
    code = resolve_manufacturer(db, manufacturer_code, manufacturer_code)
    results: list[PriceBookProductResult] = []
    for prod in book.products:
        part_number, starting_price = prod.starting_config()
        option_count = sum(len(s.options) for s in prod.steps)
        product = (
            db.query(Product)
            .filter(Product.manufacturer_code == code, Product.sku == prod.base_code)
            .first()
        )
        if product is None:
            product = Product(
                manufacturer_code=code, sku=prod.base_code, name=prod.name,
                category=infer_category(prod.name), list_price=starting_price,
                source=source,
            )
            db.add(product)
            db.flush()
            status = "created"
        else:
            changed = starting_price and starting_price != product.list_price
            if changed:
                product.list_price = starting_price
            status = "updated" if changed else "matched"
        results.append(PriceBookProductResult(
            base_code=prod.base_code, name=prod.name,
            configured_part_number=part_number, starting_list_price=starting_price,
            step_count=len(prod.steps), option_count=option_count,
            product_id=product.id, status=status,
        ))
    db.commit()
    return results, book.warnings


def build_project(db: Session, sif: SifFile, name: str, source: str = "sif") -> Project:
    """Create a Project from a BOM export, auto-creating any missing catalog products."""
    project = Project(name=name, source=source)
    db.add(project)
    db.flush()

    for it in sif.items:
        code = resolve_manufacturer(db, it.manufacturer_code, it.manufacturer_code)
        product = (
            db.query(Product)
            .filter(Product.manufacturer_code == code, Product.sku == it.part_number)
            .first()
        )
        if product is None:
            product = Product(
                manufacturer_code=code, sku=it.part_number, name=it.description,
                category=infer_category(it.description), list_price=it.list_price,
                source=source,
            )
            db.add(product)
            db.flush()
        elif it.list_price and not product.list_price:
            product.list_price = it.list_price

        db.add(ProjectLine(
            project_id=project.id, product_id=product.id, qty=it.quantity,
            list_price_override=it.list_price or None,
            discount_override=(it.discount_pct / 100.0) if it.discount_pct else None,
        ))
    db.commit()
    db.refresh(project)
    return project


def resolve_discount(db: Session, manufacturer_code: str, settings: DealerSettings,
                     line_override: float | None) -> float:
    if line_override is not None:
        return line_override
    d = db.get(Discount, manufacturer_code)
    if d is not None:
        return d.band
    return settings.default_discount


def get_settings(db: Session) -> DealerSettings:
    s = db.get(DealerSettings, 1)
    if s is None:
        s = DealerSettings(id=1)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def quote_inputs_for_project(db: Session, project: Project) -> tuple[list[QuoteLineInput], DealerRates]:
    settings = get_settings(db)
    rates = DealerRates(settings.install_rate, settings.freight_rate, settings.tax_rate)
    inputs: list[QuoteLineInput] = []
    for line in project.lines:
        product = db.get(Product, line.product_id)
        if product is None:
            continue
        unit_list = line.list_price_override or product.list_price
        band = resolve_discount(db, product.manufacturer_code, settings, line.discount_override)
        inputs.append(QuoteLineInput(
            product_id=product.id, manufacturer_code=product.manufacturer_code,
            sku=product.sku, name=product.name, qty=line.qty,
            unit_list=unit_list, discount_band=band,
        ))
    return inputs, rates
