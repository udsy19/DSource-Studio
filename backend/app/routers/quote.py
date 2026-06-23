from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..ingest import service
from ..models import Product, Project
from ..pricing.engine import QuoteLineInput, compute_quote
from ..schemas import QuoteLineOut, QuoteOut

router = APIRouter(prefix="/api/quote", tags=["quote"])


def _to_out(result, project: Project | None = None) -> QuoteOut:
    return QuoteOut(
        is_budgetary=result.is_budgetary, disclaimer=result.disclaimer,
        project_id=project.id if project else None,
        project_name=project.name if project else None,
        lines=[QuoteLineOut(**vars(l)) for l in result.lines],
        subtotal_list=result.subtotal_list, discount_amount=result.discount_amount,
        net_merchandise=result.net_merchandise, install_rate=result.install_rate,
        freight_rate=result.freight_rate, tax_rate=result.tax_rate,
        install=result.install, freight=result.freight, taxable_base=result.taxable_base,
        tax=result.tax, total=result.total,
    )


@router.get("/project/{project_id}", response_model=QuoteOut)
def quote_project(project_id: int, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    inputs, rates = service.quote_inputs_for_project(db, project)
    return _to_out(compute_quote(inputs, rates), project)


class AdHocLine(BaseModel):
    product_id: int
    qty: float


class AdHocQuoteRequest(BaseModel):
    lines: list[AdHocLine]


@router.post("", response_model=QuoteOut)
def quote_adhoc(req: AdHocQuoteRequest, db: Session = Depends(get_db)):
    if not req.lines:
        raise HTTPException(status_code=422, detail="No line items.")
    settings = service.get_settings(db)
    from ..pricing.engine import DealerRates
    rates = DealerRates(settings.install_rate, settings.freight_rate, settings.tax_rate)
    inputs: list[QuoteLineInput] = []
    for ln in req.lines:
        product = db.get(Product, ln.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail=f"Product {ln.product_id} not found.")
        band = service.resolve_discount(db, product.manufacturer_code, settings, None)
        inputs.append(QuoteLineInput(
            product_id=product.id, manufacturer_code=product.manufacturer_code,
            sku=product.sku, name=product.name, qty=ln.qty,
            unit_list=product.list_price, discount_band=band,
        ))
    return _to_out(compute_quote(inputs, rates))
