"""SIF (Standard Interchange Format) parser + writer — the production data primitive.

SIF is the de-facto contract-furniture interchange format. Every specifier a dealer
already runs (CET Designer, Configura Spec/ProjectSpec, 2020 Worksheet) EXPORTS it, and
every dealer ERP (Hedberg, ECi DDMSPLUS) IMPORTS it. That makes it the legitimate,
vendor-neutral pipe for a dealer-facing tool: the dealer hands us SIF straight from the
tools they own — no licensed OFML ingestion required.

Format (per the public Design Manager spec + corroborating sources):
  - Plain text, line-oriented, records separated by blank line(s), CRLF in the wild.
  - Each field is its own line: `KEY=VALUE`.
  - A leading record may be file-level header (ST = title, SF = source/cross-ref).
  - Per line item — required: PN (part number), and in practice PD/MC/QT/PL.
        PN  part number (canonical SKU)
        PD  product description
        MC  manufacturer code (<=5 chars)
        QT  quantity
        PL  list price (unit, list)
    Optional commercial/option fields we use:
        S%  discount percent (e.g. 50.0)   |  S-  discount amount (per unit)
        ON  option number   |  OD  option description   (repeat as pairs)
        AN/AD  attribute number/description (repeat)

  Real files carry per-implementation extension fields (DX-prefixed, etc.); we preserve
  every unknown field on the record so nothing is silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Keys that may legitimately repeat within a single item record.
_OPTION_KEYS = {"ON", "OD"}
_ATTR_KEYS = {"AN", "AD"}


@dataclass
class SifOption:
    number: str = ""
    description: str = ""


@dataclass
class SifLineItem:
    part_number: str
    manufacturer_code: str = ""
    description: str = ""
    quantity: float = 1.0
    list_price: float = 0.0
    discount_pct: float | None = None      # from S%
    discount_amount: float | None = None   # from S- (per unit)
    options: list[SifOption] = field(default_factory=list)
    attributes: list[SifOption] = field(default_factory=list)
    raw: dict[str, list[str]] = field(default_factory=dict)  # every field, nothing dropped


@dataclass
class SifFile:
    title: str = ""
    source: str = ""
    items: list[SifLineItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _to_float(value: str, default: float = 0.0) -> float:
    s = re.sub(r"[^0-9.\-]", "", value or "")
    if s in ("", "-", ".", "--"):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _split_records(text: str) -> list[list[tuple[str, str]]]:
    """Split a SIF blob into records (lists of (KEY, VALUE)) on blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    records: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if current:
                records.append(current)
                current = []
            continue
        if "=" not in line:
            # tolerate stray lines (e.g. comments) without dropping the record
            continue
        key, val = line.split("=", 1)
        current.append((key.strip().upper(), val.strip()))
    if current:
        records.append(current)
    return records


def parse_sif(text: str) -> SifFile:
    out = SifFile()
    for record in _split_records(text):
        keys = {k for k, _ in record}

        # File-level header record: has ST/SF but no PN.
        if "PN" not in keys and (keys & {"ST", "SF"}):
            for k, v in record:
                if k == "ST" and not out.title:
                    out.title = v
                elif k == "SF" and not out.source:
                    out.source = v
            continue

        if "PN" not in keys:
            out.warnings.append(f"Skipped record without PN: {record[:2]}")
            continue

        item = SifLineItem(part_number="")
        pending_option: SifOption | None = None
        pending_attr: SifOption | None = None

        for k, v in record:
            item.raw.setdefault(k, []).append(v)

            if k == "PN":
                item.part_number = v
            elif k == "MC":
                item.manufacturer_code = v
            elif k == "PD":
                item.description = v
            elif k == "QT":
                item.quantity = _to_float(v, 1.0) or 1.0
            elif k == "PL":
                item.list_price = _to_float(v, 0.0)
            elif k == "S%":
                item.discount_pct = _to_float(v, 0.0)
            elif k == "S-":
                item.discount_amount = _to_float(v, 0.0)
            elif k == "ON":
                pending_option = SifOption(number=v)
                item.options.append(pending_option)
            elif k == "OD":
                if pending_option is not None and not pending_option.description:
                    pending_option.description = v
                else:
                    item.options.append(SifOption(description=v))
            elif k == "AN":
                pending_attr = SifOption(number=v)
                item.attributes.append(pending_attr)
            elif k == "AD":
                if pending_attr is not None and not pending_attr.description:
                    pending_attr.description = v
                else:
                    item.attributes.append(SifOption(description=v))

        if not item.description:
            item.description = item.part_number
        out.items.append(item)
    return out


def write_sif(sif: SifFile) -> str:
    """Serialize back to SIF (round-trip). Useful for export back into dealer tools."""
    lines: list[str] = []
    header: list[str] = []
    if sif.title:
        header.append(f"ST={sif.title}")
    if sif.source:
        header.append(f"SF={sif.source}")
    if header:
        lines.extend(header)
        lines.append("")

    for it in sif.items:
        block = [f"MC={it.manufacturer_code}", f"PN={it.part_number}", f"PD={it.description}",
                 f"QT={_fmt_qty(it.quantity)}", f"PL={it.list_price:.2f}"]
        if it.discount_pct is not None:
            block.append(f"S%={it.discount_pct:.1f}")
        if it.discount_amount is not None:
            block.append(f"S-={it.discount_amount:.2f}")
        for opt in it.options:
            if opt.number:
                block.append(f"ON={opt.number}")
            if opt.description:
                block.append(f"OD={opt.description}")
        lines.extend(block)
        lines.append("")

    return "\r\n".join(lines).rstrip("\r\n") + "\r\n"


def _fmt_qty(q: float) -> str:
    return str(int(q)) if float(q).is_integer() else f"{q:g}"
