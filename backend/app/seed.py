"""Seed the dealer's standing config: manufacturers, discount bands, dealer rates.

The catalog itself is loaded by ingesting the synthetic SIF export (see main.py) — that
exercises the real data path rather than hand-seeding products.
"""

from sqlalchemy.orm import Session

from .models import DealerSettings, Discount, Manufacturer

# Discount bands are "% off list". The HMI band 0.505 is the REAL cooperative band: the median
# Tier-1 discount across Herman Miller lines in the NASPO ValuePoint / WA-DES MillerKnoll
# Participating Addendum (contract #21422, Attachment C), parsed from
# data/coop/millerknoll_wa_pricing.pdf. main.bootstrap() re-asserts it via realdata.apply_coop_hmi_band.
MANUFACTURERS = [
    ("HMI", "Herman Miller", 0.505),  # REAL NASPO/WA-DES MillerKnoll co-op band
    ("SC", "Steelcase", 0.48),
    ("HAW", "Haworth", 0.47),
    ("KNL", "Knoll", 0.46),
    ("HUM", "Humanscale", 0.45),
    ("INT", "Interface", 0.42),
    ("FRM", "Framery", 0.40),
]


def seed(db: Session) -> None:
    for code, name, band in MANUFACTURERS:
        if db.get(Manufacturer, code) is None:
            db.add(Manufacturer(code=code, name=name))
        if db.get(Discount, code) is None:
            db.add(Discount(manufacturer_code=code, band=band))
    if db.get(DealerSettings, 1) is None:
        db.add(DealerSettings(
            id=1, name="Pilot Dealer (synthetic)",
            default_discount=0.40, install_rate=0.15, freight_rate=0.03, tax_rate=0.0863,
        ))
    db.commit()
