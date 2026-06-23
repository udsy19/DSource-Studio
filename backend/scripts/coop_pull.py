"""CLI: pull / parse a cooperative-contract furniture pricing PDF into discount-off-list bands.

Usage (from backend/, with the venv active):
    # Parse the already-downloaded MillerKnoll NASPO/WA-DES contract:
    python -m scripts.coop_pull --pdf data/coop/millerknoll_wa_pricing.pdf

    # Download (the public WA DES MillerKnoll price list) then parse:
    python -m scripts.coop_pull --download --pdf data/coop/millerknoll_wa_pricing.pdf

    # Emit JSON (all bands) and the per-manufacturer-code rollup for the Discount table:
    python -m scripts.coop_pull --pdf data/coop/millerknoll_wa_pricing.pdf --json
    python -m scripts.coop_pull --pdf data/coop/millerknoll_wa_pricing.pdf --rollup

This is a thin wrapper over app.coop.parser. It does NOT write to the DB — it prints the
extracted bands and the per-manufacturer-code rollup the integrator can apply to the
Discount(manufacturer_code, band) table.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# Make `app` importable when run as a plain script as well as `python -m scripts.coop_pull`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.coop.parser import parse_contract  # noqa: E402

# Public, no-login WA State DES MillerKnoll (NASPO ValuePoint) furniture price list.
DEFAULT_URL = "https://apps.des.wa.gov/contracting/MillerKnoll%20Pricing.pdf"


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as fh:  # noqa: S310
        fh.write(resp.read())
    print(f"[coop_pull] downloaded {dest} ({dest.stat().st_size:,} bytes) from {url}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse a co-op furniture pricing PDF into discount bands.")
    ap.add_argument("--pdf", required=True, help="path to the co-op pricing PDF")
    ap.add_argument("--url", default=DEFAULT_URL, help="source URL (also recorded on each band)")
    ap.add_argument("--contract", default=None, help="human label for the source contract")
    ap.add_argument("--download", action="store_true", help="download --url to --pdf first")
    ap.add_argument("--json", action="store_true", help="print all bands as JSON")
    ap.add_argument("--rollup", action="store_true", help="print per-manufacturer-code rollup")
    args = ap.parse_args(argv)

    pdf = Path(args.pdf)
    if args.download:
        download(args.url, pdf)
    if not pdf.exists():
        ap.error(f"PDF not found: {pdf} (use --download to fetch it)")

    kwargs = {"source_url": args.url}
    if args.contract:
        kwargs["source_contract"] = args.contract
    parsed = parse_contract(str(pdf), **kwargs)

    if args.json:
        print(json.dumps([b.as_dict() for b in parsed.bands], indent=2))
        return 0

    rollup = parsed.by_manufacturer_code()
    if args.rollup:
        print(json.dumps(rollup, indent=2))
        return 0

    # Default: a readable summary.
    print(f"Title:    {parsed.title}")
    print(f"Contract: {parsed.source_contract}")
    print(f"Source:   {parsed.source_url}")
    print(f"Bands:    {len(parsed.bands)}")
    if parsed.warnings:
        print("Warnings:")
        for w in parsed.warnings:
            print(f"  - {w}")
    print("\nSample bands (first 12, '% off list'):")
    for b in parsed.bands[:12]:
        code = b.manufacturer_code or "—"
        line = b.product_line or "(brand-wide)"
        tiers = "/".join(f"{t * 100:.2f}%" for t in b.tier_discounts)
        print(f"  [{code:>3}] {b.manufacturer:<14} {line:<28} {tiers}")
    print("\nPer-manufacturer-code rollup (median Tier-1 band → Discount table):")
    for code, band in sorted(rollup.items()):
        print(f"  {code}: band={band}  ({band * 100:.2f}% off list)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
