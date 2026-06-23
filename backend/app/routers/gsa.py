"""FastAPI router for the GSA Advantage furniture price-list connector.

Defines an APIRouter only — the integrator registers it in main.py later with:

    from .routers import gsa
    app.include_router(gsa.router)

Endpoints:
    GET  /api/gsa/health                  — connector status + known furniture contracts
    POST /api/gsa/pull/{contract}         — live-fetch + parse a contract's price list
    GET  /api/gsa/parse/{contract}        — parse previously-cached HTML (no network)

The pull endpoint returns parsed rows in the project's catalog shape. It does NOT write to
the DB by itself (kept side-effect-free for the pilot); the integrator can feed
`row` dicts into the existing catalog upsert. See the module README in app/gsa/__init__.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..gsa.parser import parse_price_list
from ..gsa.scraper import GsaScraperError, fetch_price_list, load_cached, price_list_url

router = APIRouter(prefix="/api/gsa", tags=["gsa"])

# Verified furniture contractors under MAS SIN 33721 (public price lists).
KNOWN_FURNITURE_CONTRACTS = {
    "GS27F0014V": "Steelcase Inc.",
    "47QSMS24D0034": "Steelcase Inc.",
    "GS03F036DA": "MillerKnoll / Herman Miller",
    "GS03F057DA": "Haworth Inc.",
}


def _serialize(parse_result, fetch=None) -> dict:
    rows = [r.to_catalog_dict() for r in parse_result.records]
    payload = {
        "contract": parse_result.contract,
        "manufacturer": parse_result.manufacturer,
        "sin": "33721",
        "price_kind": "gsa_net",  # GSA Advantage carries the government NET price
        "count": len(rows),
        "rows": rows,
        "warnings": list(parse_result.warnings),
    }
    if fetch is not None:
        payload["fetch"] = {
            "method": fetch.method,
            "url": fetch.url,
            "status": fetch.status,
            "ok": fetch.ok,
            "looks_blocked": fetch.looks_blocked,
            "note": fetch.note,
            "bytes": fetch.length,
        }
        payload["warnings"].extend(fetch.warnings)
    return payload


@router.get("/health")
def health():
    return {
        "status": "ok",
        "connector": "gsa-advantage",
        "schedule": "MAS",
        "sin": "33721",
        "url_pattern": price_list_url("<CONTRACT>"),
        "known_contracts": KNOWN_FURNITURE_CONTRACTS,
        "note": (
            "GSA Advantage ref_text pages are WAF/JS-gated and most redirect to a "
            "Terms & Conditions PDF; a headless browser (Playwright) is used to fetch. "
            "Prices returned are the GOVERNMENT NET price (gsa_net)."
        ),
    }


@router.post("/pull/{contract}")
def pull(contract: str, save: bool = Query(True, description="cache HTML under data/gsa/")):
    """Live-fetch and parse a contract's GSA Advantage price list."""
    try:
        fetch = fetch_price_list(contract, save=save)
    except GsaScraperError as exc:
        raise HTTPException(status_code=502, detail=f"GSA fetch failed: {exc}") from exc

    parsed = parse_price_list(fetch.html, contract=contract,
                              manufacturer=KNOWN_FURNITURE_CONTRACTS.get(contract.upper()))
    return _serialize(parsed, fetch)


@router.get("/parse/{contract}")
def parse_cached(contract: str):
    """Parse previously-cached HTML for a contract (no network)."""
    try:
        fetch = load_cached(contract)
    except GsaScraperError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    parsed = parse_price_list(fetch.html, contract=contract,
                              manufacturer=KNOWN_FURNITURE_CONTRACTS.get(contract.upper()))
    return _serialize(parsed, fetch)
