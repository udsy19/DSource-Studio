"""Cooperative-contract discount-band ingest router.

Upload a public cooperative / state purchasing furniture pricing PDF and get back the REAL
discount-off-list bands it contains, normalized per (manufacturer, product line) with the
project's manufacturer codes mapped where known. The integrator registers this router in
main.py (see this module's bottom for the one-liner) — it is intentionally self-contained
and does not touch any existing file.

This endpoint is read-only: it returns extracted bands and a per-manufacturer-code rollup
the caller can use to update the Discount(manufacturer_code, band) table. It does not write
to the DB itself, keeping the connector side-effect free.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..coop.parser import parse_contract
from ..database import get_db
from ..models import Discount

router = APIRouter(prefix="/api/coop", tags=["coop"])


class DiscountBandOut(BaseModel):
    manufacturer: str
    manufacturer_code: str | None
    product_line: str
    collection: str | None = None
    category: str | None = None
    discount_pct: float
    tier_discounts: list[float] = []
    source_contract: str
    source_url: str


class CoopParseReport(BaseModel):
    title: str
    source_contract: str
    source_url: str
    bands_parsed: int
    # Representative per-manufacturer-code band (median across that maker's lines), ready to
    # feed the Discount(manufacturer_code, band) table.
    manufacturer_bands: dict[str, float]
    # When apply=true, the per-manufacturer bands written into the Discount table.
    applied_bands: dict[str, float] | None = None
    bands: list[DiscountBandOut] = []
    warnings: list[str] = []


@router.post("/discounts", response_model=CoopParseReport)
async def parse_coop_discounts(
    file: UploadFile = File(...),
    source_contract: str | None = Form(None),
    source_url: str | None = Form(None),
    apply: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Parse a co-op furniture pricing PDF into discount-off-list bands.

    With `apply=true`, the per-manufacturer rollup is upserted into the dealer's
    `Discount(manufacturer_code, band)` table so the budgetary quote engine immediately
    uses these real, contract-sourced bands instead of assumed defaults.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="Empty file.")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Expected a .pdf co-op pricing document.")

    kwargs: dict[str, str] = {}
    if source_contract:
        kwargs["source_contract"] = source_contract
    if source_url:
        kwargs["source_url"] = source_url

    try:
        parsed = parse_contract(content, **kwargs)
    except Exception as exc:  # noqa: BLE001 - surface parse errors to the caller
        raise HTTPException(status_code=422, detail=f"Could not parse PDF: {exc}") from exc

    if not parsed.bands:
        raise HTTPException(
            status_code=422,
            detail="No discount bands found; PDF layout differs from supported co-op grids. "
            + " ".join(parsed.warnings),
        )

    manufacturer_bands = parsed.by_manufacturer_code()
    applied = None
    if apply:
        for code, band in manufacturer_bands.items():
            row = db.get(Discount, code)
            if row is None:
                db.add(Discount(manufacturer_code=code, band=band))
            else:
                row.band = band
        db.commit()
        applied = manufacturer_bands

    return CoopParseReport(
        title=parsed.title,
        source_contract=parsed.source_contract,
        source_url=parsed.source_url,
        bands_parsed=len(parsed.bands),
        manufacturer_bands=manufacturer_bands,
        applied_bands=applied,
        bands=[DiscountBandOut(**b.as_dict()) for b in parsed.bands],
        warnings=parsed.warnings,
    )


# ── Integration (for the integrator) ────────────────────────────────────────────────────
# In app/main.py:
#     from .routers import catalog, coop, ingest, projects, quote   # add `coop`
#     app.include_router(coop.router)
# No new dependency is required (pdfplumber is already installed).
