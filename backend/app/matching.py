"""Catalog matching core — band logic, image decode/crop, and hit formatting.

Shared by the text/image `/api/match` route and the Explore region back-match. Keeps the
NEVER-fake discipline: a score below the 'close' band is labelled 'no_match', not the nearest row.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from sqlalchemy.orm import Session

from .config import settings
from .materials.derive import derive_material_attributes, material_family_from
from .models import Product


@dataclass(frozen=True)
class MatchBands:
    exact: float
    close: float


def band(score: float, bands: MatchBands) -> str:
    if score >= bands.exact:
        return "exact"
    if score >= bands.close:
        return "close"
    return "no_match"


def bands_for(by_image: bool) -> MatchBands:
    """CLIP's modality gap means text↔image and image↔image cosines live on different scales,
    so the bands are calibrated per modality (see config + memory.md KEY FINDING)."""
    if by_image:
        return MatchBands(settings.match_image_exact, settings.match_image_close)
    return MatchBands(settings.match_text_exact, settings.match_text_close)


def decode_image(data: str):
    from PIL import Image

    raw = data.split(",", 1)[1] if data.startswith("data:") else data
    return Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")


def crop_region(image, box: tuple[int, int, int, int]):
    """Crop a (x, y, w, h) region, clamped to the image — the unit a region back-match scores."""
    width, height = image.size
    x, y, w, h = box
    left = max(0, min(x, width))
    top = max(0, min(y, height))
    right = max(left, min(x + w, width))
    bottom = max(top, min(y + h, height))
    return image.crop((left, top, right, bottom))


def _primary_material(enrichment: dict | None, material_attrs: dict | None) -> str | None:
    if enrichment:
        value = (enrichment.get("primary_material") or {}).get("value")
        if value:
            return value
    if material_attrs:
        return material_attrs.get("primary_material")
    return None


def format_hits(db: Session, hits: list[tuple[int, float]], bands: MatchBands) -> list[dict]:
    out = []
    for product_id, score in hits:
        p = db.get(Product, product_id)
        if p is None:
            continue
        prov = p.provenance or {}
        enrichment = prov.get("enrichment") or None
        material = _primary_material(enrichment, prov.get("material_attrs"))
        family = material_family_from(material)
        out.append({
            "product_id": p.id, "sku": p.sku, "name": p.name, "category": p.category,
            "vendor": prov.get("vendor") or p.manufacturer_code,
            "price_inr": p.price_inr, "gst_rate": p.gst_rate,
            "image_url": p.image_url, "url": prov.get("url"),
            "score": round(score, 4), "label": band(score, bands),
            "flagged_fields": prov.get("flagged_fields", []),
            "material": material,
            "enrichment": enrichment,
            "maintenance": derive_material_attributes(family) if family else None,
        })
    return out
