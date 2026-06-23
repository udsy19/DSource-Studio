"""Smart Procurement router (Phase 3).

POST /api/procurement/rfq -> ranked vendor comparison for a confirmed BOM.
POST /api/procurement/po  -> Purchase Order document for a chosen vendor.

Vendors are SYNTHETIC (see app/procurement/models.py). USD only.

NOT registered in app/main.py by this module — the integrator adds:
    from .routers import procurement
    app.include_router(procurement.router)
Tables are created by the existing `Base.metadata.create_all(bind=engine)` in main.bootstrap()
(this module's models reuse the shared Base). To seed vendors at boot, call
`app.procurement.service.seed_vendors(db)` inside bootstrap().
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..procurement import service
from ..procurement.models import seed_vendors

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


class BomLineIn(BaseModel):
    sku: str
    qty: float = 1.0
    unit_list: float = 0.0
    manufacturer_code: str = ""
    name: str = ""


class RfqRequest(BaseModel):
    lines: list[BomLineIn] = Field(default_factory=list)


class PoRequest(BaseModel):
    lines: list[BomLineIn] = Field(default_factory=list)
    vendor_id: int


def _to_bom(lines: list[BomLineIn]) -> list[service.BomLine]:
    if not lines:
        raise HTTPException(status_code=422, detail="BOM has no lines.")
    return [service.BomLine.from_dict(l.model_dump()) for l in lines]


@router.post("/vendors/seed")
def seed(db: Session = Depends(get_db)):
    """Idempotently seed the synthetic US vendors. Handy when running this router standalone."""
    created = seed_vendors(db)
    return {"created": created, "synthetic": True}


@router.post("/rfq")
def rfq(req: RfqRequest, db: Session = Depends(get_db)):
    bom = _to_bom(req.lines)
    bids = service.build_rfq(db, bom)
    return {
        "currency": service.CURRENCY,
        "lines_total": len(bom),
        "vendor_count": len(bids),
        "vendors": [service.bid_to_dict(b) for b in bids],
        "is_synthetic": True,
        "note": "Vendors are synthetic placeholders; real dealer-vendor terms are unpublished.",
    }


@router.post("/po")
def po(req: PoRequest, db: Session = Depends(get_db)):
    bom = _to_bom(req.lines)
    try:
        return service.build_po(db, bom, req.vendor_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
