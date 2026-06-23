import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.enrichment.schema import Attribute, MaterialEnrichment, Source
from app.enrichment.service import content_hash, decide_provider, enrich_product, is_enriched
from app.models import Product


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield s
    finally:
        s.close()


class FakeIndex:
    def __init__(self, hits):
        self.hits = hits

    def query(self, vec, k=10, category=None):
        return self.hits


class FakeEmbedder:
    def embed_image(self, image):
        return [0.1, 0.2, 0.3, 0.4]


class FakeEnricher:
    def __init__(self, name, result, available=True):
        self.name, self._result, self._available, self.calls = name, result, available, 0

    def available(self):
        return self._available

    def enrich(self, image, title, description):
        self.calls += 1
        return self._result


def _product(db, name, category="seating", enriched=False):
    prov = {"description": "a nice chair"}
    p = Product(manufacturer_code="NK", sku=name, name=name, category=category,
                source="harvest", image_url=f"https://cdn/{name}.jpg", provenance=prov)
    db.add(p)
    db.flush()
    if enriched:
        prov = dict(prov)
        prov["enrichment"] = {"primary_material": {"value": "steel", "confidence": 0.8, "source": "image"}}
        prov["enrichment_hash"] = content_hash(p)
        p.provenance = prov
        db.flush()
    return p


RESULT = MaterialEnrichment(primary_material=Attribute(value="solid sheesham", confidence=0.7, source=Source.description))


def test_schema_defaults_to_missing():
    e = MaterialEnrichment()
    assert e.primary_material.value is None
    assert e.primary_material.source == Source.missing


def test_content_hash_changes_with_name(db):
    a, b = _product(db, "chair-a"), _product(db, "chair-b")
    assert content_hash(a) != content_hash(b)


def test_decide_provider_gemini_when_enriched_neighbor_is_close(db):
    candidate = _product(db, "new-chair")
    neighbor = _product(db, "old-chair", enriched=True)
    index = FakeIndex([(candidate.id, 1.0), (neighbor.id, 0.91)])  # neighbor above 0.85
    assert decide_provider(db, candidate, [0.1] * 4, index, threshold=0.85) == "gemini"


def test_decide_provider_claude_when_novel(db):
    candidate = _product(db, "new-chair")
    neighbor = _product(db, "old-chair", enriched=True)
    index = FakeIndex([(neighbor.id, 0.50)])  # closest enriched neighbor below threshold
    assert decide_provider(db, candidate, [0.1] * 4, index, threshold=0.85) == "claude"


def test_enrich_product_caches_and_does_not_call_model(db):
    p = _product(db, "chair", enriched=True)
    fake = FakeEnricher("claude", RESULT)
    out = enrich_product(db, p, enrichers={"claude": fake}, embedder=FakeEmbedder(),
                         index=FakeIndex([]), image=Image.new("RGB", (8, 8)))
    assert out["provider"] == "cache"
    assert fake.calls == 0


def test_enrich_product_routes_persists_and_flags(db):
    p = _product(db, "novel-chair")
    fake = FakeEnricher("claude", RESULT)
    out = enrich_product(db, p, enrichers={"claude": fake}, embedder=FakeEmbedder(),
                         index=FakeIndex([]), image=Image.new("RGB", (8, 8)))
    assert out["provider"] == "claude" and fake.calls == 1
    assert is_enriched(p)
    assert p.provenance["enrichment"]["primary_material"]["value"] == "solid sheesham"


def test_falls_back_to_available_provider(db):
    p = _product(db, "novel-chair")
    claude = FakeEnricher("claude", RESULT, available=False)  # preferred but unconfigured
    gemini = FakeEnricher("gemini", RESULT, available=True)
    out = enrich_product(db, p, enrichers={"gemini": gemini, "claude": claude},
                         embedder=FakeEmbedder(), index=FakeIndex([]), image=Image.new("RGB", (8, 8)))
    assert out["provider"] == "gemini" and gemini.calls == 1


class RaisingEnricher:
    name = "claude"

    def available(self):
        return True

    def enrich(self, image, title, description):
        raise RuntimeError("401 bad key")


def test_falls_back_when_preferred_provider_errors(db):
    # novel item routes to claude; claude raises (e.g. bad key) -> fall back to gemini.
    p = _product(db, "novel-chair")
    gemini = FakeEnricher("gemini", RESULT, available=True)
    out = enrich_product(db, p, enrichers={"claude": RaisingEnricher(), "gemini": gemini},
                         embedder=FakeEmbedder(), index=FakeIndex([]), image=Image.new("RGB", (8, 8)))
    assert out["provider"] == "gemini" and gemini.calls == 1
