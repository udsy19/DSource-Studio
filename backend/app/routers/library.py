"""Steelcase catalog API — the settings (whole rooms) + products (individual SKUs) library that
backs generation and swapping. Settings drive room-swap alternatives; products drive piece-swap
(switch this chair/table for another of the same category). Reads the offline-built settings.json
(empty when absent, so the UI just shows nothing rather than erroring).
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Query

from ..testfit.settings import (
    Product,
    Setting,
    build_products,
    load_settings,
    products_for,
    settings_for,
)

router = APIRouter(prefix="/api/library", tags=["library"])

# Built offline + read-only at runtime, so load once per process.
_settings: list[Setting] | None = None
_products: list[Product] | None = None


def _catalog() -> tuple[list[Setting], list[Product]]:
    global _settings, _products
    if _settings is None:
        _settings = load_settings()
        _products = build_products(_settings)
    return _settings, _products or []


@router.get("/settings")
def list_settings(
    type: str | None = None,
    max_w: float | None = Query(None),
    max_h: float | None = Query(None),
):
    """Settings, optionally filtered to a type that fits within (max_w, max_h) — room-swap options."""
    settings, _ = _catalog()
    if type and max_w is not None and max_h is not None:
        settings = settings_for(settings, type, max_w, max_h)
    elif type:
        settings = [s for s in settings if s.setting_type == type]
    return [asdict(s) for s in settings]


@router.get("/products")
def list_products(category: str | None = None):
    """Real furniture SKUs, optionally filtered to a category — piece-swap options."""
    _, products = _catalog()
    products = products_for(products, category) if category else products
    return [asdict(p) for p in products]
