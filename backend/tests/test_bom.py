"""Priced BOM aggregation from an extracted layout."""

from app.ingestion.schema import ExtractedLayout, FurnitureItem
from app.takeoff.bom import build_bom


def _item(model, price, cat="chair"):
    return FurnitureItem(category=cat, block_name=f"{cat} {model}", brand="Steelcase",
                         model=model, x=0, y=0, w=2, h=2, rotation=0, list_price=price)


def test_bom_aggregates_by_sku_and_excludes_unpriced():
    layout = ExtractedLayout(
        source="cad", units="ft", bounds=[0, 0, 100, 100],
        furniture=[
            _item("442A40", 2569.0),
            _item("442A40", 2569.0),          # same SKU -> qty 2 on one line
            _item("OBBORDER05", 10387.0, "table"),
            FurnitureItem(category="other", block_name="*C9", brand=None, model=None,
                          x=0, y=0, w=1, h=1, rotation=0, list_price=None),  # unpriced
        ],
    )
    bom = build_bom(layout)
    assert bom["total"] == round(2 * 2569.0 + 10387.0, 2)
    assert bom["priced_items"] == 3 and bom["unpriced_items"] == 1
    gesture = next(l for l in bom["lines"] if l["model"] == "442A40")
    assert gesture["qty"] == 2 and gesture["line_total"] == round(2 * 2569.0, 2)
    # sorted by line total desc -> the table leads
    assert bom["lines"][0]["model"] == "OBBORDER05"
