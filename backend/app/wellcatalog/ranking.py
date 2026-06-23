"""Composite ranking of catalog products by WELL compliance + lead time + cost.

score = w_well * well_component
      + w_lead * lead_component        (shorter lead time -> higher)
      + w_cost * cost_component        (lower list_price -> higher, normalized in category)

Each component is normalized to 0..1 within the candidate set (per category when filtered),
so the composite is comparable across very different price/lead scales. Products WITHOUT a
ProductCert still appear, treated as a worst-case "none" profile, so they rank lower but are
never dropped — surfacing the catalog-data gap rather than hiding it.

US / USD. list_price is USD list (read off the read-only Product spine).
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Product
from .models import ProductCert

# WELL rating -> quality score (best 1.0). "none"/unknown -> 0.0.
WELL_SCORE = {"A+": 1.0, "A": 0.8, "B": 0.5, "none": 0.0}

DEFAULT_WEIGHTS = {"well": 0.5, "lead": 0.25, "cost": 0.25}


@dataclass
class CertView:
    well_rating: str = "none"
    lead_time_days: int | None = None
    low_voc: bool = False
    recycled_pct: float = 0.0
    embodied_carbon_kg: float = 0.0

    @classmethod
    def from_row(cls, c: ProductCert) -> "CertView":
        return cls(
            well_rating=c.well_rating,
            lead_time_days=c.lead_time_days,
            low_voc=c.low_voc,
            recycled_pct=c.recycled_pct,
            embodied_carbon_kg=c.embodied_carbon_kg,
        )


@dataclass
class RankedProduct:
    product_id: int
    sku: str
    manufacturer_code: str
    name: str
    category: str
    list_price: float
    has_cert: bool
    cert: CertView | None
    score: float
    why: dict = field(default_factory=dict)


def _normalize_weights(well: float, lead: float, cost: float) -> tuple[float, float, float]:
    total = well + lead + cost
    if total <= 0:
        d = DEFAULT_WEIGHTS
        return d["well"], d["lead"], d["cost"]
    return well / total, lead / total, cost / total


def _norm_lower_better(value: float, lo: float, hi: float) -> float:
    """Map value into 0..1 where the smallest value -> 1.0 (best)."""
    if hi <= lo:
        return 1.0
    return (hi - value) / (hi - lo)


def rank_products(
    db: Session,
    category: str | None = None,
    weights: dict | None = None,
    w_well: float | None = None,
    w_lead: float | None = None,
    w_cost: float | None = None,
) -> list[RankedProduct]:
    """Join Product + ProductCert (LEFT join) and return products ranked by composite score.

    Weights may be supplied either as a `weights` dict ({"well","lead","cost"}) or as the
    individual w_* args (which override the dict). They are renormalized to sum to 1.
    """
    weights = weights or DEFAULT_WEIGHTS
    well_w = w_well if w_well is not None else weights.get("well", DEFAULT_WEIGHTS["well"])
    lead_w = w_lead if w_lead is not None else weights.get("lead", DEFAULT_WEIGHTS["lead"])
    cost_w = w_cost if w_cost is not None else weights.get("cost", DEFAULT_WEIGHTS["cost"])
    well_w, lead_w, cost_w = _normalize_weights(well_w, lead_w, cost_w)

    q = (
        db.query(Product, ProductCert)
        .outerjoin(ProductCert, ProductCert.sku == Product.sku)
    )
    if category:
        from sqlalchemy import func
        q = q.filter(func.lower(Product.category) == category.lower())
    rows = q.all()
    if not rows:
        return []

    # Candidate-set bounds for normalization (cost from all rows; lead from rows that have one).
    prices = [p.list_price or 0.0 for p, _ in rows]
    price_lo, price_hi = min(prices), max(prices)
    leads = [c.lead_time_days for _, c in rows if c is not None and c.lead_time_days is not None]
    # Missing lead times are penalized to the worst observed (or a floor) so no-cert ranks lower.
    worst_lead = max(leads) if leads else 0
    lead_lo = min(leads) if leads else 0
    lead_hi = worst_lead

    ranked: list[RankedProduct] = []
    for product, cert in rows:
        has_cert = cert is not None
        view = CertView.from_row(cert) if has_cert else None

        rating = cert.well_rating if has_cert else "none"
        well_component = WELL_SCORE.get(rating, 0.0)

        lead_value = (cert.lead_time_days if has_cert and cert.lead_time_days is not None
                      else worst_lead)
        lead_component = _norm_lower_better(lead_value, lead_lo, lead_hi)

        cost_component = _norm_lower_better(product.list_price or 0.0, price_lo, price_hi)

        score = well_w * well_component + lead_w * lead_component + cost_w * cost_component

        why = {
            "well": {
                "rating": rating,
                "component": round(well_component, 3),
                "weight": round(well_w, 3),
                "contribution": round(well_w * well_component, 3),
            },
            "lead": {
                "days": lead_value,
                "component": round(lead_component, 3),
                "weight": round(lead_w, 3),
                "contribution": round(lead_w * lead_component, 3),
            },
            "cost": {
                "list_price": product.list_price,
                "component": round(cost_component, 3),
                "weight": round(cost_w, 3),
                "contribution": round(cost_w * cost_component, 3),
            },
            "cert_present": has_cert,
        }

        ranked.append(RankedProduct(
            product_id=product.id,
            sku=product.sku,
            manufacturer_code=product.manufacturer_code,
            name=product.name,
            category=product.category,
            list_price=product.list_price,
            has_cert=has_cert,
            cert=view,
            score=round(score, 4),
            why=why,
        ))

    # Highest composite first; tie-break: has_cert, then cheaper, then sku for stability.
    ranked.sort(key=lambda r: (-r.score, not r.has_cert, r.list_price, r.sku))
    return ranked
