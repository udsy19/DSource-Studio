"""Procurement service — BOM -> RFQ vendor comparison -> Purchase Order.

The dealer confirms a test-fit BOM (lines of {sku, qty, unit_list, manufacturer_code}), then:

  1. build_rfq(): for every vendor that carries at least one line's manufacturer, compute the
     vendor's net total, max lead time over the lines it can supply, and line coverage (% of
     BOM lines fulfillable). Rank by a composite cost+lead-time score (lower is better).
  2. build_po(): for a chosen vendor, emit a Purchase Order document (PO number, line items,
     subtotal/tax/total, delivery window = today + lead_time).

Pricing reuses the dealer's list-minus logic (engine baseline): a line's net is
    unit_list * qty * (1 - DISCOUNT_BASELINE) * vendor.price_multiplier
The vendor's multiplier tilts that net up or down vs the dealer's standard discount band.

USD throughout. Vendors are SYNTHETIC (see app/procurement/models.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .models import Vendor, seed_vendors  # re-exported for convenience

# Baseline list-minus discount used to net merchandise before applying a vendor multiplier.
# Mirrors the dealer's standard discount posture (~0.45) without coupling to per-mfr bands;
# the vendor's price_multiplier is what differentiates vendors in the comparison.
DISCOUNT_BASELINE = 0.45

# Modeled sales tax on merchandise (US/USD). Kept flat here — the firm tax lands in the
# dealer's ERP; this is a procurement-side estimate.
TAX_RATE = 0.0863

# Composite ranking weights. Score = cost_norm * COST_W + lead_norm * LEAD_W (lower = better).
# Both terms are normalized to [0,1] across the candidate set so neither dominates by units.
COST_WEIGHT = 0.7
LEAD_WEIGHT = 0.3

CURRENCY = "USD"


@dataclass
class BomLine:
    sku: str
    qty: float
    unit_list: float
    manufacturer_code: str
    name: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "BomLine":
        return cls(
            sku=str(d["sku"]),
            qty=float(d.get("qty", 1)),
            unit_list=float(d.get("unit_list", 0.0)),
            manufacturer_code=str(d.get("manufacturer_code", "")),
            name=str(d.get("name", "")),
        )


@dataclass
class VendorBid:
    vendor_id: int
    vendor_name: str
    city: str
    state: str
    price_multiplier: float
    lead_time_days: int                 # max lead time over the lines this vendor supplies
    lines_covered: int
    lines_total: int
    coverage_pct: float                 # 0..1 fraction of BOM lines fulfillable
    net_total: float                    # USD, sum of covered lines' net
    composite_score: float = 0.0        # lower is better; set during ranking
    rank: int = 0
    can_fulfill_all: bool = False
    uncovered_skus: list[str] = field(default_factory=list)


def _line_net(line: BomLine, multiplier: float) -> float:
    return round(line.unit_list * line.qty * (1 - DISCOUNT_BASELINE) * multiplier, 2)


def _vendor_bid(vendor: Vendor, lines: list[BomLine]) -> VendorBid:
    carried = set(vendor.carried_manufacturers or [])
    net_total = 0.0
    covered = 0
    uncovered: list[str] = []
    max_lead = 0
    for ln in lines:
        if ln.manufacturer_code in carried:
            net_total += _line_net(ln, vendor.price_multiplier)
            covered += 1
            max_lead = max(max_lead, vendor.lead_time_days)
        else:
            uncovered.append(ln.sku)
    total = len(lines)
    return VendorBid(
        vendor_id=vendor.id, vendor_name=vendor.name, city=vendor.city, state=vendor.state,
        price_multiplier=vendor.price_multiplier,
        lead_time_days=max_lead,
        lines_covered=covered, lines_total=total,
        coverage_pct=round(covered / total, 4) if total else 0.0,
        net_total=round(net_total, 2),
        can_fulfill_all=(covered == total and total > 0),
        uncovered_skus=uncovered,
    )


def _rank(bids: list[VendorBid]) -> list[VendorBid]:
    """Rank by composite cost+lead score (lower = better).

    Full-coverage vendors always outrank partial-coverage ones; within a coverage tier we
    normalize net cost and lead time to [0,1] and blend. A single candidate scores 0.0.
    """
    if not bids:
        return bids

    def normalize(values: list[float]) -> dict[int, float]:
        lo, hi = min(values), max(values)
        span = hi - lo
        if span <= 0:
            return {i: 0.0 for i in range(len(values))}
        return {i: (v - lo) / span for i, v in enumerate(values)}

    costs = normalize([b.net_total for b in bids])
    leads = normalize([float(b.lead_time_days) for b in bids])
    for i, b in enumerate(bids):
        b.composite_score = round(costs[i] * COST_WEIGHT + leads[i] * LEAD_WEIGHT, 4)

    # Higher coverage first (negate), then lower composite score.
    ordered = sorted(bids, key=lambda b: (-b.coverage_pct, b.composite_score, b.net_total))
    for idx, b in enumerate(ordered, start=1):
        b.rank = idx
    return ordered


def build_rfq(db: Session, lines: list[BomLine]) -> list[VendorBid]:
    """Return ranked VendorBids for every vendor that can supply >=1 BOM line.

    Vendors carrying none of the lines' manufacturers are excluded entirely.
    """
    vendors = db.query(Vendor).all()
    bids: list[VendorBid] = []
    for v in vendors:
        bid = _vendor_bid(v, lines)
        if bid.lines_covered > 0:  # only candidates that can actually supply something
            bids.append(bid)
    return _rank(bids)


def bid_to_dict(b: VendorBid) -> dict:
    return {
        "vendor_id": b.vendor_id,
        "vendor_name": b.vendor_name,
        "city": b.city,
        "state": b.state,
        "price_multiplier": b.price_multiplier,
        "lead_time_days": b.lead_time_days,
        "lines_covered": b.lines_covered,
        "lines_total": b.lines_total,
        "coverage_pct": b.coverage_pct,
        "net_total": b.net_total,
        "composite_score": b.composite_score,
        "rank": b.rank,
        "can_fulfill_all": b.can_fulfill_all,
        "uncovered_skus": b.uncovered_skus,
        "currency": CURRENCY,
    }


# --- Purchase Order ---------------------------------------------------------------------

def _po_number(vendor_id: int, today: date) -> str:
    return f"PO-{today.strftime('%Y%m%d')}-V{vendor_id:03d}"


def build_po(db: Session, lines: list[BomLine], vendor_id: int, today: date | None = None) -> dict:
    """Generate a Purchase Order document for `vendor_id` over the lines it can supply.

    Returns a dict (PO payload). Raises ValueError if the vendor is unknown or carries none
    of the BOM lines.
    """
    today = today or date.today()
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise ValueError(f"vendor {vendor_id} not found")

    carried = set(vendor.carried_manufacturers or [])
    po_lines: list[dict] = []
    skipped: list[str] = []
    subtotal = 0.0
    for ln in lines:
        if ln.manufacturer_code not in carried:
            skipped.append(ln.sku)
            continue
        net = _line_net(ln, vendor.price_multiplier)
        subtotal += net
        po_lines.append({
            "sku": ln.sku,
            "name": ln.name,
            "manufacturer_code": ln.manufacturer_code,
            "qty": ln.qty,
            "unit_list": round(ln.unit_list, 2),
            "extended_net": net,
        })

    if not po_lines:
        raise ValueError(f"vendor {vendor_id} carries none of the BOM lines")

    subtotal = round(subtotal, 2)
    tax = round(subtotal * TAX_RATE, 2)
    total = round(subtotal + tax, 2)
    delivery_date = today + timedelta(days=vendor.lead_time_days)

    return {
        "po_number": _po_number(vendor.id, today),
        "currency": CURRENCY,
        "issued_date": today.isoformat(),
        "vendor": {
            "id": vendor.id,
            "name": vendor.name,
            "city": vendor.city,
            "state": vendor.state,
            "synthetic": True,
        },
        "lines": po_lines,
        "subtotal": subtotal,
        "tax_rate": TAX_RATE,
        "tax": tax,
        "total": total,
        "lead_time_days": vendor.lead_time_days,
        "delivery_window": {
            "from": today.isoformat(),
            "to": delivery_date.isoformat(),
            "days": vendor.lead_time_days,
        },
        "skipped_skus": skipped,
        "is_synthetic_vendor": True,
        "disclaimer": (
            "Procurement estimate against a SYNTHETIC vendor. Pricing = list minus a "
            f"{int(DISCOUNT_BASELINE * 100)}% baseline x the vendor's multiplier; tax is "
            "modeled. Not a firm purchase commitment."
        ),
    }


__all__ = [
    "BomLine", "VendorBid", "Vendor", "seed_vendors",
    "build_rfq", "build_po", "bid_to_dict",
    "DISCOUNT_BASELINE", "TAX_RATE", "CURRENCY",
]
