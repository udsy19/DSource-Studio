"""Phase 3 — Smart Procurement: BOM -> RFQ vendor comparison -> Purchase Order.

Fast & self-contained: in-memory SQLite, no app bootstrap, no PDF/DXF parsing. We seed the
synthetic vendors directly and assert ranking, coverage filtering, and PO arithmetic.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.procurement import service
from app.procurement.models import SYNTHETIC_VENDORS, Vendor, seed_vendors


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    seed_vendors(s)
    try:
        yield s
    finally:
        s.close()


def _bom():
    # All-HMI BOM: a desk + a task chair. Every vendor carrying "HMI" can fulfill both lines.
    return [
        service.BomLine(sku="SC-OLOGY-RECT", qty=10, unit_list=1200.0, manufacturer_code="HMI", name="Desk"),
        service.BomLine(sku="AER1", qty=10, unit_list=1726.0, manufacturer_code="HMI", name="Aeron"),
    ]


def test_vendors_seeded(db):
    assert db.query(Vendor).count() == len(SYNTHETIC_VENDORS)
    # Idempotent: re-seeding adds nothing.
    assert seed_vendors(db) == 0
    assert db.query(Vendor).count() == len(SYNTHETIC_VENDORS)


def test_rfq_returns_ranked_vendors(db):
    bids = service.build_rfq(db, _bom())
    assert bids, "expected at least one candidate vendor"
    # Ranks are 1..n, contiguous and ordered.
    assert [b.rank for b in bids] == list(range(1, len(bids) + 1))
    scores = [b.composite_score for b in bids]
    # Full-coverage vendors first; within them composite score is non-decreasing.
    full = [b for b in bids if b.can_fulfill_all]
    full_scores = [b.composite_score for b in full]
    assert full_scores == sorted(full_scores)


def test_only_carrying_vendors_appear(db):
    # FRM-only BOM: only vendors carrying "FRM" may appear.
    bom = [service.BomLine(sku="FRM-POD", qty=2, unit_list=9000.0, manufacturer_code="FRM", name="Pod")]
    bids = service.build_rfq(db, bom)
    assert bids
    carrying = {v["name"] for v in SYNTHETIC_VENDORS if "FRM" in v["carried_manufacturers"]}
    assert {b.vendor_name for b in bids} == carrying
    for b in bids:
        assert b.lines_covered == 1


def test_excludes_vendors_with_no_coverage(db):
    # A manufacturer no synthetic vendor carries -> no candidates.
    bom = [service.BomLine(sku="ZZZ", qty=1, unit_list=100.0, manufacturer_code="NOPE", name="x")]
    assert service.build_rfq(db, bom) == []


def test_coverage_partial(db):
    # HMI line every HMI vendor covers; ZZZ line nobody covers -> coverage < 1.0 for all.
    bom = [
        service.BomLine(sku="A", qty=1, unit_list=1000.0, manufacturer_code="HMI", name="a"),
        service.BomLine(sku="B", qty=1, unit_list=1000.0, manufacturer_code="NOPE", name="b"),
    ]
    bids = service.build_rfq(db, bom)
    assert bids
    for b in bids:
        assert b.coverage_pct == 0.5
        assert not b.can_fulfill_all
        assert "B" in b.uncovered_skus


def test_price_multiplier_affects_net(db):
    bom = _bom()
    bids = service.build_rfq(db, bom)
    by_name = {b.vendor_name: b for b in bids}
    # Pacific (0.95) should net cheaper than Empire State (1.05) on the same all-HMI BOM.
    pac = by_name["Pacific Workspace Supply (synthetic)"]
    emp = by_name["Empire State Furniture Group (synthetic)"]
    assert pac.net_total < emp.net_total


def test_po_totals_add_up(db):
    bom = _bom()
    bids = service.build_rfq(db, bom)
    top = bids[0]
    po = service.build_po(db, bom, top.vendor_id)

    # Subtotal == sum of line extended_net.
    line_sum = round(sum(l["extended_net"] for l in po["lines"]), 2)
    assert po["subtotal"] == line_sum
    # Subtotal + tax == total (within a cent).
    assert abs(po["subtotal"] + po["tax"] - po["total"]) < 0.01
    assert po["tax"] == round(po["subtotal"] * service.TAX_RATE, 2)
    assert po["currency"] == "USD"
    assert po["po_number"].startswith("PO-")
    assert po["is_synthetic_vendor"] is True


def test_po_line_net_matches_formula(db):
    bom = _bom()
    bids = service.build_rfq(db, bom)
    top = bids[0]
    vendor = db.get(Vendor, top.vendor_id)
    po = service.build_po(db, bom, top.vendor_id)

    line = po["lines"][0]
    bl = bom[0]
    expected = round(
        bl.unit_list * bl.qty * (1 - service.DISCOUNT_BASELINE) * vendor.price_multiplier, 2
    )
    assert line["extended_net"] == expected


def test_po_delivery_window_is_today_plus_lead(db):
    bom = _bom()
    bids = service.build_rfq(db, bom)
    top = bids[0]
    vendor = db.get(Vendor, top.vendor_id)
    today = date(2026, 6, 22)
    po = service.build_po(db, bom, top.vendor_id, today=today)

    assert po["issued_date"] == today.isoformat()
    assert po["delivery_window"]["from"] == today.isoformat()
    expected_to = (today + timedelta(days=vendor.lead_time_days)).isoformat()
    assert po["delivery_window"]["to"] == expected_to
    assert po["delivery_window"]["days"] == vendor.lead_time_days


def test_po_skips_uncovered_lines(db):
    bom = [
        service.BomLine(sku="A", qty=1, unit_list=1000.0, manufacturer_code="HMI", name="a"),
        service.BomLine(sku="B", qty=1, unit_list=1000.0, manufacturer_code="NOPE", name="b"),
    ]
    bids = service.build_rfq(db, bom)
    vendor_id = bids[0].vendor_id
    po = service.build_po(db, bom, vendor_id)
    assert "B" in po["skipped_skus"]
    assert all(l["sku"] != "B" for l in po["lines"])


def test_po_unknown_vendor_raises(db):
    with pytest.raises(ValueError):
        service.build_po(db, _bom(), vendor_id=99999)
