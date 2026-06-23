"""Persist harvested NormalizedProduct rows into the catalog (Product), canonical on
(manufacturer_code, sku). Idempotent — re-harvesting updates rather than duplicates.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..ingest.service import resolve_manufacturer
from ..models import Product
from .schema import NormalizedProduct


@dataclass
class HarvestStoreResult:
    created: int
    updated: int
    no_price: int      # rows with no real INR price (B2B/quote-only) — flagged, never faked
    duplicates: int    # same (mfr, sku) seen twice in one batch (e.g. size variants) — first wins


def _provenance(mp: NormalizedProduct) -> dict:
    return {
        "source_tier": mp.source_tier,
        "harvested_at": mp.harvested_at.isoformat(),
        "flagged_fields": mp.flagged_fields,
        "image_urls": mp.image_urls,
        "material_attrs": mp.material_attrs,
        "typology_tags": mp.typology_tags,
        "vendor": mp.vendor,
        "url": mp.url,
        "color": mp.color,
        "finish": mp.finish,
    }


def upsert_harvest(
    db: Session, products: list[NormalizedProduct], source: str = "harvest"
) -> HarvestStoreResult:
    created = updated = no_price = duplicates = 0
    seen: set[tuple[str, str]] = set()
    for mp in products:
        code = resolve_manufacturer(db, mp.manufacturer_code, mp.vendor)
        key = (code, mp.sku)
        if key in seen:
            duplicates += 1  # same sku twice in this batch (size variants) — keep the first
            continue
        seen.add(key)
        if mp.price_inr is None:
            no_price += 1
        row = (
            db.query(Product)
            .filter(Product.manufacturer_code == code, Product.sku == mp.sku)
            .first()
        )
        primary_image = mp.image_urls[0] if mp.image_urls else None
        if row is None:
            db.add(Product(
                manufacturer_code=code, sku=mp.sku, name=mp.title, category=mp.category,
                source=source, image_url=primary_image, price_inr=mp.price_inr,
                gst_rate=mp.gst_rate, provenance=_provenance(mp),
            ))
            created += 1
        else:
            row.name, row.category, row.source = mp.title, mp.category, source
            row.image_url, row.price_inr = primary_image, mp.price_inr
            row.gst_rate, row.provenance = mp.gst_rate, _provenance(mp)
            updated += 1
    db.commit()
    return HarvestStoreResult(created=created, updated=updated, no_price=no_price, duplicates=duplicates)
