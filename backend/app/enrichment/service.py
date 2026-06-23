"""Novelty-gated enrichment orchestration.

A product near-duplicate of an already-enriched one (image cosine >= threshold, same category)
routes to the cheap model; novel/first-seen items escalate. Results are cached by content hash
so re-runs never re-bill an unchanged product, and persisted into Product.provenance.
"""

from __future__ import annotations

import hashlib
import logging

from PIL import Image
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Product
from .providers import VisionEnricher

logger = logging.getLogger(__name__)


def content_hash(product: Product) -> str:
    prov = product.provenance or {}
    basis = f"{product.image_url}|{product.name}|{prov.get('description', '')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def is_enriched(product: Product) -> bool:
    prov = product.provenance or {}
    return bool(prov.get("enrichment")) and prov.get("enrichment_hash") == content_hash(product)


def decide_provider(db: Session, product: Product, query_vec: list[float], index, threshold: float) -> str:
    """Cheap 'gemini' if a same-category, already-enriched neighbor is within the novelty
    threshold; otherwise 'claude' for a genuinely novel item."""
    for pid, score in index.query(query_vec, k=10, category=product.category):
        if pid == product.id:
            continue
        if score < threshold:
            break  # hits are sorted by similarity desc — nothing closer remains
        neighbor = db.get(Product, pid)
        if neighbor and (neighbor.provenance or {}).get("enrichment"):
            return "gemini"
    return "claude"


def enrich_product(
    db: Session, product: Product, *, enrichers: dict[str, VisionEnricher], embedder, index,
    image: Image.Image, threshold: float | None = None, force: bool = False,
) -> dict | None:
    threshold = settings.enrich_novelty_threshold if threshold is None else threshold
    if not force and is_enriched(product):
        return {"provider": "cache", "enrichment": (product.provenance or {})["enrichment"]}

    provider = decide_provider(db, product, embedder.embed_image(image), index, threshold)
    description = (product.provenance or {}).get("description")
    for name, enricher in _providers_to_try(enrichers, provider):
        try:
            result = enricher.enrich(image, product.name, description)
        except Exception as exc:  # external API boundary: log and fall through to the next provider
            logger.warning("enricher %s failed on %s: %s", name, product.sku, exc)
            continue
        if result is None:
            continue
        prov = dict(product.provenance or {})
        prov["enrichment"] = result.model_dump(mode="json")
        prov["enrichment_provider"] = name
        prov["enrichment_hash"] = content_hash(product)
        product.provenance = prov
        db.commit()
        return {"provider": name, "enrichment": prov["enrichment"]}
    return None


def _providers_to_try(enrichers: dict[str, VisionEnricher], preferred: str) -> list[tuple[str, VisionEnricher]]:
    """Preferred configured provider first, then the other configured ones — so a bad key on the
    chosen provider falls back rather than failing the whole enrichment."""
    order = []
    chosen = enrichers.get(preferred)
    if chosen is not None and chosen.available():
        order.append((preferred, chosen))
    order.extend((name, e) for name, e in enrichers.items() if name != preferred and e.available())
    return order
