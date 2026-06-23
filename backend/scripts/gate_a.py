"""Gate A — the Phase 0 validation proof.

Ingest a known project's SIF export, compute our budgetary total, and compare it to the
dealer's actual quote for that project. Passes if within the configured tolerance.

This is the falsifiable test of the whole data thesis: if our number tracks the dealer's
real quote on their own historical project, the ingest + pricing spine is sound.

Run:  python -m scripts.gate_a            (uses synthetic known_quote.json)
      python -m scripts.gate_a --print    (just print our computed total)
"""

import json
import sys
from pathlib import Path

# allow running as `python scripts/gate_a.py` too
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.ingest import service  # noqa: E402
from app.ingest.sif import parse_sif  # noqa: E402
from app.pricing.engine import compute_quote  # noqa: E402
from app.seed import seed  # noqa: E402

SYNTHETIC = Path(__file__).resolve().parent.parent / "data" / "synthetic"
TOLERANCE = 0.15


def compute_project_total(project_sif_path: Path) -> tuple[float, object]:
    """Build an in-memory DB, seed config + catalog, ingest the project, compute the quote."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        seed(db)
        service.upsert_catalog(db, parse_sif((SYNTHETIC / "dealer_catalog.sif").read_text()), "sif")
        project = service.build_project(db, parse_sif(project_sif_path.read_text()),
                                        name="Gate A", source="sif")
        inputs, rates = service.quote_inputs_for_project(db, project)
        return compute_quote(inputs, rates).total, compute_quote(inputs, rates)
    finally:
        db.close()


def main() -> int:
    project_sif = SYNTHETIC / "project_alpha.sif"
    our_total, quote = compute_project_total(project_sif)

    if "--print" in sys.argv:
        print(f"net_merchandise = {quote.net_merchandise:,.2f}")
        print(f"install         = {quote.install:,.2f}")
        print(f"freight         = {quote.freight:,.2f}")
        print(f"tax             = {quote.tax:,.2f}")
        print(f"OUR BUDGETARY TOTAL = {our_total:,.2f}")
        return 0

    target_path = SYNTHETIC / "known_quote.json"
    target = json.loads(target_path.read_text())
    dealer_total = float(target["dealer_quote_total"])

    delta = abs(our_total - dealer_total) / dealer_total
    status = "PASS" if delta <= TOLERANCE else "FAIL"
    print(f"Project           : {target.get('project')}")
    print(f"Dealer real quote : {dealer_total:,.2f}")
    print(f"Our budgetary     : {our_total:,.2f}")
    print(f"Delta             : {delta * 100:.1f}%  (tolerance {TOLERANCE * 100:.0f}%)")
    print(f"GATE A            : {status}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
