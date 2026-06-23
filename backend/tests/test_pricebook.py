"""Price-book parser tests — run against the REAL Herman Miller Aeron price book.

PB_AEN.pdf is downloaded into data/pricebooks/ (see README). If absent, these tests skip
so the suite still runs, but locally they validate extraction against real published data.
The parser deliberately emits only confidently-priced products and flags the rest, so we
assert real ground-truth prices rather than full coverage of every quirky configurator.
"""

from pathlib import Path

import pytest

from app.pricebook.parser import parse_book

PB = Path(__file__).resolve().parent.parent / "data" / "pricebooks" / "PB_AEN.pdf"
pytestmark = pytest.mark.skipif(not PB.exists(), reason="real price book PDF not downloaded")


def test_title_and_real_prices():
    book = parse_book(str(PB))
    assert "Aeron" in book.title
    prices = {p.base_code: p.starting_config()[1] for p in book.products}
    # Real ground-truth from the 6/26 Aeron book: both AER1 and AER2 open with a
    # "Step 2. Size  A a size +$1726" base, so each starts at $1726 (verified in the PDF).
    assert prices.get("AER1") == 1726.0
    assert prices.get("AER2") == 1726.0
    # Hardened parser also extracts the stool/ESD variants (AER7x, AERE1) — several products.
    assert len(book.products) >= 5


def test_emits_only_confident_products_and_flags_rest():
    book = parse_book(str(PB))
    # Every emitted product is real and priced.
    for p in book.products:
        part_number, price = p.starting_config()
        assert price > 0
        assert part_number.startswith(p.base_code)
        assert len(p.steps) <= 16
    # Products it could not confidently price are surfaced, not silently dropped or mispriced.
    assert any("review" in w.lower() for w in book.warnings)
