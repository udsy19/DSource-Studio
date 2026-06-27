"""India sourcing — map a test-fit's furniture program to REAL catalog SKUs (INR) via the
match engine. Honest: any need with no real catalog match is reported in `unmatched`, never
priced with a fabricated number. Replaces the legacy US-dealer USD quote/BOM.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..embeddings.catalog_index import get_embedder, get_index
from ..matching import bands_for, format_hits

router = APIRouter(prefix="/api/source", tags=["source"])

# Furniture per test-fit instance: (need label, catalog search query, quantity per instance).
_PROGRAM: dict[str, list[tuple[str, str, int]]] = {
    "workstation": [("Desk", "office desk workstation", 1),
                    ("Task chair", "ergonomic mesh office chair", 1)],
    "private_office": [("Desk", "executive office table desk", 1),
                       ("Task chair", "high back office chair", 1)],
    "meeting_room": [("Table", "conference meeting table", 1),
                     ("Chair", "office chair", 6)],
    "collaboration": [("Lounge", "lounge sofa seating", 2)],
}


class SourceRequest(BaseModel):
    counts: dict[str, int]


def build_india_source(counts: dict[str, int], match: Callable[[str], dict | None]) -> dict:
    lines: list[dict] = []
    unmatched: list[dict] = []
    for itype, items in _PROGRAM.items():
        n = counts.get(itype, 0)
        if n <= 0:
            continue
        for label, query, per in items:
            qty = n * per
            r = match(query)
            if r and r.get("label") != "no_match" and r.get("price_inr"):
                gst = r.get("gst_rate") or 0.18
                lines.append({
                    "need": label, "for_type": itype, "qty": qty,
                    "sku": r["sku"], "name": r["name"], "vendor": r["vendor"],
                    "unit_inr": r["price_inr"], "gst_rate": gst,
                    "line_inr": round(qty * r["price_inr"], 2),
                    "label": r["label"], "material": r.get("material"),
                })
            else:
                unmatched.append({"need": label, "for_type": itype, "qty": qty})

    subtotal = sum(line["line_inr"] for line in lines)
    gst_total = sum(line["line_inr"] * line["gst_rate"] for line in lines)
    return {
        "currency": "INR", "lines": lines, "unmatched": unmatched,
        "subtotal": round(subtotal, 2), "gst": round(gst_total, 2),
        "total": round(subtotal + gst_total, 2),
    }


@router.post("/india")
def source_india(req: SourceRequest, db: Session = Depends(get_db)) -> dict:
    embedder, index, bands = get_embedder(), get_index(), bands_for(by_image=False)

    def match(query: str) -> dict | None:
        hits = index.query(embedder.embed_text(query), k=1)
        return format_hits(db, hits, bands)[0] if hits else None

    return build_india_source(req.counts, match)
