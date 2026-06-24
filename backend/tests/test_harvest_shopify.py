from app.harvest.shopify import parse_products_json

# Mirrors real Shopify /products.json shapes seen on Indian brands, including the rifeindia
# B2B case (price 0.00 / null sku) that must NOT become a fake price.
PAYLOAD = {
    "products": [
        {
            "title": "Aria Ergonomic Office Chair",
            "handle": "aria-office-chair",
            "product_type": "Office Chair",
            "vendor": "Nilkamal",
            "tags": ["Material_Mesh", "Colour_Black", "Finish_Matte"],
            "images": [{"src": "https://cdn.shopify.com/aria-1.jpg"},
                       {"src": "https://cdn.shopify.com/aria-2.jpg"}],
            "variants": [{"sku": "NK-ARIA-01", "price": "8499.00", "available": True}],
        },
        {
            "title": "Pro Monitor Arm",
            "handle": "pro-monitor-arm",
            "product_type": "Accessory",
            "vendor": "Rife",
            "tags": [],
            "images": [{"src": "https://cdn.shopify.com/arm-1.jpg"}],
            "variants": [{"sku": None, "price": "0.00", "available": False}],
        },
        {
            "title": "Teak Side Table",
            "handle": "teak-side-table",
            "product_type": "Table",
            "vendor": "TrustBasket",
            "tags": [],
            "images": [],
            "variants": [{"sku": "TB-TEAK-9", "price": "3200", "available": True}],
        },
    ]
}


def test_parses_all_products():
    products = parse_products_json(PAYLOAD, manufacturer_code="NK", base_url="https://shop.test")
    assert len(products) == 3


def test_full_product_mapping():
    chair = parse_products_json(PAYLOAD, "NK", base_url="https://shop.test")[0]
    assert chair.sku == "NK-ARIA-01"
    assert chair.price_inr == 8499.0
    assert chair.category == "seating"
    assert chair.color == "Black"
    assert chair.finish == "Matte"
    assert chair.material_attrs == {"primary_material": "Mesh"}
    assert chair.url == "https://shop.test/products/aria-office-chair"
    assert chair.typology_tags == ["workplace"]
    assert "gst_rate" in chair.flagged_fields  # GST is always estimated, never sourced


def test_zero_price_and_null_sku_are_flagged_not_faked():
    arm = parse_products_json(PAYLOAD, "RF", base_url="https://shop.test")[1]
    assert arm.price_inr is None  # 0.00 is treated as missing, never stored as a real price
    assert "price_inr" in arm.flagged_fields
    assert arm.sku == "pro-monitor-arm"  # fell back to the handle
    assert "sku" in arm.flagged_fields


def test_prefers_priced_variant_over_zero_sample():
    # Some stores (e.g. wallpaper) list a ₹0 "sample" variant first; take the real-priced one.
    payload = {"products": [{
        "title": "Olive Meadow Wallpaper", "handle": "olive-meadow", "product_type": "Wallpaper",
        "vendor": "Giffywalls", "tags": [], "images": [{"src": "https://cdn/w.jpg"}],
        "variants": [
            {"sku": "GW-SAMPLE", "price": "0.00", "available": True},
            {"sku": "GW-ROLL", "price": "1290.00", "available": True},
        ],
    }]}
    wall = parse_products_json(payload, "GW", base_url="https://shop.test")[0]
    assert wall.price_inr == 1290.0
    assert wall.sku == "GW-ROLL"


def test_missing_images_and_material_are_flagged():
    table = parse_products_json(PAYLOAD, "TB", base_url="https://shop.test")[2]
    assert table.price_inr == 3200.0
    assert "image_urls" in table.flagged_fields
    assert "material" in table.flagged_fields
    assert table.material_attrs == {}
