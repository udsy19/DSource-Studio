"""Priced bill of materials from an extracted layout.

Furniture read from a CAD/CET drawing carries the manufacturer spec (brand, part number, list
price — see cad_reader._cet_spec). Aggregate it by product into a real, priced BOM: one line per
(brand, model, description), with quantity, unit list price, and line total. Items without a price
are reported separately and never faked (the project's never-fabricate rule).
"""

from __future__ import annotations

from collections import defaultdict

from ..ingestion.schema import ExtractedLayout, FurnitureItem


def _key(f: FurnitureItem) -> tuple[str, str, str]:
    return (f.brand or "", f.model or "", f.block_name or "")


def build_bom(layout: ExtractedLayout) -> dict:
    """Aggregate the layout's furniture into priced BOM lines + a grand total.

    Lines are grouped by (brand, model, description) and sorted by line total descending. Unpriced
    items (no list_price) are counted but excluded from the total, with their quantity surfaced so
    the gap is explicit rather than hidden."""
    priced: dict[tuple[str, str, str], dict] = {}
    unpriced: dict[tuple[str, str, str], int] = defaultdict(int)

    for f in layout.furniture:
        if f.category == "mullion":  # glazing framing, not a product line
            continue
        k = _key(f)
        if f.list_price and f.list_price > 0:  # a $0 CET spec means "no standalone price", not free
            line = priced.setdefault(
                k,
                {
                    "brand": f.brand or "—",
                    "model": f.model or "—",
                    "description": f.block_name or "—",
                    "category": f.category,
                    "qty": 0,
                    "unit_price": round(f.list_price, 2),
                },
            )
            line["qty"] += 1
        else:
            unpriced[k] += 1

    lines = [
        {**line, "line_total": round(line["unit_price"] * line["qty"], 2)}
        for line in priced.values()
    ]
    lines.sort(key=lambda line: line["line_total"], reverse=True)

    return {
        "lines": lines,
        "total": round(sum(line["line_total"] for line in lines), 2),
        "priced_items": sum(line["qty"] for line in lines),
        "unpriced_items": sum(unpriced.values()),
        "currency": "USD",  # Steelcase/CET list prices are USD; India catalog pricing is a later track
    }
