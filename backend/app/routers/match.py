"""Catalog match — text or image query -> ranked real products with an honest confidence band.

Below the 'close' band we return label='no_match' rather than the nearest row (NEVER-fake).
Thresholds in config are calibrated per modality on real seed data (scripts/harvest_seed.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..embeddings.catalog_index import get_embedder, get_index
from ..config import settings
from ..matching import bands_for, decode_image, format_hits

router = APIRouter(prefix="/api/match", tags=["match"])


class MatchRequest(BaseModel):
    text: str | None = None
    image: str | None = None  # data URL or base64
    k: int = 6
    category: str | None = None


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
    vector = embedder.embed_image(decode_image(req.image)) if by_image else embedder.embed_text(req.text)
    hits = get_index().query(vector, k=req.k, category=req.category)
    return {"results": format_hits(db, hits, bands_for(by_image))}
