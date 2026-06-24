"""Live enrichment, index-driven: enrich exactly the products that are in the vector index
(i.e. everything that can be matched), so every match result can carry material detail. Run
from backend/:  ./.venv/bin/python -m scripts.enrich_seed

Paid vision-LLM calls — already-enriched products are skipped via the content-hash cache
BEFORE any image fetch, so re-runs are cheap. Defaults to Gemini-only because the Claude key
is currently invalid; pass gemini_only=False once a valid ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

from app.database import SessionLocal
from app.embeddings.catalog_index import _fetch_image, get_embedder, get_index
from app.enrichment.providers import GeminiEnricher, build_enrichers
from app.enrichment.service import enrich_product, is_enriched
from app.models import Product


def main(gemini_only: bool = True) -> None:
    db = SessionLocal()
    embedder, index = get_embedder(), get_index()
    enrichers = {"gemini": GeminiEnricher()} if gemini_only else build_enrichers()
    available = [n for n, e in enrichers.items() if e.available()]
    ids = [r[0] for r in index._db.execute("SELECT product_id FROM product_vectors").fetchall()]
    print(f"[enrich] providers: {available or 'NONE'} | indexed products: {len(ids)}")

    enriched = cached = skipped = 0
    for pid in ids:
        p = db.get(Product, pid)
        if p is None or not p.image_url:
            skipped += 1
            continue
        if is_enriched(p):  # cache hit — skip before any network/model work
            cached += 1
            continue
        image = _fetch_image(p.image_url)
        if image is None:
            skipped += 1
            continue
        out = enrich_product(db, p, enrichers=enrichers, embedder=embedder, index=index, image=image)
        if out:
            enriched += 1
            if enriched % 20 == 0:
                print(f"[enrich] {enriched} new…")
    print(f"[enrich] done: {enriched} newly enriched, {cached} cached, {skipped} skipped")
    db.close()


if __name__ == "__main__":
    main()
