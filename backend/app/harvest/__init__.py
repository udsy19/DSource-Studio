"""Catalog harvesting — turn public India supplier sites into NormalizedProduct rows.

Tiered, cheapest/most-robust-first: Tier 0 Shopify /products.json (here), then WooCommerce
Store API, schema.org JSON-LD, headless render. Parsing is pure and offline-testable; the
network fetch lives behind HarvestClient. Never fakes a field — missing/estimated values are
recorded in NormalizedProduct.flagged_fields.
"""
