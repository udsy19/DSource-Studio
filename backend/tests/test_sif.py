from app.ingest.sif import parse_sif, write_sif

SAMPLE = """ST=Test Project
SF=XREF-1

MC=SC
PN=SC-LEAP-V2
PD=Leap V2 Task Chair
QT=28
PL=1037.00
ON=BUZZ2
OD=3D Knit Back - Graphite
ON=BASE
OD=Polished Aluminum Base

MC=FRM
PN=FR-FRAMERY-O
PD=Framery O Phone Booth
QT=2
PL=11900.00
S%=38.0
"""


def test_parse_header_and_items():
    sif = parse_sif(SAMPLE)
    assert sif.title == "Test Project"
    assert sif.source == "XREF-1"
    assert len(sif.items) == 2


def test_parse_fields_and_types():
    sif = parse_sif(SAMPLE)
    leap = sif.items[0]
    assert leap.manufacturer_code == "SC"
    assert leap.part_number == "SC-LEAP-V2"
    assert leap.quantity == 28.0
    assert leap.list_price == 1037.0
    assert leap.discount_pct is None
    # two ON/OD option pairs parsed correctly
    assert len(leap.options) == 2
    assert leap.options[0].number == "BUZZ2"
    assert leap.options[0].description == "3D Knit Back - Graphite"
    assert leap.options[1].number == "BASE"


def test_line_level_discount():
    sif = parse_sif(SAMPLE)
    booth = sif.items[1]
    assert booth.discount_pct == 38.0


def test_messy_values_and_currency():
    sif = parse_sif("MC=HMI\nPN=X\nQT=10\nPL=$1,795.00\n")
    assert sif.items[0].list_price == 1795.0
    assert sif.items[0].quantity == 10.0


def test_round_trip():
    sif = parse_sif(SAMPLE)
    again = parse_sif(write_sif(sif))
    assert len(again.items) == len(sif.items)
    assert again.items[0].part_number == "SC-LEAP-V2"
    assert again.items[0].quantity == 28.0
    assert again.items[1].discount_pct == 38.0
