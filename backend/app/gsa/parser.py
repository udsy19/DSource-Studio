"""Parse GSA Advantage price-list HTML into normalized catalog records.

Network-independent: feed it an HTML string (live-fetched or a saved fixture) and it
returns a list of `GsaPriceRecord`.

GSA Advantage "Authorized FSS Schedule Price List" pages render the catalog as one or more
HTML tables. The standard GSA Advantage product table carries, per row:

    * a manufacturer part number  (header: "MFR PART #", "Mfr Part No", "Part Number",
      "Manufacturer Part Number", "Model", "Item #")
    * a product description / name (header: "Description", "Product", "Item Description")
    * a price                      (header: "GSA Price", "Price", "Net Price",
      "Government Net Price", "Unit Price")

KEY PRICING NOTE: GSA Advantage shows the **Government NET price** — the discounted price
the government pays, with the schedule discount already deducted. There is usually NO
separate "list price" column. So we map the scraped figure to `gsa_price`, and the project
catalog's `list_price` slot should be populated from `gsa_price` (clearly labeled) rather
than pretending it is a manufacturer list price.

The parser is defensive: it locates the price-list table by inspecting header cells,
tolerates extra columns (SIN, UOM, qty), and falls back to a plain-text line scanner if
no recognizable table is present (covers the I-FSS-600 "text file" template variant).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---- header keyword maps (lowercased substring match) -----------------------------

_PART_HEADERS = (
    "mfr part", "manufacturer part", "mfg part", "part number", "part no",
    "part #", "model number", "model #", "model no", "item number", "item #",
    "manufacturer's part", "mfr model",
)
_DESC_HEADERS = (
    "description", "item description", "product description", "product name",
    "product", "item name", "nomenclature",
)
_PRICE_HEADERS = (
    "gsa price", "government net price", "net price", "gsa net", "unit price",
    "price", "awarded price", "contract price",
)
_MFR_HEADERS = (
    "manufacturer", "mfr name", "mfr", "make", "brand", "vendor",
)
_SIN_HEADERS = ("sin", "special item number")
_UOM_HEADERS = ("uom", "unit of issue", "unit of measure", "u/i", "u/m")

# A price like $1,234.56 or 1234.56 (optionally with $ and thousands separators).
_PRICE_RE = re.compile(r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)")


@dataclass
class GsaPriceRecord:
    """One normalized price-list row.

    Maps onto the project's catalog Product shape:
        manufacturer_code -> Product.manufacturer_code
        sku               -> Product.sku   (manufacturer part number)
        name              -> Product.name  (short description)
        gsa_price         -> Product.list_price  (GSA = government NET price; see module
                             docstring — there is no separate list price on GSA Advantage)
    """

    manufacturer_code: str
    sku: str
    name: str
    gsa_price: float | None = None
    # GSA pages carry the government net price, not a separate manufacturer list price.
    list_price: float | None = None
    sin: str | None = None
    uom: str | None = None
    contract: str | None = None
    source: str = "gsa"

    def to_catalog_dict(self) -> dict:
        """Project-shaped dict for catalog upsert. Uses gsa_price as the catalog price."""
        return {
            "manufacturer_code": self.manufacturer_code,
            "sku": self.sku,
            "name": self.name,
            # Catalog stores one price; GSA gives us the government net price.
            "list_price": self.gsa_price if self.gsa_price is not None else (self.list_price or 0.0),
            "price_uom": (self.uom or "each").lower(),
            "source": self.source,
            "price_kind": "gsa_net",  # explicit label so the integrator never confuses it
        }


@dataclass
class GsaParseResult:
    contract: str | None
    manufacturer: str | None
    records: list[GsaPriceRecord]
    warnings: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.records)


# ---- helpers ----------------------------------------------------------------------

def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _match_header(cell: str, keywords: tuple[str, ...]) -> bool:
    c = cell.lower()
    return any(k in c for k in keywords)


def _parse_price(text: str) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _mfr_code(manufacturer: str | None, fallback: str = "GSA") -> str:
    """Derive a short (<=8 char) manufacturer_code from a manufacturer name."""
    name = _norm(manufacturer)
    if not name:
        return fallback
    # Take alphanumerics of the first word(s), upper, truncate to 8.
    token = re.sub(r"[^A-Za-z0-9]", "", name.split()[0])
    return (token[:8] or fallback).upper()


# ---- core: table parsing ----------------------------------------------------------

def _column_index(headers: list[str], keywords: tuple[str, ...]) -> int | None:
    for i, h in enumerate(headers):
        if _match_header(h, keywords):
            return i
    return None


def _parse_tables(html: str, contract: str | None, manufacturer: str | None,
                  warnings: list[str]) -> list[GsaPriceRecord]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:  # pragma: no cover
        warnings.append("beautifulsoup4 not installed; cannot parse HTML tables")
        return []

    soup = BeautifulSoup(html, "html.parser")
    records: list[GsaPriceRecord] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Find a header row that has both a part-number-ish and a price-ish column.
        header_idx = None
        headers: list[str] = []
        for ri, row in enumerate(rows[:5]):
            cells = [_norm(c.get_text(" ")) for c in row.find_all(["th", "td"])]
            if not cells:
                continue
            has_part = any(_match_header(c, _PART_HEADERS) for c in cells)
            has_price = any(_match_header(c, _PRICE_HEADERS) for c in cells)
            if has_part and has_price:
                header_idx = ri
                headers = cells
                break

        if header_idx is None:
            continue

        i_part = _column_index(headers, _PART_HEADERS)
        i_desc = _column_index(headers, _DESC_HEADERS)
        i_price = _column_index(headers, _PRICE_HEADERS)
        # Manufacturer column, but never re-use the part/desc/price columns (e.g. the
        # "mfr" in "Mfr Part No" must not be mistaken for a manufacturer-name column).
        i_mfr = _column_index(headers, _MFR_HEADERS)
        if i_mfr in (i_part, i_desc, i_price):
            i_mfr = None
        i_sin = _column_index(headers, _SIN_HEADERS)
        i_uom = _column_index(headers, _UOM_HEADERS)
        if i_part is None or i_price is None:
            continue

        for row in rows[header_idx + 1:]:
            cells = [_norm(c.get_text(" ")) for c in row.find_all(["th", "td"])]
            if len(cells) <= max(i_part, i_price):
                continue
            sku = cells[i_part]
            price = _parse_price(cells[i_price])
            if not sku or price is None:
                continue
            name = cells[i_desc] if (i_desc is not None and i_desc < len(cells)) else sku
            # Prefer a per-row manufacturer column; otherwise fall back to the page-level
            # contractor name so every row shares one stable manufacturer_code.
            row_mfr = (cells[i_mfr] if (i_mfr is not None and i_mfr < len(cells)) else None) or manufacturer or "GSA"
            sin = cells[i_sin] if (i_sin is not None and i_sin < len(cells)) else None
            uom = cells[i_uom] if (i_uom is not None and i_uom < len(cells)) else None
            records.append(GsaPriceRecord(
                manufacturer_code=_mfr_code(row_mfr),
                sku=sku, name=name or sku, gsa_price=price,
                sin=sin or None, uom=uom or None, contract=contract,
            ))

    return records


# ---- core: plain-text fallback ----------------------------------------------------

# Lines like:  SIN 33721  PART-123  Mesh task chair  $345.67
_TEXT_LINE_RE = re.compile(
    r"^(?P<sku>[A-Z0-9][A-Z0-9./\-]{2,30})\s+"
    r"(?P<name>.+?)\s+"
    r"\$?(?P<price>[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\s*$"
)


def _parse_text(text: str, contract: str | None, manufacturer: str | None,
                warnings: list[str]) -> list[GsaPriceRecord]:
    records: list[GsaPriceRecord] = []
    for raw in text.splitlines():
        line = _norm(raw)
        if not line:
            continue
        m = _TEXT_LINE_RE.match(line)
        if not m:
            continue
        price = _parse_price(m.group("price"))
        if price is None:
            continue
        records.append(GsaPriceRecord(
            manufacturer_code=_mfr_code(manufacturer),
            sku=m.group("sku"), name=_norm(m.group("name")),
            gsa_price=price, contract=contract,
        ))
    if records:
        warnings.append("parsed via plain-text fallback (no recognizable HTML table)")
    return records


# ---- metadata extraction ----------------------------------------------------------

_CONTRACT_RE = re.compile(r"\b((?:GS|47Q)[A-Z0-9]{6,16})\b")


def _extract_contract(html_or_text: str, given: str | None) -> str | None:
    if given:
        return given.strip().upper()
    m = _CONTRACT_RE.search(html_or_text or "")
    return m.group(1) if m else None


def _extract_manufacturer(html: str) -> str | None:
    """Best-effort: GSA pages name the contractor near the top (e.g. 'STEELCASE INC.')."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        title = soup.find("title")
        if title:
            t = _norm(title.get_text())
            # title often == contractor name
            if t and "price list" not in t.lower() and "gsa" not in t.lower():
                return t
    except Exception:
        pass
    m = re.search(r"contractor\s*[:\-]?\s*([A-Z][A-Za-z0-9 .,&'\-]{2,60})", html or "")
    return _norm(m.group(1)) if m else None


# ---- public API -------------------------------------------------------------------

def parse_price_list(html: str, *, contract: str | None = None,
                     manufacturer: str | None = None) -> GsaParseResult:
    """Parse GSA Advantage price-list HTML/text into normalized records.

    Args:
        html: the rendered HTML (or plain text) of an `_online.htm` price list.
        contract: optional contract number to stamp on records (else auto-detected).
        manufacturer: optional manufacturer/contractor name (else auto-detected).
    """
    warnings: list[str] = []
    contract_ = _extract_contract(html, contract)
    manufacturer_ = manufacturer or _extract_manufacturer(html)

    records: list[GsaPriceRecord] = []
    if "<" in (html or "") and ">" in (html or ""):
        records = _parse_tables(html, contract_, manufacturer_, warnings)
    if not records:
        records = _parse_text(html, contract_, manufacturer_, warnings)

    if not records:
        warnings.append(
            "no price rows found — page may be empty/WAF-blocked or use an unrecognized layout"
        )

    # De-dupe on (manufacturer_code, sku), keeping first occurrence.
    seen: set[tuple[str, str]] = set()
    deduped: list[GsaPriceRecord] = []
    for r in records:
        key = (r.manufacturer_code, r.sku)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)

    return GsaParseResult(
        contract=contract_, manufacturer=manufacturer_,
        records=deduped, warnings=warnings,
    )
