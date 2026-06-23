"""WELL-ranked catalog tests — fast, in-memory SQLite, no PDF / no app bootstrap.

Verifies:
  * an A+ / short-lead / low-cost product ranks above a B / long-lead / high-cost one
  * shifting the composite weights flips the ordering (cost-dominant favors the cheap item)
  * a Product WITHOUT a cert still appears (cert is None) and ranks below a strong cert
  * the router endpoints respond against an isolated session
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import Product
from app.routers import wellcatalog as wellcatalog_router
from app.wellcatalog.models import ProductCert
from app.wellcatalog.ranking import rank_products


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    try:
        _seed(session)
        yield session
    finally:
        session.close()


def _seed(session):
    # Three seating products spanning the quality/lead/cost space.
    session.add_all([
        Product(id=1, manufacturer_code="HMI", sku="HM-AERON-B",
                name="Aeron Chair Size B", category="seating", list_price=1795.0),
        Product(id=2, manufacturer_code="KNL", sku="KN-SLOW-CHAIR",
                name="Slow Lounge Chair", category="seating", list_price=2400.0),
        Product(id=3, manufacturer_code="SC", sku="SC-NOCERT",
                name="Mystery Chair (no cert)", category="seating", list_price=900.0),
        # a flooring item to confirm category filtering excludes it
        Product(id=4, manufacturer_code="INT", sku="IF-WW890-CT",
                name="World Woven 890 Carpet Tile", category="flooring", list_price=4.85),
    ])
    session.add_all([
        # Best profile: A+, short lead, mid cost.
        ProductCert(sku="HM-AERON-B", well_rating="A+", lead_time_days=14,
                    low_voc=True, recycled_pct=39.0, embodied_carbon_kg=65.0),
        # Worst profile: B, long lead, high cost.
        ProductCert(sku="KN-SLOW-CHAIR", well_rating="B", lead_time_days=60,
                    low_voc=False, recycled_pct=10.0, embodied_carbon_kg=120.0),
        # SC-NOCERT intentionally has NO ProductCert row.
        ProductCert(sku="IF-WW890-CT", well_rating="A+", lead_time_days=24,
                    low_voc=True, recycled_pct=68.0, embodied_carbon_kg=6.0),
    ])
    session.commit()


def test_aplus_short_lead_low_cost_outranks_b_long_lead(db):
    ranked = rank_products(db, category="seating")
    skus = [r.sku for r in ranked]
    assert skus[0] == "HM-AERON-B"
    # The strong A+ product must rank above the B / long-lead / pricey one.
    assert skus.index("HM-AERON-B") < skus.index("KN-SLOW-CHAIR")


def test_no_cert_product_appears_and_ranks_lower(db):
    ranked = rank_products(db, category="seating")
    by_sku = {r.sku: r for r in ranked}
    # Present despite having no cert.
    assert "SC-NOCERT" in by_sku
    nocert = by_sku["SC-NOCERT"]
    assert nocert.has_cert is False
    assert nocert.cert is None
    assert nocert.why["well"]["rating"] == "none"
    # Ranks below the A+ Aeron.
    skus = [r.sku for r in ranked]
    assert skus.index("HM-AERON-B") < skus.index("SC-NOCERT")


def test_weights_change_ordering(db):
    # WELL-dominant: the A+ Aeron wins outright.
    well_first = rank_products(db, category="seating",
                               w_well=1.0, w_lead=0.0, w_cost=0.0)
    assert well_first[0].sku == "HM-AERON-B"

    # Cost-dominant: the cheapest seating (the no-cert $900 chair) rises to the top.
    cost_first = rank_products(db, category="seating",
                               w_well=0.0, w_lead=0.0, w_cost=1.0)
    assert cost_first[0].sku == "SC-NOCERT"

    # Ordering genuinely differs between the two weightings.
    assert [r.sku for r in well_first] != [r.sku for r in cost_first]


def test_category_filter(db):
    seating = rank_products(db, category="seating")
    assert all(r.category == "seating" for r in seating)
    assert "IF-WW890-CT" not in {r.sku for r in seating}

    flooring = rank_products(db, category="flooring")
    assert {r.sku for r in flooring} == {"IF-WW890-CT"}

    all_rows = rank_products(db)  # no filter -> everything
    assert len(all_rows) == 4


def test_router_rank_and_cert_endpoints(db):
    app = FastAPI()
    app.include_router(wellcatalog_router.router)
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    resp = client.get("/api/wellcatalog/rank", params={"category": "seating"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["currency"] == "USD"
    assert body["results"][0]["sku"] == "HM-AERON-B"
    # no-cert product surfaces with cert null
    nocert = next(r for r in body["results"] if r["sku"] == "SC-NOCERT")
    assert nocert["cert"] is None and nocert["has_cert"] is False

    cert_resp = client.get("/api/wellcatalog/cert/HM-AERON-B")
    assert cert_resp.status_code == 200
    cbody = cert_resp.json()
    assert cbody["has_cert"] is True
    assert cbody["cert"]["well_rating"] == "A+"
    assert cbody["product"]["category"] == "seating"

    # unknown sku -> 404
    assert client.get("/api/wellcatalog/cert/DOES-NOT-EXIST").status_code == 404
