"""Tests for the GSA Advantage furniture connector — PARSER focused, no network.

The parser is exercised against a saved HTML fixture that mirrors the real GSA Advantage
"Authorized FSS Schedule Price List" product-table layout for SIN 33721 furniture
(MFR PART # / Description / GSA Price). See data/gsa/SAMPLE_furniture_online.htm for the
provenance note: every live ref_text page we fetched redirects to a Terms & Conditions PDF,
so the line-item SKU table is the structured-catalog/HTML-price-list format.

No test here touches the network.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.gsa.parser import GsaPriceRecord, parse_price_list
from app.gsa.scraper import price_list_url

DATA = Path(__file__).resolve().parent.parent / "data" / "gsa"
FIXTURE = DATA / "SAMPLE_furniture_online.htm"


@pytest.fixture
def sample_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


# ---- URL building ------------------------------------------------------------------

def test_price_list_url():
    assert price_list_url("gs27f0014v") == (
        "https://www.gsaadvantage.gov/ref_text/GS27F0014V/GS27F0014V_online.htm"
    )


# ---- HTML table parsing ------------------------------------------------------------

def test_parse_finds_all_rows(sample_html):
    result = parse_price_list(sample_html, contract="GS27F0014V")
    assert len(result) == 5
    assert result.contract == "GS27F0014V"


def test_parse_maps_to_catalog_shape(sample_html):
    result = parse_price_list(sample_html, contract="GS27F0014V")
    leap = next(r for r in result.records if r.sku == "SCS-LEAP-V2")
    # sku = manufacturer part number
    assert leap.sku == "SCS-LEAP-V2"
    # name = short description
    assert "Leap V2" in leap.name
    # gsa_price = government NET price, parsed from "$1,012.40"
    assert leap.gsa_price == pytest.approx(1012.40)
    # manufacturer_code derived & <=8 chars (Product.manufacturer_code is String(8))
    assert leap.manufacturer_code
    assert len(leap.manufacturer_code) <= 8


def test_prices_parsed_with_thousands_separators(sample_html):
    result = parse_price_list(sample_html, contract="GS27F0014V")
    by_sku = {r.sku: r.gsa_price for r in result.records}
    assert by_sku["435A00"] == pytest.approx(345.67)
    assert by_sku["OLOGY-2430"] == pytest.approx(1489.00)
    assert by_sku["FYI-CONF-96"] == pytest.approx(2755.25)
    assert by_sku["UNIVPED-BBF"] == pytest.approx(418.90)


def test_to_catalog_dict_uses_gsa_net_as_price(sample_html):
    result = parse_price_list(sample_html, contract="GS27F0014V")
    rec = next(r for r in result.records if r.sku == "OLOGY-2430")
    d = rec.to_catalog_dict()
    assert d["manufacturer_code"] == rec.manufacturer_code
    assert d["sku"] == "OLOGY-2430"
    assert d["name"] == rec.name
    # catalog list_price slot is fed from the GSA net price, explicitly labeled
    assert d["list_price"] == pytest.approx(1489.00)
    assert d["price_kind"] == "gsa_net"
    assert d["price_uom"] == "ea"  # from the U/I column
    assert d["source"] == "gsa"


def test_uom_captured(sample_html):
    result = parse_price_list(sample_html, contract="GS27F0014V")
    assert all((r.uom or "").upper() == "EA" for r in result.records)


def test_dedupe_on_mfr_and_sku():
    html = """
    <table>
      <tr><th>Mfr Part No</th><th>Description</th><th>GSA Price</th></tr>
      <tr><td>ABC-1</td><td>Chair</td><td>$100.00</td></tr>
      <tr><td>ABC-1</td><td>Chair dup</td><td>$100.00</td></tr>
      <tr><td>ABC-2</td><td>Desk</td><td>$200.00</td></tr>
    </table>
    """
    result = parse_price_list(html, manufacturer="Acme")
    assert len(result) == 2
    assert {r.sku for r in result.records} == {"ABC-1", "ABC-2"}


# ---- header-variant tolerance ------------------------------------------------------

@pytest.mark.parametrize("part_header,price_header", [
    ("Manufacturer Part Number", "GSA Price"),
    ("Model Number", "Net Price"),
    ("Item #", "Unit Price"),
    ("Part No", "Government Net Price"),
])
def test_header_synonyms(part_header, price_header):
    html = f"""
    <table>
      <tr><th>{part_header}</th><th>Description</th><th>{price_header}</th></tr>
      <tr><td>X-9</td><td>Lounge Sofa</td><td>$1,250.00</td></tr>
    </table>
    """
    result = parse_price_list(html, manufacturer="Haworth")
    assert len(result) == 1
    assert result.records[0].sku == "X-9"
    assert result.records[0].gsa_price == pytest.approx(1250.00)


# ---- plain-text fallback (I-FSS-600 text template variant) -------------------------

def test_plain_text_fallback():
    text = (
        "Authorized Federal Supply Schedule Price List\n"
        "Contract GS-03F-057DA\n"
        "PART-100 Mesh task chair with arms $345.67\n"
        "PART-200 Sit-stand desk 30x60 $1,489.00\n"
        "this is not a product line and should be ignored\n"
    )
    result = parse_price_list(text, contract="GS03F057DA")
    skus = {r.sku for r in result.records}
    assert "PART-100" in skus
    assert "PART-200" in skus
    prices = {r.sku: r.gsa_price for r in result.records}
    assert prices["PART-200"] == pytest.approx(1489.00)


# ---- blocked / empty input ---------------------------------------------------------

def test_empty_or_blocked_returns_no_rows_with_warning():
    result = parse_price_list("")
    assert len(result) == 0
    assert any("no price rows" in w for w in result.warnings)


def test_meta_refresh_redirect_page_yields_no_rows_but_warns():
    # This is exactly what the live ref_text pages return (real captured shape).
    html = (
        '<html><head><meta http-equiv="refresh" '
        'content="0;url=GS27F0014V_TERMS.PDF"><title></title></head><body></body></html>'
    )
    result = parse_price_list(html, contract="GS27F0014V")
    assert len(result) == 0
    assert result.warnings


# ---- record dataclass sanity -------------------------------------------------------

def test_record_dataclass_defaults():
    r = GsaPriceRecord(manufacturer_code="STEELCAS", sku="X", name="Y", gsa_price=10.0)
    assert r.source == "gsa"
    assert r.list_price is None
    assert r.to_catalog_dict()["list_price"] == pytest.approx(10.0)
