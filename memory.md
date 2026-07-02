# DSource AI — Memory (living state)

The single source of truth for *current* state: locked decisions, status, what's real vs synthetic, open questions. Updated as work lands. Companion to `CLAUDE.md` (rules) and `ROADMAP.md` (plan).

_Last updated: 2026-07-02._

## Studio (qbiq-clone) — active phase (branch `floorplan-editor`)

The Studio/test-fit track (semantic scene editor: locked underlay + editable zones/partitions/doors/placements, command API `/api/scene/*` with invariants, 671-plate Steelcase library, program-as-scoreboard, localStorage `editedDesigns[]`, Tier-0 variant scoring in `scoring.py`). Phase-2 plan = five workstreams A–E (Canva-feel on-canvas editing, Submit→Results→Editor IA, program anchor pins, N-candidate generation, agent-critic R&D).

- **Workstream A DONE (on-canvas interaction model).** Every persistent edit is still one validated command via `/api/scene/apply`; local transforms during a gesture are ephemeral (optimistic), server scene is the source of truth.
  - A0: rotate grip bug fixed — a bare click did pointerdown→up with no move, so `rotating` stayed null and the pointerUp guard dropped the command. Now bare click = +90° detent; drag preview snaps to 45° (WYSIWYG with backend `_snap_45`).
  - A2: item drag clamps to its zone bbox client-side (UX hint; server `clamp_local_into_zone` stays authority); selected item eases to committed pose so a server settle / rejected-command snap-back reads as motion.
  - A3: doors slide along their host wall (offset clamped to `[0, len−width]`, the jamb bound mirroring `EditDoor`) and flip via an on-canvas ⟲ grip — one command each. DoorPanel slimmed to a recap (nudge/flip buttons removed).
  - Gizmo delete bug found+fixed by the acceptance run: the delete affordance didn't `stopPropagation` on pointerdown, so canvas pan-capture ate the click.
  - Frontend has **no test runner** (no vitest/jest) — per the phase rule, frontend changes are guarded by Playwright browser verification, not unit tests. Standing up vitest is a deferred, separate decision.
- **Next:** Workstream B (Submit→Results→Editor IA restructure) — replaces the Review wizard step, the `Resume editing` dashboard side-door, and the modal editor entry. Then C/D (anchor pins, N-candidate generation), then E (agent-critic, offline/gated).

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
- **Phase 1 COMPLETE (catalog + embeddings, end-to-end on real data):**
  - ✅ Dep gate: torch 2.12.1 + open_clip 3.3.0 + transformers 5.12.1 + sqlite-vec 0.1.9 + curl_cffi 0.15.0 + apsw 3.53.2 on Py3.13/arm64. **Gotcha:** stdlib `sqlite3` here lacks loadable extensions → `sqlite-vec` attaches via **apsw** (same `dsource.db`; SQLAlchemy keeps the stdlib driver for the ORM).
  - ✅ Harvest: `app/harvest/` Tier-0 Shopify (curl_cffi client, pure parser, `upsert_harvest`). **Live-seeded ~749 real India products** (Nilkamal 250, TrustBasket 250, Ugaoo 249) with INR prices via `scripts/harvest_seed.py`.
  - ✅ Embeddings: `app/embeddings/` (marqo-ecommerce-B embedder + SqliteVecIndex over apsw, cosine). 120 indexed.
  - ✅ Match: `POST /api/match` (text/image → ranked real products + honest exact/close/no_match). Retrieval ranking is GOOD (text "mesh office chair" → the real Nilkamal mesh chairs; gibberish → no_match).
  - **KEY FINDING — modality gap:** text↔image cosines (~0.12 for correct) sit FAR below image↔image (~0.5–0.9). So bands are calibrated PER MODALITY: text exact 0.16 / close 0.10 (from seed: true-match median 0.124 vs wrong p90 0.103); image exact 0.85 / close 0.72 (conservative — image calibration is category-noise-polluted, needs cleaner signal). In `config.py`.
  - Bugs found+fixed by the live run (both now regression-tested): manufacturer re-insert under autoflush=False (flush in `resolve_manufacturer`); same-SKU size-variants colliding in one batch (in-batch dedup in `upsert_harvest`).
- ✅ **Phase 1 polish done:** `calibrate_bands` now picks the best balanced-accuracy threshold per modality and reports TPR/TNR (seed: text BA 0.81, image BA 0.83); config bands set from it (text 0.13/0.08, image 0.80/0.68). `infer_category` broadened (lighting/planters/decor). Harvest now captures stripped `body_html` as `description` (feeds enrichment).
- ✅ **Phase 1.5 enrichment done:** `app/enrichment/` — one Pydantic `MaterialEnrichment` (value/confidence/source per attr, 'missing' explicit) drives both providers via SDKs (anthropic 0.111, google-genai 2.9). `decide_provider` novelty-gates (near-dup of an enriched product → Gemini; novel → Claude); content-hash cache; resilient provider fallback. **Live-verified on real products via Gemini** (e.g. plastic/engineered-wood with honest image/title/inferred source). 8 unit tests (fakes). CLI: `scripts/enrich_seed.py`.
- ⚠️ **ANTHROPIC_API_KEY is truncated** (confirmed: live Claude calls 401 → fall back to Gemini). Re-paste full key in `.env` to enable the novel-item Claude path; Gemini path works now.
- **GST:** no canonical HSN table → `derive_gst(category)` (furniture 18% etc.), always flagged estimated.
- ✅ **Phase 3 Specify material-swap done:** `CadViewer.tsx` palettes drive the 3D finishes live AND resolve each to a real SKU via `/api/match`. Materials BOM sums matched SKUs + GST and shows material + maintenance per line.
- ✅ **Phase 2 material→maintenance done:** `app/materials/` pure `derive_material_attributes()` over a 20-family standard-backed table (6 axes, basis enum). `material_family_from()` maps freeform material text → table key (specific-before-generic; unmappable → None). Wired into `/api/match` results (`material`, `enrichment`, `maintenance`).
- ✅ **Catalog broadened (fills Floor/Wall):** +8 verified INR Shopify brands — Imperial Knots/Obeetee (rugs→Floor), Giffywalls (wallpaper→Walls), Oorjaa/FIG/Purple Turtles/Decor Kart (lighting), Marshalls (wallpaper). Seed now per-brand-indexed (45 each, 7 brands) + resilient to a flaky domain. Floor→Obeetee rugs (₹12.6k–283.5k), Wall→Giffywalls wallpaper (priced after `_primary_variant` skips ₹0 sample variants). Furniture→Nilkamal.
- **Parallel agents used (2026-06-24):** 3 concurrent (Phase 2 build · catalog research · match-API exposure) — disjoint files, integrated + committed individually.
- ✅ **Bulk enrichment done (Gemini):** all **390 indexed products enriched** via `scripts/enrich_seed.py` (now index-driven — enriches exactly what's matchable; content-hash cache skips before fetch). Match results carry material + maintenance: e.g. mesh chair → dust 4/5·wipe 5/5, engineered-wood table → dust 2/5·wipe 4/5. Surfaced in the swap-panel BOM.
- ⚠️ **Claude key STILL truncated** (77 chars vs ~108, 401, paste cuts at `…eHHmMx`). All enrichment routed to Gemini via fallback. To enable the Claude novel-item path the user must paste the FULL key (suggested: `! read -s` into .env, or a fenced code block). Gemini occasionally mislabels material (e.g. "Lantana" for a lamp) — carries source/confidence so not silently faked; Claude would improve novel-item accuracy.
- **Honest gaps:** wool/viscose (rugs) and bare "walnut wood" don't map to a maintenance family → material shows, scores blank. tiles/paint/vinyl remain quote-only (no priced India source).
- ✅ **De-mocked the Studio sidebar (2026-06-24):** removed the legacy US-dealer USD quote + Herman Miller/Knoll BOM + synthetic US vendors. New `/api/source/india` (`routers/source.py`, `build_india_source`) maps the test-fit furniture program → real Nilkamal SKUs via the match engine → INR BOM + GST (sample plate: 282 desks+chairs etc. → **₹1.02 cr**, 0 unmatched). Studio renders it; deleted orphaned `Procurement.tsx` + dead api/types (`usd`, `requestRfq`, `createPo`, `Po`/`VendorBid`/`RfqResponse`). Note: backend testfit still COMPUTES the US quote/bom (now unrendered, legacy, has tests) — real India vendor comparison is Phase 5.
- **Still mock-ish but honestly-flagged (kept):** Wellbeing panel (light/acoustics/movement/social measured from geometry; others ≈ proxies). Test-fit stats are real geometry.

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
