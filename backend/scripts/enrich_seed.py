"""Live enrichment: for the first N indexed catalog products, fetch the image, route via the
novelty gate (Gemini for near-duplicates, Claude for novel), extract material attributes, and
persist them. Run from backend/:  ./.venv/bin/python -m scripts.enrich_seed [N]

Paid vision-LLM calls — content-hash cached, so re-runs skip unchanged products. Demand-first:
early items are mostly novel (-> Claude); the cheap-Gemini hit-rate climbs as coverage grows.
"""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.embeddings.catalog_index import _fetch_image, get_embedder, get_index
from app.enrichment.providers import build_enrichers
from app.enrichment.service import enrich_product
from app.models import Product


def main(n: int = 5) -> None:
    db = SessionLocal()
    embedder, index, enrichers = get_embedder(), get_index(), build_enrichers()
    available = [name for name, e in enrichers.items() if e.available()]
    print(f"[enrich] providers available: {available or 'NONE — set keys in .env'}")
    products = (db.query(Product)
                .filter(Product.source == "harvest", Product.image_url.isnot(None))
                .limit(n).all())
    for p in products:
        image = _fetch_image(p.image_url)
        if image is None:
            print(f"[enrich] {p.sku}: image fetch failed, skipped")
            continue
        out = enrich_product(db, p, enrichers=enrichers, embedder=embedder, index=index, image=image)
        if out is None:
            print(f"[enrich] {p.sku}: no provider available")
            continue
        pm = out["enrichment"].get("primary_material", {})
        fin = out["enrichment"].get("finish", {})
        print(f"[enrich] {p.sku} via {out['provider']:6} | {p.name[:38]:38} "
              f"-> material={pm.get('value')} ({pm.get('source')}) finish={fin.get('value')}")
    db.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
