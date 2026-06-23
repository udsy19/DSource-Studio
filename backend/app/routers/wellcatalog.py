"""WELL-ranked catalog API.

GET /api/wellcatalog/rank   -> products ranked by composite WELL + lead + cost score
GET /api/wellcatalog/cert/{sku} -> a single product's certification facts

Products without a cert still appear (cert: null) and rank lower. US / USD.

NOT registered in app/main.py (that file is read-only for this layer). To wire it up, add:

    from .routers import wellcatalog
    app.include_router(wellcatalog.router)

and seed certs at bootstrap (after the catalog SIF ingest) with:

    from .wellcatalog.models import ProductCert  # ensures table is created by create_all
    from .wellcatalog.seed import seed_certs
    seed_certs(db)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product
from ..wellcatalog.models import ProductCert
from ..wellcatalog.ranking import RankedProduct, rank_products

router = APIRouter(prefix="/api/wellcatalog", tags=["wellcatalog"])


def _cert_dict(cert: ProductCert | None) -> dict | None:
    if cert is None:
        return None
    return {
        "sku": cert.sku,
        "well_rating": cert.well_rating,
        "lead_time_days": cert.lead_time_days,
        "low_voc": cert.low_voc,
        "recycled_pct": cert.recycled_pct,
        "embodied_carbon_kg": cert.embodied_carbon_kg,
    }


def _ranked_dict(r: RankedProduct) -> dict:
    cert = None
    if r.cert is not None:
        cert = {
            "well_rating": r.cert.well_rating,
            "lead_time_days": r.cert.lead_time_days,
            "low_voc": r.cert.low_voc,
            "recycled_pct": r.cert.recycled_pct,
            "embodied_carbon_kg": r.cert.embodied_carbon_kg,
        }
    return {
        "product_id": r.product_id,
        "sku": r.sku,
        "manufacturer_code": r.manufacturer_code,
        "name": r.name,
        "category": r.category,
        "list_price": r.list_price,
        "has_cert": r.has_cert,
        "cert": cert,
        "score": r.score,
        "why": r.why,
    }


@router.get("/rank")
def rank(
    category: str | None = Query(None, description="e.g. seating, desking, tables, flooring, pods"),
    w_well: float = Query(0.5, ge=0.0, description="weight on WELL rating"),
    w_lead: float = Query(0.25, ge=0.0, description="weight on (short) lead time"),
    w_cost: float = Query(0.25, ge=0.0, description="weight on (low) cost"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    ranked = rank_products(
        db, category=category, w_well=w_well, w_lead=w_lead, w_cost=w_cost
    )
    return {
        "category": category,
        "weights": {"well": w_well, "lead": w_lead, "cost": w_cost},
        "count": len(ranked),
        "currency": "USD",
        "results": [_ranked_dict(r) for r in ranked[:limit]],
    }


@router.get("/cert/{sku}")
def get_cert(sku: str, db: Session = Depends(get_db)):
    cert = db.query(ProductCert).filter(ProductCert.sku == sku).one_or_none()
    product = db.query(Product).filter(Product.sku == sku).first()
    if cert is None and product is None:
        raise HTTPException(status_code=404, detail=f"No product or cert for sku {sku!r}")
    return {
        "sku": sku,
        "has_cert": cert is not None,
        "cert": _cert_dict(cert),
        "product": (
            {
                "product_id": product.id,
                "name": product.name,
                "category": product.category,
                "manufacturer_code": product.manufacturer_code,
                "list_price": product.list_price,
            }
            if product is not None
            else None
        ),
    }
