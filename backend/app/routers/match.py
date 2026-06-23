"""Catalog match — text or image query -> ranked real products with an honest confidence band.

Below the 'close' band we return label='no_match' rather than the nearest row (NEVER-fake).
Thresholds in config are PROVISIONAL until calibrated on real data (scripts/harvest_seed.py).
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..embeddings.catalog_index import get_embedder, get_index
from ..models import Product

router = APIRouter(prefix="/api/match", tags=["match"])


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


class MatchRequest(BaseModel):
    text: str | None = None
    image: str | None = None  # data URL or base64
    k: int = 6
    category: str | None = None


def _bands(by_image: bool) -> MatchBands:
    if by_image:
        return MatchBands(settings.match_image_exact, settings.match_image_close)
    return MatchBands(settings.match_text_exact, settings.match_text_close)


@router.get("/status")
def status() -> dict:
    return {
        "indexed": get_index().count(),
        "model": settings.embed_model,
        "text_bands": {"exact": settings.match_text_exact, "close": settings.match_text_close},
        "image_bands": {"exact": settings.match_image_exact, "close": settings.match_image_close},
    }


@router.post("")
def match(req: MatchRequest, db: Session = Depends(get_db)) -> dict:
    if not req.text and not req.image:
        raise HTTPException(status_code=422, detail="Provide `text` or `image`.")
    embedder = get_embedder()
    by_image = bool(req.image)
    vector = embedder.embed_image(_decode_image(req.image)) if by_image else embedder.embed_text(req.text)
    hits = get_index().query(vector, k=req.k, category=req.category)
    return {"results": _results(db, hits, _bands(by_image))}


def _results(db: Session, hits: list[tuple[int, float]], bands: MatchBands) -> list[dict]:
    out = []
    for product_id, score in hits:
        p = db.get(Product, product_id)
        if p is None:
            continue
        prov = p.provenance or {}
        out.append({
            "product_id": p.id, "sku": p.sku, "name": p.name, "category": p.category,
            "vendor": prov.get("vendor") or p.manufacturer_code,
            "price_inr": p.price_inr, "gst_rate": p.gst_rate,
            "image_url": p.image_url, "url": prov.get("url"),
            "score": round(score, 4), "label": band(score, bands),
            "flagged_fields": prov.get("flagged_fields", []),
        })
    return out


def _decode_image(data: str):
    from PIL import Image

    raw = data.split(",", 1)[1] if data.startswith("data:") else data
    return Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
