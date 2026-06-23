#!/usr/bin/env python
"""CLI: pull a GSA Advantage furniture contract's price list and print parsed rows.

Usage:
    python scripts/gsa_pull.py GS27F0014V               # live fetch + parse
    python scripts/gsa_pull.py GS27F0014V --no-fetch    # parse cached HTML only
    python scripts/gsa_pull.py GS27F0014V --json        # emit JSON rows
    python scripts/gsa_pull.py --list                   # list known furniture contracts

Furniture is MAS SIN 33721. Prices are the GOVERNMENT NET price (gsa_net), not a
separate manufacturer list price.

Run from the backend/ directory (so `app` is importable):
    cd backend && python scripts/gsa_pull.py GS27F0014V
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make `app` importable when run as a script from backend/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.gsa.parser import parse_price_list  # noqa: E402
from app.gsa.scraper import (  # noqa: E402
    GsaScraperError,
    fetch_price_list,
    load_cached,
)

KNOWN = {
    "GS27F0014V": "Steelcase Inc.",
    "47QSMS24D0034": "Steelcase Inc.",
    "GS03F036DA": "MillerKnoll / Herman Miller",
    "GS03F057DA": "Haworth Inc.",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pull a GSA Advantage furniture price list.")
    ap.add_argument("contract", nargs="?", help="GSA contract number (e.g. GS27F0014V)")
    ap.add_argument("--no-fetch", action="store_true",
                    help="parse cached HTML under data/gsa/ instead of live-fetching")
    ap.add_argument("--no-save", action="store_true", help="do not cache fetched HTML")
    ap.add_argument("--json", action="store_true", help="emit JSON rows")
    ap.add_argument("--list", action="store_true", help="list known furniture contracts")
    args = ap.parse_args(argv)

    if args.list:
        print("Known furniture contractors (MAS SIN 33721):")
        for c, name in KNOWN.items():
            print(f"  {c:16s} {name}")
        return 0

    if not args.contract:
        ap.error("contract number is required (or use --list)")

    try:
        if args.no_fetch:
            fetch = load_cached(args.contract)
        else:
            fetch = fetch_price_list(args.contract, save=not args.no_save)
    except GsaScraperError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parsed = parse_price_list(fetch.html, contract=args.contract,
                              manufacturer=KNOWN.get(args.contract.upper()))
    rows = [r.to_catalog_dict() for r in parsed.records]

    if args.json:
        print(json.dumps({
            "contract": parsed.contract,
            "manufacturer": parsed.manufacturer,
            "price_kind": "gsa_net",
            "fetch_method": fetch.method,
            "fetch_ok": fetch.ok,
            "looks_blocked": fetch.looks_blocked,
            "count": len(rows),
            "rows": rows,
            "warnings": parsed.warnings + fetch.warnings,
        }, indent=2))
        return 0

    print(f"Contract:     {parsed.contract or args.contract}")
    print(f"Manufacturer: {parsed.manufacturer or '(unknown)'}")
    print(f"Fetch:        method={fetch.method} bytes={fetch.length} "
          f"ok={fetch.ok} blocked={fetch.looks_blocked}")
    if fetch.note:
        print(f"Note:         {fetch.note}")
    for w in parsed.warnings + fetch.warnings:
        print(f"  ! {w}")
    print(f"\nParsed {len(rows)} rows (price_kind=gsa_net):")
    print(f"  {'MFR':8s} {'SKU':22s} {'GSA_NET':>10s}  NAME")
    for r in rows:
        print(f"  {r['manufacturer_code']:8s} {r['sku'][:22]:22s} "
              f"{r['list_price']:>10.2f}  {r['name'][:46]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
