"""The Steelcase catalog API — settings/products/geometry endpoints degrade gracefully."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_products_endpoint_returns_a_list():
    r = client.get("/api/library/products", params={"category": "chair"})
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_geometry_missing_sku_returns_empty_footprint_fallback():
    r = client.get("/api/library/geometry", params={"sku": "__no_such_sku__"})
    assert r.status_code == 200
    assert r.json() == {"outline": [], "w": 0, "h": 0}
