"""Live enrichment: for each seed brand, enrich up to N catalog products — fetch the image,
route via the novelty gate, extract material attributes, persist. Run from backend/:
  ./.venv/bin/python -m scripts.enrich_seed [per_brand]

Paid vision-LLM calls — content-hash cached, so re-runs skip unchanged products. Per-brand so
Floor/Wall/Furniture all gain material detail. Defaults to Gemini-only because the Claude key
is currently invalid; pass gemini_only=False once a valid ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.embeddings.catalog_index import _fetch_image, get_embedder, get_index
from app.enrichment.providers import GeminiEnricher, build_enrichers
from app.enrichment.service import enrich_product
from app.models import Product

SEED_CODES = ["NK", "TB", "UG", "IK", "OBT", "GW", "OOR"]


def main(per_brand: int = 15, gemini_only: bool = True) -> None:
    db = SessionLocal()
    embedder, index = get_embedder(), get_index()
    enrichers = {"gemini": GeminiEnricher()} if gemini_only else build_enrichers()
    available = [n for n, e in enrichers.items() if e.available()]
    print(f"[enrich] providers: {available or 'NONE'} | per_brand={per_brand}")
    total = 0
    for code in SEED_CODES:
        products = (db.query(Product)
                    .filter(Product.source == "harvest", Product.manufacturer_code == code,
                            Product.image_url.isnot(None))
                    .limit(per_brand).all())
        done = 0
        for p in products:
            image = _fetch_image(p.image_url)
            if image is None:
                continue
            out = enrich_product(db, p, enrichers=enrichers, embedder=embedder, index=index, image=image)
            if out:
                done += 1
                total += 1
        print(f"[enrich] {code}: enriched {done}/{len(products)}")
    print(f"[enrich] total enriched: {total}")
    db.close()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
