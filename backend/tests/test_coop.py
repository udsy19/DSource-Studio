"""Co-op discount-band parser tests — run against the REAL MillerKnoll NASPO price list.

millerknoll_wa_pricing.pdf is downloaded into data/coop/ (the MillerKnoll Product & Price
List / "Attachment C – Pricing Information" from the NASPO ValuePoint office-furniture master
agreement, as adopted in Washington State DES contract #21422):
    https://apps.des.wa.gov/contracting/MillerKnoll%20Pricing.pdf

If absent the tests skip (so the suite still runs), but locally they validate extraction
against the real published "% off list" discount table. The asserted values below are the
actual numbers printed in that contract PDF.
"""

from pathlib import Path

import pytest

from app.coop.parser import manufacturer_code, parse_contract

PDF = Path(__file__).resolve().parent.parent / "data" / "coop" / "millerknoll_wa_pricing.pdf"
pytestmark = pytest.mark.skipif(not PDF.exists(), reason="real co-op pricing PDF not downloaded")


def _bands_by_line(parsed):
    """Index bands by (manufacturer, product_line) for assertions; later rows win on dup."""
    return {(b.manufacturer, b.product_line): b for b in parsed.bands}


def test_title_and_volume():
    parsed = parse_contract(str(PDF))
    assert "Pricing Information" in parsed.title
    # The contract lists ~244 product-line discount rows across 5 categories.
    assert len(parsed.bands) >= 240
    assert not parsed.warnings  # every row carried an identifiable brand


def test_real_herman_miller_discounts():
    parsed = parse_contract(str(PDF))
    idx = _bands_by_line(parsed)

    # REAL ground-truth "% off list" tiers from the MillerKnoll NASPO/WA-DES contract.
    aeron = idx[("Herman Miller", "Aeron")]
    assert aeron.manufacturer_code == "HMI"
    assert aeron.discount_pct == 0.5075                       # Tier 1 (<= $50k) = 50.75%
    assert aeron.tier_discounts == [0.5075, 0.51, 0.5175]     # 50.75 / 51.00 / 51.75
    assert aeron.category == "Office Seating and Accessories"

    assert idx[("Herman Miller", "Cosm")].tier_discounts == [0.505, 0.5075, 0.525]
    assert idx[("Herman Miller", "Embody")].discount_pct == 0.485
    # Eames Aluminum Group is flat across tiers at 46.00%, with its collection captured.
    eames = idx[("Herman Miller", "Eames Chairs")]
    assert eames.collection == "Eames Aluminum Group"
    assert eames.tier_discounts == [0.46, 0.46, 0.46]


def test_real_knoll_discounts():
    parsed = parse_contract(str(PDF))
    idx = _bands_by_line(parsed)
    gen = idx[("Knoll", "Generation Task Chair")]
    assert gen.manufacturer_code == "KNL"
    assert gen.tier_discounts == [0.59, 0.5925, 0.595]        # 59.00 / 59.25 / 59.50


def test_manufacturer_code_mapping():
    # Names map to the project's manufacturer CODES (app/seed.py) where known.
    assert manufacturer_code("Herman Miller") == "HMI"
    assert manufacturer_code("Knoll") == "KNL"
    assert manufacturer_code("Steelcase") == "SC"
    assert manufacturer_code("Haworth") == "HAW"
    assert manufacturer_code("Humanscale") == "HUM"
    # Brands the project doesn't seed are kept raw with code=None (not dropped).
    assert manufacturer_code("Geiger") is None


def test_per_manufacturer_rollup_for_discount_table():
    parsed = parse_contract(str(PDF))
    rollup = parsed.by_manufacturer_code()
    # Only known codes appear; each is a sane "% off list" in (0,1).
    assert set(rollup) == {"HMI", "KNL"}
    for code, band in rollup.items():
        assert 0.0 < band < 1.0
    # Median Tier-1 band lands in the documented Herman Miller / Knoll ranges.
    assert 0.40 <= rollup["HMI"] <= 0.70
    assert 0.40 <= rollup["KNL"] <= 0.70
