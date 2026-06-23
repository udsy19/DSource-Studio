"""Fetcher for GSA Advantage public price-list pages.

GSA Advantage `ref_text/<CONTRACT>/<CONTRACT>_online.htm` pages are protected by a JS /
WAF challenge: a plain `httpx`/`requests` GET returns an empty (or challenge-only) body.
A headless browser is required to let the challenge resolve and the catalog render.

Strategy:
  1. Try Playwright (headless Chromium) with a real user-agent and generous timeouts.
     This is the path that actually works against the live site.
  2. If Playwright (or its browser binary) is unavailable in the environment, fall back to
     a plain `httpx` GET so the caller still gets *something* (and a clear marker that it
     is likely WAF-blocked). The parser is tested independently of this module, so a
     blocked fetch never blocks development.

Everything here is best-effort and honest: `fetch_price_list` returns a `FetchResult` that
records which method was used, the HTTP/render status, and whether the body looks empty /
WAF-gated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

GSA_BASE = "https://www.gsaadvantage.gov/ref_text"

# A real, current desktop UA. The WAF rejects obvious bot UAs.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Where we stash fetched HTML for offline parser testing.
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "gsa"


class GsaScraperError(RuntimeError):
    """Raised when a fetch cannot be performed at all (not merely WAF-blocked)."""


def price_list_url(contract: str) -> str:
    """Build the public price-list URL for a GSA contract number.

    e.g. price_list_url("GS27F0014V") ->
        https://www.gsaadvantage.gov/ref_text/GS27F0014V/GS27F0014V_online.htm
    """
    c = (contract or "").strip().upper()
    if not c:
        raise GsaScraperError("empty contract number")
    return f"{GSA_BASE}/{c}/{c}_online.htm"


@dataclass
class FetchResult:
    contract: str
    url: str
    method: str            # "playwright" | "httpx" | "cache"
    html: str
    status: int | None = None        # HTTP status (httpx) or None for playwright
    ok: bool = False                 # we got a non-trivial body back
    looks_blocked: bool = False      # body empty / challenge-only => likely WAF
    note: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.html or "")


def _looks_blocked(html: str) -> bool:
    """Heuristic: empty body or a bare WAF/challenge page with no catalog content."""
    if not html or len(html.strip()) < 200:
        return True
    low = html.lower()
    challenge_markers = (
        "request unsuccessful",
        "incapsula",
        "_incapsula_resource",
        "access denied",
        "are you a human",
        "enable javascript",
        "captcha",
    )
    has_challenge = any(m in low for m in challenge_markers)
    # The real price list mentions the contract or "price list" / a product table.
    has_catalog = ("price list" in low or "<table" in low or "mfr part" in low
                   or "special item number" in low)
    return has_challenge and not has_catalog


def fetch_with_playwright(url: str, *, timeout_ms: int = 45000,
                          settle_ms: int = 3500,
                          user_agent: str = DEFAULT_USER_AGENT) -> tuple[str, str]:
    """Render `url` in headless Chromium and return (html, note).

    Raises GsaScraperError if Playwright or the browser binary is unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - env dependent
        raise GsaScraperError(f"playwright not installed: {exc}") from exc

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:  # browser binary missing / sandbox blocked
                raise GsaScraperError(f"chromium launch failed: {exc}") from exc
            try:
                context = browser.new_context(
                    user_agent=user_agent,
                    viewport={"width": 1366, "height": 900},
                    locale="en-US",
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Let the WAF JS challenge resolve + catalog hydrate.
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                except Exception:
                    pass
                time.sleep(settle_ms / 1000.0)
                html = page.content()
                return html, "rendered via headless chromium"
            finally:
                browser.close()
    except GsaScraperError:
        raise
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        raise GsaScraperError(f"playwright fetch error: {exc}") from exc


def fetch_with_httpx(url: str, *, timeout: float = 30.0,
                     user_agent: str = DEFAULT_USER_AGENT) -> tuple[str, int]:
    """Plain HTTP GET fallback. Expected to be WAF-blocked (empty body) on live GSA."""
    import httpx

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        resp = client.get(url)
        return resp.text, resp.status_code


def fetch_price_list(contract: str, *, prefer_playwright: bool = True,
                     save: bool = False) -> FetchResult:
    """Fetch a contract's GSA Advantage price-list HTML.

    Tries Playwright first (the path that works against the live WAF-gated site); falls
    back to httpx if the browser is unavailable. Always returns a FetchResult describing
    what happened — it never silently hides a WAF block.
    """
    url = price_list_url(contract)
    contract_u = contract.strip().upper()
    warnings: list[str] = []

    if prefer_playwright:
        try:
            html, note = fetch_with_playwright(url)
            blocked = _looks_blocked(html)
            result = FetchResult(
                contract=contract_u, url=url, method="playwright", html=html,
                ok=not blocked, looks_blocked=blocked, note=note, warnings=warnings,
            )
            if save:
                _save(result)
            return result
        except GsaScraperError as exc:
            warnings.append(f"playwright unavailable, falling back to httpx: {exc}")

    # Fallback: plain HTTP (likely empty/blocked on live GSA).
    try:
        html, status = fetch_with_httpx(url)
    except Exception as exc:
        raise GsaScraperError(f"both playwright and httpx failed: {exc}") from exc

    blocked = _looks_blocked(html)
    note = "httpx GET (WAF likely blocked)" if blocked else "httpx GET"
    result = FetchResult(
        contract=contract_u, url=url, method="httpx", html=html, status=status,
        ok=not blocked, looks_blocked=blocked, note=note, warnings=warnings,
    )
    if save:
        _save(result)
    return result


def _save(result: FetchResult) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{result.contract}_online.htm"
    path.write_text(result.html or "", encoding="utf-8")
    return path


def load_cached(contract: str) -> FetchResult:
    """Load previously-saved HTML for offline parsing."""
    path = DATA_DIR / f"{contract.strip().upper()}_online.htm"
    if not path.exists():
        raise GsaScraperError(f"no cached HTML at {path}")
    html = path.read_text(encoding="utf-8")
    return FetchResult(
        contract=contract.strip().upper(), url=price_list_url(contract),
        method="cache", html=html, ok=not _looks_blocked(html),
        looks_blocked=_looks_blocked(html), note=f"loaded {path}",
    )
