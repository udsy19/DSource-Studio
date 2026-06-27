import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Product
from app.matching import MatchBands, format_hits


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield s
    finally:
        s.close()


BANDS = MatchBands(exact=0.13, close=0.08)


def _add(db, provenance):
    p = Product(manufacturer_code="NK", sku="SKU-1", name="Test Chair", provenance=provenance)
    db.add(p)
    db.flush()
    return p.id


def test_enrichment_material_and_dict_exposed(db):
    enrichment = {"primary_material": {"value": "solid sheesham", "confidence": 0.7, "source": "description"}}
    product_id = _add(db, {"enrichment": enrichment})

    result = format_hits(db, [(product_id, 0.9)], BANDS)[0]

    assert result["material"] == "solid sheesham"
    assert result["enrichment"] == enrichment
    # material maps to a known family -> a real derived maintenance profile is attached
    assert result["maintenance"] is not None
    assert "dust_static_affinity" in result["maintenance"]


def test_unmappable_material_has_no_maintenance(db):
    product_id = _add(db, {"material_attrs": {"primary_material": "aerogel"}})
    result = format_hits(db, [(product_id, 0.9)], BANDS)[0]
    assert result["material"] == "aerogel"
    assert result["maintenance"] is None  # unknown family -> no fabricated profile


def test_material_attrs_fallback_no_enrichment(db):
    product_id = _add(db, {"material_attrs": {"primary_material": "Mesh"}})

    result = format_hits(db, [(product_id, 0.9)], BANDS)[0]

    assert result["material"] == "Mesh"
    assert result["enrichment"] is None


def test_no_provenance_yields_none(db):
    product_id = _add(db, None)

    result = format_hits(db, [(product_id, 0.9)], BANDS)[0]

    assert result["material"] is None
    assert result["enrichment"] is None
