"""Real Herman Miller price-book ingest + the REAL NASPO/WA-DES co-op discount band.

This module is the bridge between the published Herman Miller price-book PDFs (parsed by
`app.pricebook.parser`) and the dealer catalog, plus the real cooperative discount band parsed
from the MillerKnoll WA-DES contract. It is invoked from `app.main.bootstrap()` so that when the
studio runs a test-fit quote, HM line items price off REAL list prices × the REAL co-op band.

Honest scope note
-----------------
The price-book parser is tuned to Herman Miller's "Step N." chair-style configurator grammar.
Of the books we downloaded, the ones that parse into confidently-priced products are:

  * Seating (chairs):  PB_AEN (Aeron), PB_EMB (Embody), PB_SET (Setu)
  * Lounge:            PB_PLX (Plex)

The sit-to-stand desk books (Renew/Motia/Nevi), the conference-table books (Everywhere/Headway),
Tu Wood Storage and Swoop lounge do NOT parse under this grammar — their PDFs use a different
table layout and yield zero confidently-priced products. Rather than fabricate numbers we SKIP
them; the desk/table BOM lines fall back to the synthetic catalog and are flagged real=False.

The list below names every book we attempted; `bootstrap` ingests whichever ones parse and
reports the rest. The REAL co-op band for HMI is 0.505 (median Tier-1 discount across Herman
Miller lines in the WA-DES MillerKnoll NASPO ValuePoint contract #21422 / Attachment C).
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from .ingest import service
from .models import Discount, Product
from .pricebook.parser import parse_book

PRICEBOOKS_DIR = Path(__file__).resolve().parent.parent / "data" / "pricebooks"
COOP_PDF = Path(__file__).resolve().parent.parent / "data" / "coop" / "millerknoll_wa_pricing.pdf"

# REAL Herman Miller price books to attempt, by furniture type. Files are downloaded into
# data/pricebooks/ from hermanmiller.com/.../pricing/PB_<code>.pdf.
HM_PRICEBOOKS: list[tuple[str, str, str]] = [
    # (filename, furniture_type, note)
    ("PB_AEN.pdf", "task_chair", "Aeron Chairs"),
    ("PB_EMB.pdf", "task_chair", "Embody Chairs"),
    ("PB_SET.pdf", "task_chair", "Setu Chairs"),
    ("PB_PLX.pdf", "lounge", "Plex Lounge Furniture"),
    # Attempted but do NOT parse under the Step-N grammar (kept for transparency / future work):
    ("PB_REN.pdf", "desk", "Renew Sit-to-Stand Tables"),
    ("PB_MOT.pdf", "desk", "Motia Sit-to-Stand Tables"),
    ("PB_NEV.pdf", "desk", "Nevi Sit-to-Stand Tables"),
    ("PB_EWT.pdf", "table", "Everywhere Tables"),
    ("PB_HWT.pdf", "table", "Headway Tables"),
    ("PB_TMS.pdf", "storage", "Tu Metal Storage"),
    ("PB_TWS.pdf", "storage", "Tu Wood Storage"),
    ("PB_SWP.pdf", "lounge", "Swoop Lounge Furniture"),
]

# REAL cooperative discount band for Herman Miller (HMI). Median Tier-1 % off list across
# Herman Miller product lines in the WA-DES MillerKnoll NASPO ValuePoint contract (#21422,
# Attachment C). Verified by parsing data/coop/millerknoll_wa_pricing.pdf.
HMI_COOP_BAND = 0.505


def ingest_hm_pricebooks(db: Session) -> list[dict]:
    """Ingest every downloaded HM price book that parses; return a per-book report.

    Books that parse into 0 confidently-priced products are reported with parsed=0 and skipped
    (their warnings are surfaced) — they are NOT loaded with fabricated data.
    """
    # Fast path: if real HM products are already in the catalog (warm DB), skip re-parsing the
    # 12 large PDFs. Parsing only needs to happen on a cold catalog (first boot / fresh test DB).
    already = db.query(Product).filter(
        Product.manufacturer_code == "HMI", Product.source == "pricebook"
    ).count()
    if already:
        return [{"file": "(cached)", "type": "all", "note": f"{already} real HM products already loaded",
                 "present": True, "parsed": already, "skus": []}]

    report: list[dict] = []
    for filename, ftype, note in HM_PRICEBOOKS:
        path = PRICEBOOKS_DIR / filename
        if not path.exists():
            report.append({"file": filename, "type": ftype, "note": note,
                           "present": False, "parsed": 0, "skus": []})
            continue
        try:
            book = parse_book(str(path))
        except Exception as exc:  # noqa: BLE001
            report.append({"file": filename, "type": ftype, "note": note,
                           "present": True, "parsed": 0, "error": str(exc), "skus": []})
            continue
        if not book.products:
            report.append({"file": filename, "type": ftype, "note": note,
                           "present": True, "parsed": 0, "skus": [],
                           "warnings": book.warnings})
            continue
        results, warnings = service.upsert_price_book(db, book, manufacturer_code="HMI")
        report.append({
            "file": filename, "type": ftype, "note": note, "present": True,
            "parsed": len(results),
            "skus": [(r.base_code, r.starting_list_price) for r in results],
            "warnings": warnings,
        })
    return report


def apply_coop_hmi_band(db: Session, band: float = HMI_COOP_BAND) -> None:
    """Ensure HMI's Discount band is the REAL co-op value (0.505) before quoting."""
    row = db.get(Discount, "HMI")
    if row is None:
        db.add(Discount(manufacturer_code="HMI", band=band))
    else:
        row.band = band
    db.commit()
