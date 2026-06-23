"""Cooperative-contract discount-band parser — a REAL-data connector.

Cooperative and state purchasing contracts publish furniture pricing as a "discount off
manufacturer's published list price", typically as a table of (manufacturer, product line,
optional collection) -> percentage discount, often split into volume/price tiers. These
bands let the quote engine compute net from list using the *contract's* real discounts
instead of the dealer's assumed band.

REAL SOURCE used to develop & test this parser
-----------------------------------------------
MillerKnoll, Inc. — NASPO ValuePoint "Office Furniture and Related Services" master
agreement, as adopted by the Washington State DES Participating Addendum (Contract #21422).
Public PDF: "Attachment C – Pricing Information" (NASPO ValuePoint Price List, Aug 2022,
Solicitation #CT22-79).
URL: https://apps.des.wa.gov/contracting/MillerKnoll%20Pricing.pdf

Its layout (the one this parser targets):
    Brand | Product Line(s) Offered | Collection (If applicable) | Tier1% | Tier2% | Tier3%
grouped under "Category #N:" section headers, where the three tiers are volume bands:
    Tier 1 = list spend <= $50k, Tier 2 = $50k-$150k, Tier 3 = over $150k.
Percentages are "% off list" (e.g. Herman Miller Aeron = 50.75% / 51.00% / 51.75%).

We pull these via pdfplumber's table extraction (the grid is clean), collapsing the merged
spacer cells PDF tables leave behind. We capture all three tier discounts but expose the
Tier-1 (entry) discount as the primary `discount_pct` — that is the band that applies to a
typical order before volume tiers kick in, and is the conservative number for budgetary net.

List prices themselves are facts (uncopyrightable, Feist); contract discount percentages are
likewise published terms of a public procurement. We store the facts, not creative layout.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

# Manufacturer NAME -> project manufacturer CODE (see app/seed.py). Brands not in the
# project's seed (Geiger, Nemschoff, naughtone, HAY, Muuto, ...) keep code=None but we still
# emit the raw name so the integrator can decide how to map/seed them.
NAME_TO_CODE: dict[str, str] = {
    "herman miller": "HMI",
    "steelcase": "SC",
    "haworth": "HAW",
    "knoll": "KNL",
    "humanscale": "HUM",
}

_PCT_RE = re.compile(r"^\s*(\d{1,2}(?:\.\d+)?)\s*%\s*$")
_CATEGORY_RE = re.compile(r"Category\s*#?\s*(\d+)\s*:\s*(.+)")
# Brand cell is a short proper name; used to recognise the brand column when collapsing rows.
_KNOWN_BRANDS = {
    "herman miller", "knoll", "geiger", "nemschoff", "naughtone", "hay", "muuto",
    "steelcase", "haworth", "humanscale", "datesweiser", "fully", "design within reach",
    "colebrook bosson saunders", "maharam",
}


def manufacturer_code(name: str) -> str | None:
    """Map a manufacturer/brand NAME to the project's manufacturer CODE, or None if unknown."""
    return NAME_TO_CODE.get((name or "").strip().lower())


@dataclass
class DiscountBand:
    """A single REAL discount-off-list record extracted from a co-op contract."""

    manufacturer: str                 # raw brand name as printed, e.g. "Herman Miller"
    manufacturer_code: str | None     # mapped project code, e.g. "HMI", or None if unknown
    product_line: str                 # e.g. "Aeron"; "" if a brand-wide / un-lined band
    discount_pct: float               # PRIMARY band, off list, as a float (0.5075 == 50.75%)
    collection: str | None = None     # optional sub-collection, e.g. "KnollStudio"
    category: str | None = None       # contract category section, e.g. "Office Seating ..."
    tier_discounts: list[float] = field(default_factory=list)  # all volume tiers, off list
    source_contract: str = ""         # human label of the contract
    source_url: str = ""              # where the PDF came from

    def as_dict(self) -> dict:
        return {
            "manufacturer": self.manufacturer,
            "manufacturer_code": self.manufacturer_code,
            "product_line": self.product_line,
            "collection": self.collection,
            "category": self.category,
            "discount_pct": self.discount_pct,
            "tier_discounts": self.tier_discounts,
            "source_contract": self.source_contract,
            "source_url": self.source_url,
        }


@dataclass
class ParsedCoopContract:
    title: str
    source_contract: str
    source_url: str
    bands: list[DiscountBand] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def by_manufacturer_code(self) -> dict[str, float]:
        """Roll bands up to one representative band per known manufacturer CODE.

        Uses the *median* Tier-1 discount across that manufacturer's product lines — a
        defensible single number for the project's `Discount(manufacturer_code, band)` row,
        which is per-manufacturer not per-line. Lines with unknown codes are excluded.
        """
        buckets: dict[str, list[float]] = {}
        for b in self.bands:
            if b.manufacturer_code:
                buckets.setdefault(b.manufacturer_code, []).append(b.discount_pct)
        out: dict[str, float] = {}
        for code, vals in buckets.items():
            vals = sorted(vals)
            n = len(vals)
            median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
            out[code] = round(median, 4)
        return out


def _pct_to_float(cell: str) -> float | None:
    if not cell:
        return None
    m = _PCT_RE.match(cell)
    if not m:
        return None
    return round(float(m.group(1)) / 100.0, 6)


def _collapse(row: list[str | None]) -> list[str]:
    """PDF table rows are riddled with None / '' spacer cells from merged columns.

    Collapse to the non-empty cells in order, which yields, for a data row:
        [brand, product_line, (collection?), tier1%, tier2%, tier3%]
    """
    return [(c or "").strip() for c in row if c and str(c).strip()]


def _is_header_row(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    return (
        "brand" in joined and ("product line" in joined or "discount" in joined)
    ) or "percentage discount" in joined or "minimum" in joined and "tier" in joined


def parse_contract(
    source: bytes | str,
    source_contract: str = "MillerKnoll NASPO ValuePoint (WA DES #21422) – Attachment C",
    source_url: str = "https://apps.des.wa.gov/contracting/MillerKnoll%20Pricing.pdf",
) -> ParsedCoopContract:
    """Parse a co-op furniture pricing PDF into normalized discount-off-list bands.

    Targets the NASPO/MillerKnoll grid layout described in the module docstring. Rows that
    don't yield a brand + at least one percentage are skipped (and counted in warnings) — we
    never fabricate a discount we didn't read.
    """
    import pdfplumber

    opener = io.BytesIO(source) if isinstance(source, bytes) else source
    with pdfplumber.open(opener) as pdf:
        pages = pdf.pages
        page_text = [p.extract_text() or "" for p in pages]
        page_tables = [p.extract_tables() or [] for p in pages]

    title = "Co-op Furniture Pricing"
    for txt in page_text:
        for line in txt.splitlines():
            line = line.strip()
            if "Pricing Information" in line or "Price List" in line:
                title = line
                break
        if title != "Co-op Furniture Pricing":
            break

    result = ParsedCoopContract(
        title=title, source_contract=source_contract, source_url=source_url
    )

    skipped = 0
    last_brand: str | None = None
    current_category: str | None = None  # carried across pages (a table can span pages)
    for txt, tables in zip(page_text, page_tables):
        # Category headers live in page text (not always inside a table cell on this layout).
        # The first header on a page (if any) applies to that page's leading rows; later
        # headers within the page are picked up from in-grid text rows below.
        for line in txt.splitlines():
            m = _CATEGORY_RE.search(line)
            if m:
                current_category = m.group(2).strip()
                break

        for table in tables:
            for row in table:
                cells = _collapse(row)
                if not cells or _is_header_row(cells):
                    continue

                # Pull every percentage cell out; the remainder is text (brand/line/collection).
                pcts: list[float] = []
                texts: list[str] = []
                for c in cells:
                    v = _pct_to_float(c)
                    if v is not None:
                        pcts.append(v)
                    else:
                        texts.append(c)

                if not pcts:
                    # A category section header can appear as a lone text row inside the grid.
                    joined = " ".join(texts)
                    cm = _CATEGORY_RE.search(joined)
                    if cm:
                        current_category = cm.group(2).strip()
                    continue

                # Identify brand: first text cell that looks like a brand; else inherit the
                # previous row's brand (wrapped multi-line product names leave brand blank).
                brand = ""
                rest: list[str] = []
                for t in texts:
                    if not brand and (t.lower() in _KNOWN_BRANDS or last_brand is None):
                        brand = t
                    else:
                        rest.append(t)
                if not brand:
                    brand = last_brand or ""
                if brand:
                    last_brand = brand
                if not brand:
                    skipped += 1
                    continue

                product_line = rest[0] if rest else ""
                collection = rest[1] if len(rest) > 1 else None

                result.bands.append(
                    DiscountBand(
                        manufacturer=brand,
                        manufacturer_code=manufacturer_code(brand),
                        product_line=product_line,
                        collection=collection,
                        category=current_category,
                        discount_pct=pcts[0],
                        tier_discounts=pcts,
                        source_contract=source_contract,
                        source_url=source_url,
                    )
                )

    if skipped:
        result.warnings.append(f"Skipped {skipped} row(s) without an identifiable brand.")
    if not result.bands:
        result.warnings.append(
            "No discount bands parsed — the PDF layout may differ from the targeted "
            "NASPO/MillerKnoll grid. Inspect with pdfplumber.extract_tables()."
        )
    return result
