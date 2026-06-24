"""Tier 0 — Shopify Storefront /products.json.

The public Liquid-rendered route (unaffected by the 2024 Admin REST deprecation): GET
/products.json?limit=250&page=N until an empty products array. Parsing is pure; fetching
pages over the network goes through HarvestClient.
"""

from __future__ import annotations

import re

from ..ingest.service import infer_category
from .client import HarvestClient
from .schema import NormalizedProduct, derive_gst

_TAG_RE = re.compile(r"<[^>]+>")

# office/work cues -> workplace; everything else defaults to residential (a soft hint only)
_WORKPLACE_HINTS = ("office", "desk", "workstation", "task chair", "conference", "ergonomic")


def parse_products_json(
    payload: dict, manufacturer_code: str, vendor: str | None = None, base_url: str | None = None
) -> list[NormalizedProduct]:
    return [
        _parse_product(p, manufacturer_code, vendor, base_url)
        for p in payload.get("products", [])
    ]


def fetch_shopify(
    domain: str, manufacturer_code: str, client: HarvestClient | None = None, max_pages: int = 40
) -> list[NormalizedProduct]:
    client = client or HarvestClient()
    base = f"https://{domain.rstrip('/')}"
    out: list[NormalizedProduct] = []
    for page in range(1, max_pages + 1):
        payload = client.get_json(f"{base}/products.json", params={"limit": 250, "page": page})
        batch = payload.get("products", [])
        if not batch:
            break
        out.extend(parse_products_json({"products": batch}, manufacturer_code, base_url=base))
    return out


def _parse_product(
    p: dict, manufacturer_code: str, vendor: str | None, base_url: str | None
) -> NormalizedProduct:
    title = (p.get("title") or "").strip()
    handle = (p.get("handle") or "").strip()
    tags = [str(t) for t in p.get("tags", [])]
    variant = _primary_variant(p.get("variants", []))

    np = NormalizedProduct(
        manufacturer_code=manufacturer_code,
        sku=(variant.get("sku") or "").strip() or handle,
        title=title,
        vendor=(p.get("vendor") or vendor or manufacturer_code).strip(),
        url=f"{base_url}/products/{handle}" if base_url and handle else None,
        category=infer_category(f"{title} {p.get('product_type', '')}"),
        image_urls=[img["src"] for img in p.get("images", []) if img.get("src")],
        color=_tag_value(tags, ("color_", "colour_")),
        finish=_tag_value(tags, ("finish_",)),
        description=_strip_html(p.get("body_html")),
        raw_blob=p,
    )

    if not (variant.get("sku") or "").strip():
        np.flag("sku")  # fell back to handle

    np.price_inr = _parse_price(variant.get("price"))
    if np.price_inr is None:
        np.flag("price_inr")  # B2B/quote-only or missing — never store 0 as a real price

    np.gst_rate = derive_gst(np.category)
    np.flag("gst_rate")  # always estimated from category, never sourced

    material = _tag_value(tags, ("material_",))
    if material:
        np.material_attrs = {"primary_material": material}
    else:
        np.flag("material")  # commonly only in body_html prose -> left for enrichment

    if not np.image_urls:
        np.flag("image_urls")

    np.typology_tags = ["workplace"] if _looks_workplace(f"{title} {' '.join(tags)}") else ["residential"]
    return np


def _primary_variant(variants: list[dict]) -> dict:
    """Prefer the first non-zero-priced variant (some stores list a ₹0 'sample' variant first,
    e.g. wallpaper rolls), then the first available, then the first listed."""
    if not variants:
        return {}
    priced = [v for v in variants if _parse_price(v.get("price")) is not None]
    if priced:
        return next((v for v in priced if v.get("available")), priced[0])
    return next((v for v in variants if v.get("available")), variants[0])


def _parse_price(raw) -> float | None:
    if raw is None:
        return None
    cleaned = "".join(c for c in str(raw) if c.isdigit() or c == ".")
    if not cleaned:
        return None
    value = float(cleaned)
    return value if value > 0 else None


def _tag_value(tags: list[str], prefixes: tuple[str, ...]) -> str | None:
    for t in tags:
        low = t.lower()
        for pre in prefixes:
            if low.startswith(pre) and "_" in t:
                return t.split("_", 1)[1].strip() or None
    return None


def _looks_workplace(text: str) -> bool:
    low = text.lower()
    return any(h in low for h in _WORKPLACE_HINTS)


def _strip_html(html: str | None) -> str | None:
    if not html:
        return None
    text = " ".join(_TAG_RE.sub(" ", html).split())
    return text[:2000] or None
