# DSource AI — Memory (living state)

The single source of truth for *current* state: locked decisions, status, what's real vs synthetic, open questions. Updated as work lands. Companion to `CLAUDE.md` (rules) and `ROADMAP.md` (plan).

_Last updated: 2026-06-22._

## Locked decisions

- **Product:** DSource AI — single-user (pro AND end-client), multi-typology (residential/hospitality/retail/small-workplace), India-first, inspiration → real priced sourceable design. Repoints the existing Studio engine. Not enterprise, not multi-seat.
- **Architecture principle:** catalog-backed scene = source of truth; AI = inspiration/beauty layer. Two modes (Explore creative-first / Specify catalog-first) share one engine; back-match (CLIP) bridges them; both need the same prerequisite — a real catalog with image embeddings.
- **Infra posture:** free / local-first, swappable behind interfaces. Only paid calls are the vision LLMs.
- **Catalog seed:** demand-first from a **real project** (user to provide — see open questions).
- **Enrichment:** novelty-gated router — Gemini for near-duplicates (≥~75% match to already-enriched), Claude for novel/first-seen items.
- **Never fake data:** flagged in the schema (`{value, confidence, source/basis}`); "no real match" surfaced explicitly.
- **Git:** repo `https://github.com/udsy19/DSource-AI.git`, branch `main`. Commit after every change; **no Claude/AI attribution** (`.claude/rules/git-workflow.md`).

## Recommended stack (from 2026-06-22 research; full synthesis in workflow output)

| Slot | Pick | Note |
|---|---|---|
| Harvest | 4-tier `fetch_products(domain)` over `curl_cffi` (chrome131) | Shopify `/products.json` → Woo Store API → JSON-LD(+sitemap) → Playwright. ~17/95 suppliers are clean Shopify JSON |
| Embeddings | `Marqo/marqo-ecommerce-embeddings-B` (768-dim, open_clip) | text+image one space; `-L` only if B recall weak |
| Vector store | `sqlite-vec` `vec0` table in `dsource.db` | one index serves Explore + Specify + novelty gate |
| Enrichment | gemini-2.5-flash (near-dup) / claude-haiku-4-5 (novel) / claude-opus-4-8 (hard) | one Pydantic schema both providers; PDF via **pdfplumber** (never PyMuPDF/AGPL) |
| Material→maint. | pure `derive_material_attributes()` + flat `material_attributes` table | 6 axes (Martindale/PEI/AC/Janka/ACT/GREENGUARD-CARB), each with `basis` enum |
| Vendor | `vendor` + `vendor_offering` + `manufacturers.csv`; GODL pincode CSV + haversine | Bengaluru bootstrapped manually (20–50 vetted) |
| Explore | FastSAM-s → same CLIP → cosine back-match; Flux canny+depth | avoids gated SAM 3 |
| AR | `<model-viewer>` (MIT), curated GLB, tile/paint first | per-SKU GLB asset cost is the constraint |

**Patterns to mirror:** `routers/render.py` (provider-agnostic interface), `realdata.py` `ingest_hm_pricebooks` (warm-cache guard), `procurement/models.py` `seed_vendors`, `ingest/service.py` (upsert on `(manufacturer_code, sku)`, `infer_category`). Extend `models.py` `Product` (don't add a parallel table). Swappable model names go in `config.py` like `render_model`.

## Current status

- **Repo:** git initialized, pushed to GitHub `main` (initial commit `479966a`). `.gitignore` hardened (all `*.env` excluded; verified no secrets staged). `.claude/rules/git-workflow.md` added.
- **Existing engine (from Studio):** CAD ingest (DXF/DWG + unit norm), faithful 2D+3D viewer, test-fit, wellbeing scoring, pricing connectors (~53% real), procurement RFQ/PO, Flux-Canny render proxy. 64 tests green. ~5,400 LoC Python, ~1,700 LoC TS.
- **AI render:** just rewrote to a two-pass crisp line-art ControlNet capture for layout fidelity (`CadViewer.tsx` + `render.py` flux params). Awaiting in-app retest by user.
- **Docs:** `CLAUDE.md`, `ROADMAP.md`, `memory.md` created.
- **Phase 1 IN PROGRESS:**
  - ✅ Step 1 (dep gate): torch 2.12.1 + open_clip 3.3.0 + transformers 5.12.1 + sqlite-vec 0.1.9 + curl_cffi 0.15.0 + apsw 3.53.2 install on Py3.13/arm64. marqo-ecommerce-B verified: image+text both 768-dim unit-norm; MPS available. **Key gotcha:** stdlib `sqlite3` on this macOS Python is built WITHOUT loadable extensions → `sqlite-vec` must attach via **apsw** (SqliteVecIndex will use apsw, pointed at the same `dsource.db`; SQLAlchemy keeps the stdlib driver for the ORM).
  - ✅ Step 2 (Tier-0 Shopify harvest): `app/harvest/` (schema.py NormalizedProduct + derive_gst, client.py curl_cffi, shopify.py pure parse + fetch). Pure parser offline-tested incl. rifeindia price=0/null-sku regression. 71 tests green.
  - ⏭ Next: persist NormalizedProduct → catalog (extend `Product` w/ image_url/price_inr/gst_rate/provenance), then embeddings module, match endpoint, calibration.
- **Calibration plan (no labeled set):** self-label from the catalog — multi-image products give same-product positives; title→image gives text positives; within/cross-category give close/no-match. No hand-labeling needed.
- **GST:** no canonical HSN table provided → `derive_gst(category)` (furniture 18% etc.), always flagged estimated.
- **ANTHROPIC_API_KEY** added to `.env` (dormant until Phase 1.5) — paste looked possibly truncated; verify before enrichment build.

## Real vs synthetic (honesty ledger)

- **Real:** ~53% of Studio quote (chairs/lounges from HM price books × real co-op discount); CAD geometry; `data/india/manufacturers.csv` (95 verified suppliers).
- **Synthetic / flagged:** desks/tables pricing (`real=False`); procurement vendors; WELL certs. India catalog not yet ingested. No embeddings/vector code exists yet (greenfield).

## Open questions (decide before/within Phase 1)

1. **What is the real seed project?** Files/specs, SKU count, white-bg vs in-situ photos (drives B-vs-L model + ingest time + back-match mode).
2. **Labeled calibration set** (30–50 known-in-catalog products) available now, or created from the seed? (Blocks Phase 1 step 5 threshold calibration.)
3. **Demand-first scope:** full supplier catalogs, or only SKUs the seed BOM touches? (Decides whether Tiers 2–3 + most enrichment are needed for v1.)
4. **First paying customer:** designer/dealer (SaaS) or GCC occupier + fit-out contractor (B2B project)? (Affects sequencing.)
5. **Canonical HSN→GST table** for furniture/decor/lighting/textiles/plants — needed before deriving any GST.
6. **Per-product enrichment cost ceiling** for the seed batch (sets Gemini vs Haiku vs Opus aggressiveness; whether Batches is mandatory).
7. **Residential-proxy budget** for the handful of JS+WAF SPA suppliers, or defer them under free/local-first?
8. **Anthropic API key** for the enrichment Claude path (add to `backend/.env` at Phase 1.5).
9. Verify **Pixela.ai** exists (named as competitor; did not surface in research) — drop if unconfirmed.

## Top risks

1. `torch`+`open_clip` install on Py3.13/Apple-Silicon; MPS inference ~1 img/sec — verify wheels + one embed before committing; embed at ingest only, never per-request.
2. Confidence thresholds are dataset-specific — re-derive on India data; gate on absolute cosine, not softmax.
3. Material/finish is the weakest harvest field — `basis`/`source` flags mandatory.
4. GST never in source — derive from HSN, flag `estimated`; wrong rate corrupts Specify BOM.
5. Catalog cold-start: only ~16/95 suppliers list INR; long tail WAF/PDF/quote-only → high "no match" rate hurts Explore UX. Catalog is the bottleneck.
6. Legal: public product harvest low-risk (DPDPA public-data exemption), but mass-scraping IndiaMART/Justdial + redistributing scraped pricing is riskier — keep vendor bootstrap manual; legal read before productizing redistribution.
