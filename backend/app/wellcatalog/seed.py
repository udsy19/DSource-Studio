"""Seed ProductCert rows for the synthetic dealer catalog.

!!! ILLUSTRATIVE PLACEHOLDERS — NOT REAL CERTIFICATION DATA !!!
Every value below is hand-authored to be PLAUSIBLE but is clearly SYNTHETIC. The numbers
loosely echo well-known real product profiles (e.g. MillerKnoll task seating tends to carry
strong material-health / low-VOC stories; Interface carpet tile is the canonical
LEED / low-VOC / recycled-content flooring example) but NONE of these are sourced from an
actual WELL scorecard, EPD, or lead-time feed. Wiring real WELL/EPD/lead-time data in is
exactly the catalog-data problem this layer is meant to expose.

US / USD context. lead_time_days are typical-build placeholders; embodied_carbon_kg are
order-of-magnitude per-unit guesses (kgCO2e); recycled_pct is 0–100.
"""

from sqlalchemy.orm import Session

from .models import ProductCert

# (sku, well_rating, lead_time_days, low_voc, recycled_pct, embodied_carbon_kg)
# Keyed to the SKUs in data/synthetic/dealer_catalog.sif (+ AER1 / PX100 if present).
SYNTHETIC_CERTS: list[tuple[str, str, int, bool, float, float]] = [
    # --- Steelcase (SC) ---
    ("SC-LEAP-V2",      "A+", 21, True,  33.0, 72.0),   # task seating, strong material health
    ("SC-GESTURE",      "A",  28, True,  30.0, 78.0),
    ("SC-OLOGY-RECT",   "A",  35, True,  25.0, 140.0),  # height-adjust desk
    ("SC-FLEX-PERCH",   "B",  18, False, 15.0, 40.0),   # perch stool, no rating-grade story
    ("SC-VERB-CONF-8",  "B",  42, True,  20.0, 210.0),  # conference table
    # --- Herman Miller / MillerKnoll (HMI) ---
    ("HM-AERON-B",      "A+", 14, True,  39.0, 65.0),   # flagship task seating, short lead
    ("HM-SAYL",         "A",  21, True,  41.0, 52.0),
    ("HM-RENEW-SS",     "A",  30, True,  22.0, 135.0),  # sit-to-stand desk
    ("HM-EVERYWHERE-6", "B",  25, True,  18.0, 120.0),  # conference table
    # --- Haworth (HAW) ---
    ("HW-COMPOSE-BENCH","A",  45, True,  28.0, 160.0),  # benching per seat
    ("HW-FERN-LOUNGE",  "B",  38, False, 12.0, 95.0),   # lounge, lower material story
    # --- Knoll (KNL) ---
    ("KN-ANTENNA-BENCH","B",  40, False, 16.0, 170.0),
    ("KN-RILEY-OTTOMAN","none", 33, False, 8.0, 55.0),  # no rating on file
    # --- Humanscale (HUM) ---
    ("HS-FREEDOM",      "A+", 19, True,  35.0, 60.0),   # task seating
    ("HS-FLOAT-TABLE",  "A",  27, True,  24.0, 110.0),  # standing table
    # --- Framery (FRM) pods ---
    ("FR-FRAMERY-O",    "A",  56, True,  21.0, 900.0),  # phone booth, long lead, big footprint
    ("FR-FRAMERY-Q",    "B",  70, True,  19.0, 2400.0), # 4-person pod
    # --- Interface (INT) flooring — canonical low-VOC / recycled story ---
    ("IF-WW890-CT",     "A+", 24, True,  68.0, 6.0),    # carpet tile, high recycled content
    # --- Optional extras if these SKUs ever land in the catalog ---
    ("AER1",            "A+", 14, True,  39.0, 65.0),   # alias-style Aeron placeholder
    ("PX100",           "A",  30, True,  20.0, 130.0),  # generic desk placeholder
]


def seed_certs(db: Session) -> int:
    """Idempotently upsert the synthetic certs. Returns rows added."""
    added = 0
    for sku, rating, lead, low_voc, recycled, carbon in SYNTHETIC_CERTS:
        existing = db.query(ProductCert).filter(ProductCert.sku == sku).one_or_none()
        if existing is None:
            db.add(ProductCert(
                sku=sku, well_rating=rating, lead_time_days=lead,
                low_voc=low_voc, recycled_pct=recycled, embodied_carbon_kg=carbon,
            ))
            added += 1
    db.commit()
    return added
