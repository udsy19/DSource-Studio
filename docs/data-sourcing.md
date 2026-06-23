# Real-Data Sourcing Strategy (no mock data)

How DSource gets **real** US office-furniture catalog + pricing data — without depending on a
signed dealer to start. Researched + cross-verified (2026-06-20). Nothing here is legal advice;
the redistribution/ToS items flagged below need counsel before scaling.

## The core insight
**No single source gives clean `(part# + list price + net price + geometry)` at scale for free.
You ASSEMBLE it** from complementary public sources, then converge on the dealer's exact data
once one signs. Each source fills a different field:

| Field we need | Best real source | Access | Notes |
|---|---|---|---|
| Part number + specs | GSA Advantage; manufacturer price books; .rfa BIM params | scrape / parse | facts, uncopyrightable (Feist) |
| **List price** | **Manufacturer price-book PDFs** (e.g. Herman Miller `PB_*.pdf`) | parse PDF | the field GSA does **not** carry |
| **Net / discounted** | **GSA Advantage** (GSA price); co-op discount bands | scrape / parse | GSA gives discounted, not list |
| Discount-off-list band | Sourcewell (public CDN), NASPO state addenda | parse PDF | e.g. Steelcase ~40–64% off |
| Geometry (footprint/3D) | Manufacturer BIM portals (Revit .rfa, SketchUp, DWG) | per-product download | `.rfa` embeds part# + dims |
| **Exact catalog + true net (gold)** | **Dealer pCon/CET export (SIF/OEX)** | dealer-licensed | the eventual gold path |

This does **not** replace the dealer-facing thesis — the dealer stays the gold source (exact
catalog, true net, fulfillment). Public sources let us **build and demo on real data NOW**,
pre-dealer, and kill the "can we even get data?" risk.

## Sources, ranked by effort vs payoff (for getting real data WITHOUT a dealer)

### 1. Manufacturer price-book PDFs → real LIST prices + part numbers  ·  payoff HIGH / effort MED  ·  *start here*
Manufacturers publish list price books as PDFs (Herman Miller `PB_AEN.pdf` etc.; Steelcase,
Haworth similar). These carry **part number + description + list price** — exactly the list field
GSA lacks. Parseable at scale (PDF table extraction). Lowest legal risk (published facts, no
login, no WAF). **This is the most direct real-list-price source.**

### 2. GSA Advantage! product/price lists → real part# + GSA (net) price  ·  payoff HIGH / effort MED-HIGH
Path: **GSA eLibrary** → filter MAS SIN **33721 (Office Furniture)** → "Download Contractors"
(Excel) → for each contract pull `gsaadvantage.gov/ref_text/<CONTRACT>/<CONTRACT>_online.htm`.
Carries **manufacturer part number + GSA discounted price** (no list-price field). Coverage
confirmed: Steelcase, MillerKnoll, Haworth, Allsteel/HNI.
**Confirmed live:** these pages are **JS/WAF-gated** — plain HTTP returns empty, so you need a
**headless browser** (Playwright). An Apify "GSA eLibrary scraper" already exists as a shortcut.

### 3. Cooperative contracts → discount-off-list bands  ·  payoff MED / effort LOW-MED
**Sourcewell** publishes awarded furniture pricing PDFs on a public CDN (no login);
**NASPO ValuePoint** state participating addenda are public (~44–61% off list). Gives the
list-minus % to model net from list. (E&I / TIPS / Premier are membership-gated — skip.)
Mostly PDF parsing; file paths rotate between contract cycles.

### 4. Manufacturer BIM/3D portals → geometry for the test-fit  ·  payoff HIGH (Phase 2) / effort MED
Steelcase (templated Revit endpoints), Herman Miller (Revit `.rfa` / SketchUp `.skp` /
AutoCAD `.dwg`, 4 formats per product). **Per-product downloads, no bulk/API, no pricing** —
but `.rfa` files embed part numbers + dimensions as parameters (geometry **and** identity).
**Avoid aggregators** like BIMobject: their ToS (eff. 2025-06-24) forbids scraping and
prohibits ingesting content into a commercial product's catalog.

### 5. Dealer pCon/CET export (SIF/OEX) → exact catalog + true net  ·  payoff HIGHEST / effort LOW once signed
The gold path, fully legitimate, already built into our ingest (`backend/app/ingest/`).
pCon.basket PRO computes real multi-level list **and** net pricing; EAIWS (SOAP) + custom-catalog
injection exist for deeper live integration. Requires the dealer's OFML license — i.e. the GTM
win. Confirmed: **no public pCon.update catalog API** (that claim was refuted), so don't plan on
ingesting raw OFML directly.

## Legal posture (flagged — get counsel before commercial redistribution)
- **Facts are free.** Feist v. Rural Telephone: part numbers, dimensions, prices are
  uncopyrightable; "sweat of the brow" rejected. We can store the **facts**.
- **Scraping public data ≠ CFAA** in the 9th Cir (hiQ v. LinkedIn, 2022) — BUT hiQ ultimately
  **lost on ToS/breach-of-contract**, and the trend (Meta v. Bright Data 2024, Air Canada v.
  Seats.aero) is contract/ToS claims, not CFAA. **So: only scrape public, non-login, non-ToS-gated
  sources.** GSA (government, permissive `robots.txt`) and published PDFs are the safe end.
- **Don't copy creative expression.** Original product descriptions, photography, and a catalog's
  selection/arrangement may be manufacturer-copyrighted. **Store facts; regenerate our own
  descriptions/imagery.** Avoid lifting marketing text/images wholesale.

## How this plugs into what's built
The Phase 0 spine doesn't change — these are just **real connectors that feed the same normalized
catalog + SIF schema** we already have (`backend/app/ingest/`, `models.py`). We swap the synthetic
seed for: a **price-book PDF parser**, a **GSA headless scraper**, and a **co-op discount parser**,
all emitting the same `SifLineItem`/Product shape. Synthetic data stays only as test fixtures.

## Connector status (built)
Three real-data connectors are implemented and feed the Phase 0 catalog/discount schema:

| Connector | Module | Status (real data) |
|---|---|---|
| **Price-book PDF parser** | `app/pricebook/` | ✅ Works. Real Herman Miller Aeron book → 7 products (AER1/AER2 @ $1,726, AERE1 @ $2,117, stool variants @ $2,212, …). Handles configurator steps + aliases; flags accessory kits for review. Also tested on Setu/Embody. |
| **GSA Advantage scraper** | `app/gsa/`, `/api/gsa/*` | ⚠️ Partial. Playwright fetch gets through the WAF (agent pulled a real 560 KB Steelcase PDF), but the `ref_text` price-list pages are **discount/T&C PDFs, not SKU tables** — per-SKU pricing needs GSA's catalog-browse endpoint (different URL). Parser is tested on a representative fixture (15 tests). |
| **Co-op discount parser** | `app/coop/`, `/api/coop/discounts` | ✅ Works **+ applies to `Discount`**. Real MillerKnoll NASPO/WA-DES "Attachment C" PDF → 246 line bands → **HMI 50.5% / KNL 57.25%** off list. With `apply=true` it upserts the bands into the `Discount` table, so the quote engine immediately uses real contract discounts. |

### The real-net path (no GSA needed)
**`price-book list × co-op discount = real net`** — proven end-to-end: a real Herman Miller Aeron
(AER1, **$1,726 list** from the price book) × a real **50.5% MillerKnoll NASPO discount** =
**$21,682 budgetary total** for 20 chairs, with **zero synthetic data** in the path. This makes
the GSA per-SKU pull lower priority: GSA gives *net* (no list field), and we already derive net
from two cleaner public sources.

Open follow-ups: GSA per-SKU is **gated** — the `ref_text` pages are WAF-blocked to simple
fetchers and redirect to discount/T&C PDFs; real per-SKU rows would need Playwright against GSA's
undocumented JS catalog-browse endpoint (deferred as low-ROI). Broaden price-book coverage to a
second manufacturer (Steelcase/Knoll layouts differ); store co-op bands per product line (not just
a per-manufacturer median).

## Recommended first build
**Manufacturer price-book PDF parser** (source #1): most direct real **list** prices, lowest legal
risk, no WAF. Start with one manufacturer, key on part number, load into the real catalog. Then
add the GSA headless scraper (#2) for net-price cross-check + coverage.

## Open items to verify before scaling
- Whether GSA Advantage offers any bulk/API beyond the stale data.gov eLibrary XLSX (unconfirmed).
- Exact column layout of a furniture price-book PDF and a GSA `_online.htm` (render in a browser).
- Current Sourcewell furniture-pricing PDF paths (they rotate).
- Counsel read on redistributing manufacturer-supplied descriptions/images.
