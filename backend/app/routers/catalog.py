from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Product
from ..schemas import ProductOut

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("", response_model=list[ProductOut])
def list_products(
    q: str | None = Query(None),
    category: str | None = None,
    manufacturer_code: str | None = None,
    limit: int = Query(500, le=2000),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(
            func.lower(Product.name).like(like),
            func.lower(Product.sku).like(like),
            func.lower(Product.manufacturer_code).like(like),
        ))
    if category:
        query = query.filter(func.lower(Product.category) == category.lower())
    if manufacturer_code:
        query = query.filter(Product.manufacturer_code == manufacturer_code)
    return query.order_by(Product.manufacturer_code, Product.name).limit(limit).all()


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    cats = [c[0] for c in db.query(Product.category).distinct().order_by(Product.category)]
    mfrs = [m[0] for m in db.query(Product.manufacturer_code).distinct().order_by(Product.manufacturer_code)]
    return {"categories": cats, "manufacturer_codes": mfrs, "count": db.query(Product).count()}
