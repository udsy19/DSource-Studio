"""pCon.basket Excel / CSV article-list adapter.

Secondary ingest path for dealers who export from pCon rather than a SIF-producing
specifier. pCon.basket's Excel export is multi-sheet (article details/prices, article
list with properties/calculations, customer data); its CSV is an article list. We map a
flexible set of column synonyms onto the same normalized line shape the SIF parser emits,
so downstream code is format-agnostic.
"""

from __future__ import annotations

import io
import re

import pandas as pd

from .sif import SifFile, SifLineItem

COLUMN_SYNONYMS: dict[str, list[str]] = {
    "manufacturer": ["manufacturer", "mfr", "brand", "series", "supplier"],
    "sku": ["article", "article number", "article no", "part number", "part no",
            "model", "sku", "item number", "product code"],
    "description": ["description", "short text", "name", "product", "title"],
    "qty": ["qty", "quantity", "count", "amount", "pieces"],
    "list_price": ["list price", "list", "unit price", "price", "sales price", "unit list"],
    "discount_pct": ["discount", "discount %", "disc %", "discount percent"],
}


def _norm(c: str) -> str:
    return re.sub(r"\s+", " ", str(c).strip().lower())


def _to_float(v, default=0.0) -> float:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    s = re.sub(r"[^0-9.\-]", "", str(v))
    if s in ("", "-", "."):
        return default
    try:
        return float(s)
    except ValueError:
        return default


def _build_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized = {c: _norm(c) for c in columns}
    for canonical, syns in COLUMN_SYNONYMS.items():
        synset = set(syns)
        for src, n in normalized.items():
            if src in mapping:
                continue
            if n in synset:
                mapping[src] = canonical
                break
    return mapping


def read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    return pd.read_csv(io.BytesIO(content), sep=None, engine="python")


def parse_pcon(content: bytes, filename: str) -> tuple[SifFile, dict[str, str]]:
    """Return a SifFile (reusing the normalized line shape) + the column mapping."""
    df = read_dataframe(content, filename)
    mapping = _build_mapping(list(df.columns))
    canon_to_src = {v: k for k, v in mapping.items()}
    out = SifFile(title=f"pCon import: {filename}", source="pcon")

    def get(row, field):
        src = canon_to_src.get(field)
        return row[src] if src is not None and src in row else None

    for _, row in df.iterrows():
        sku = get(row, "sku")
        if sku is None or str(sku).strip() == "":
            continue
        mfr = str(get(row, "manufacturer") or "").strip()
        disc = get(row, "discount_pct")
        out.items.append(
            SifLineItem(
                part_number=str(sku).strip(),
                manufacturer_code=mfr,
                description=str(get(row, "description") or sku).strip(),
                quantity=_to_float(get(row, "qty"), 1.0) or 1.0,
                list_price=_to_float(get(row, "list_price"), 0.0),
                discount_pct=_to_float(disc) if disc is not None else None,
            )
        )
    if not out.items:
        out.warnings.append("No rows with a recognizable article/SKU column were found.")
    return out, mapping
