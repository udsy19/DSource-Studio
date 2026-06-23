"""Real-data tests: the studio test-fit quote must price Herman Miller items off REAL price-book
list prices and the REAL NASPO/WA-DES MillerKnoll co-op discount band — not the synthetic seed.

These build an isolated in-memory catalog, run the same ingest path bootstrap() uses, then drive
the test-fit BOM/quote builder against the real sample floor plate. They skip cleanly if the real
HM price-book PDFs or the sample DXF have not been provisioned.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.floorplan.dxf_ingest import ingest_dxf
from app.models import Discount, Product
from app.realdata import HMI_COOP_BAND, apply_coop_hmi_band, ingest_hm_pricebooks
from app.routers.testfit import _build_bom_and_quote
from app.seed import seed
from app.testfit.layout import ProgramSpec, WorkstationSpec, generate_mixed_layout

PRICEBOOKS = Path(__file__).resolve().parent.parent / "data" / "pricebooks"
AERON = PRICEBOOKS / "PB_AEN.pdf"
DXF = Path(__file__).resolve().parent.parent / "data" / "floorplans" / "sample_office.dxf"

pytestmark = pytest.mark.skipif(
    not AERON.exists() or not DXF.exists(),
    reason="real HM price book or sample DXF not provisioned",
)


@pytest.fixture(scope="module")
def db():
    # module-scoped: parse the 12 HM PDFs once for the whole module, not per test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()
    seed(session)
    ingest_hm_pricebooks(session)
    apply_coop_hmi_band(session)
    try:
        yield session
    finally:
        session.close()


def test_catalog_has_real_hm_pricebook_products(db):
    """The catalog contains real HM products sourced from price books with plausible prices."""
    real = db.query(Product).filter(
        Product.manufacturer_code == "HMI", Product.source == "pricebook"
    ).all()
    assert real, "no real HM price-book products were ingested"
    assert all(p.list_price > 0 for p in real)
    # Aeron AER1's real starting list price is $1726 (verified against the published 6/26 book).
    aer1 = next((p for p in real if p.sku == "AER1"), None)
    assert aer1 is not None
    assert aer1.list_price == 1726.0


def test_hmi_discount_is_real_coop_band(db):
    """HMI's discount band is the REAL co-op value (0.505) from the WA-DES MillerKnoll contract."""
    assert HMI_COOP_BAND == 0.505
    row = db.get(Discount, "HMI")
    assert row is not None
    assert row.band == 0.505


def test_testfit_quote_bom_has_real_pricebook_lines(db):
    """The test-fit BOM has at least some lines that are real=True, sourced from price books."""
    plan = ingest_dxf(str(DXF))
    fit = generate_mixed_layout(plan, WorkstationSpec(), ProgramSpec())
    assert fit.instances, "mixed layout placed no instances"

    bom, quote, _skipped = _build_bom_and_quote(db, fit)
    assert bom, "BOM is empty"

    real_lines = [b for b in bom if b["real"]]
    assert real_lines, "no real (price-book sourced) BOM lines"
    assert all(b["source"] == "pricebook" for b in real_lines)
    assert all(b["unit_list"] > 0 for b in real_lines)
    # Aeron (real) must be one of them — it's mapped onto workstation + private-office chairs.
    assert any(b["sku"] == "AER1" for b in real_lines)
    # The quote nets real list below subtotal via the real co-op discount.
    assert quote["net_merchandise"] < quote["subtotal_list"]
    assert quote["total"] > 0
