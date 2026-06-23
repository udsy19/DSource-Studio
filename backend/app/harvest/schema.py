"""NormalizedProduct — the one shape every harvest tier maps into.

Provenance is first-class: every field that is missing or estimated is named in
`flagged_fields`, so the NEVER-fake-data rule is enforced by the schema, not by convention.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

# GST is never present in source product data. Derive it from the product category (a proxy
# for HSN) and ALWAYS flag it estimated. Furniture (HSN 9401/9403) is 18%; others differ.
_GST_BY_CATEGORY: dict[str, float] = {
    "seating": 0.18,
    "desking": 0.18,
    "tables": 0.18,
    "storage": 0.18,
    "pods": 0.18,
    "flooring": 0.18,
    "lighting": 0.12,
    "textiles": 0.12,
    "plants": 0.05,
}


def derive_gst(category: str) -> float:
    """Best-effort GST from category. Callers must flag the field as estimated."""
    return _GST_BY_CATEGORY.get(category, 0.18)


class NormalizedProduct(BaseModel):
    # identity (canonical key mirrors the catalog: manufacturer_code + sku)
    manufacturer_code: str
    sku: str
    title: str
    vendor: str
    url: str | None = None

    # classification
    category: str = "other"
    typology_tags: list[str] = Field(default_factory=list)

    # media (multiple images power same-product self-calibration of match thresholds)
    image_urls: list[str] = Field(default_factory=list)

    # commercial — price_inr is None when the source omits/zeroes it (B2B quote-only); never 0-as-real
    price_inr: float | None = None
    gst_rate: float | None = None
    lead_time: str | None = None

    # material-level (best-effort from structured tags; prose extraction is enrichment's job)
    finish: str | None = None
    color: str | None = None
    material_attrs: dict = Field(default_factory=dict)

    # provenance / honesty
    source_tier: str = "shopify"
    harvested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    flagged_fields: list[str] = Field(default_factory=list)
    raw_blob: dict | None = None

    def flag(self, field: str) -> None:
        if field not in self.flagged_fields:
            self.flagged_fields.append(field)
