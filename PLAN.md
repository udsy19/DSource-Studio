# DSource — End-to-End Build Plan

**Product:** A dealer-facing SaaS for US commercial/office interiors. A contract-furniture
dealer uploads a floor plate + a program brief; an AI generates a test-fit (space plan with
furniture placed, respecting clearances/circulation/egress); it produces a bill of materials
and a budgetary quote; the dealer reviews/edits and exports it back into their existing tools
(CET / Spec / ERP) to finalize the firm quote.

**v1 decisions (locked):** dealer-facing · generative test-fit as the AI moat · optimize for a
**1-dealer pilot**.

**Pilot success metric:** on the partner dealer's *historical* projects, (a) our budgetary total
lands within ~10–15% of their real quote, and (b) our test-fit is accepted as a usable starting
point that measurably shortens their pre-sales cycle.

---

## 1. What the research changed (grounding)

Three cross-verified research passes (a 112-agent deep-research run + two focused feasibility
probes). Key load-bearing facts, with the decision each drives:

| Finding | Confidence | Decision |
|---|---|---|
| **SIF** (Standard Interchange Format) is a simple, documented `KEY=VALUE` text format carrying part number (`PN`), mfr code (`MC`), qty (`QT`), list price (`PL`), discounts, options. CET, Spec/ProjectSpec, 2020 Worksheet all **export** it; dealer ERPs (Hedberg, ECi DDMSPLUS) **import** it. Free public spec (Design Manager). | High | **SIF is our primary data ingest + round-trip format.** |
| **pCon.basket** exports priced **Excel/CSV/OBX/OEX**; **OEX** carries full article + purchase/sales pricing. | High | Secondary ingest path where dealer uses pCon. |
| **Raw OFML** catalog/pricing is hard-gated (pCon.update DataClient + per-manufacturer DLM licenses). No open API for raw ingest. | High | **Do not** try to ingest raw OFML. Consume dealer exports instead. |
| Manufacturer **list prices are PDF-only**, exclude planning/design/storage/install. | High | Quote engine = list − discount + install + freight + tax. Pricing comes from dealer's priced exports, not scraping PDFs. |
| Automated office layout is **buildable now** for the narrow case: WeWork's procedural desk-placement matched/beat architects on 77%+6% of ~13,000 real offices (97% under relaxed standards). Constraint-based + rejection-sampling enforces ADA/egress without ML. | High | **Core engine = rules + CP-SAT optimization**, not ML. |
| ML/generative floorplan models (House-GAN, Graph2Plan, diffusion) are **residential + research-grade**, still produce artifacts; furniture placement is a different problem class. | High | ML is a **later enhancement**, explicitly out of pilot scope. |
| Direct competitors **laiout** and **qbiq** exist — office-specific auto-layout, but **closed SaaS, no public API**; **qbiq validates AI output with in-house architects**. | High | Validates the market; **differentiate on dealer-native workflow** (SIF round-trip + BOM + budgetary quote into CET/ERP), and keep a **human-in-the-loop**. |
| Floor-plate ingestion: **vector** (DXF via `ezdxf`+ODA, IFC via `IfcOpenShell`/pythonOCC) is tractable; **raster/PDF vectorization** is moderate-accuracy (IoU ~55–58%), domain-gapped, junction-failure-prone — even CubiCasa keeps humans in the loop. | High | **Pilot requires vector input** (DXF/IFC) + a human "confirm boundary/columns/core" step. Raster/PDF deferred (or CubiCasa API later). |
| Standards numbers: ADA accessible route **36"**, turning **60"**; IBC business occupant load **1 per 150 sf** (2018+); corridor **44"** (≥50 occ); circulation **25–45%**; density **~130–250 RSF/person**. | High | Seed a **configurable** rule module (per code edition/jurisdiction); position output as "test-fit / design aid," not a stamped compliance check. |
| Web 3D is well-supported: **react-three-fiber + three.js + glTF** (`gltfjsx` to convert models); **Konva** for the 2D plan canvas. | High | Frontend stack. |

**The single biggest technical risk:** reliable floor-plate ingestion from messy real-world inputs.
Garbage geometry breaks every downstream constraint. Mitigation: vector-only + human-confirm for the
pilot.

---

## 2. Architecture

```
                         ┌──────────────────────── Dealer's existing world ───────────────────────┐
                         │  CET Designer / Spec / 2020 Worksheet / pCon  ──exports──▶  SIF / OEX    │
                         └─────────────────────────────────────────────────────────────┬───────────┘
                                                                                        │ (their catalog + price book + discount)
  Floor plate (DXF/IFC) ─┐                                                              ▼
                         │                                                   ┌─────────────────────┐
  Program brief ─────────┼──▶  INGEST  ─▶  PLAN MODEL  ─▶  TEST-FIT ENGINE ─▶│  Normalized Catalog │
  (headcount, zone mix,  │   (geometry +   (rooms/zones/   (rules + OR-Tools  │  (mfr, sku, price,  │
   density, code profile)│    confirm)      circulation)    CP-SAT layout)    │   2D footprint,glTF)│
                         ┘                                       │            └─────────┬───────────┘
                                                                 ▼                      │
                                            Placed furniture instances ──map to SKU──▶  BOM
                                                                 │                      │
                                  ┌──────────────────────────────┴───────┐              ▼
                                  ▼                                       ▼     Budgetary quote
                          2D plan editor (Konva)              3D walkthrough (r3f)   (list−disc+install+freight+tax)
                                  │                                       │              │
                                  └────────── dealer edits ──────────────┴──────────────┘
                                                                 │
                                                                 ▼
                                            EXPORT  ──▶  SIF / Excel  ──▶  back into CET / ERP (firm quote)
```

### Stack
- **Backend:** Python + **FastAPI**. Geometry: **Shapely** (clearance/egress offsets via `buffer`),
  **ezdxf** (+ODA File Converter for DWG), **IfcOpenShell**/pythonOCC (IFC). Optimization:
  **Google OR-Tools CP-SAT** (`AddNoOverlap2D`). Async layout jobs: **Celery/RQ + Redis**.
- **Data:** **Postgres** (+ **PostGIS** if we want spatial queries; otherwise store geometry as
  GeoJSON/WKT). Object storage (S3-compatible) for uploaded plates + glTF models + exports.
- **Frontend:** **React + TypeScript + Vite**. 2D plan editor: **Konva / react-konva**.
  3D view: **react-three-fiber + three.js + drei**, glTF furniture via **gltfjsx**.
- **Catalog geometry:** each SKU carries a **2D parametric footprint** (drives layout) and an
  optional **glTF** model (drives 3D view); sourced from manufacturer Revit/SketchUp libraries
  (MillerKnoll, Herman Miller free downloads, BIMobject).
- **Infra (pilot):** single-tenant, containerized, managed Postgres + Redis. Auth: simple
  email/password or magic link (one dealer, few users).

### Core data model (the real intellectual artifact)
- `Manufacturer`, `Product` (canonical on `(manufacturer, sku)`; 2D footprint, clearance zones,
  list price, price UOM, glTF ref) — **keyed off canonical part numbers, no fuzzy matching**.
- `PriceProfile` (dealer's discount band per manufacturer/line, install rate, freight, tax).
- `Project` → `FloorPlate` (boundary, columns, core, scale) → `Program` (zone targets) →
  `TestFit` (placed `FurnitureInstance`s + zones + circulation) → `BOM` → `Quote`.
- `IngestJob` (SIF/OEX import provenance).

---

## 3. Build phases (sequenced to de-risk; each phase ends at a gate)

### Phase 0 — Data spine: ingest → catalog → budgetary quote  *(highest certainty, immediately useful)*
Rebuild the scrapped data/quote layer **properly, around SIF as the real format.**
- **SIF parser/writer** (the production primitive): parse `KEY=VALUE` records → normalized line items;
  handle the major flavors; round-trip back out. Also a **pCon Excel/OEX** ingest adapter.
- **Normalized catalog** upsert keyed on `(mfr, sku)`; load the partner dealer's catalog + price book.
- **Budgetary quote engine:** `list × (1 − discount) + install + freight + tax`, labeled budgetary,
  with the dealer's real discount bands.
- **API + minimal UI** to import a SIF, see the catalog, build a line-item list, get a quote.
- **Real-data connectors** (no mock data — see `docs/data-sourcing.md`): instead of relying on a
  signed dealer, assemble real data from public sources that feed the *same* catalog/SIF schema —
  (1) manufacturer **price-book PDF parser** → real list prices + part numbers; (2) **GSA Advantage**
  headless scraper → part# + GSA net price; (3) **co-op** (Sourcewell/NASPO) discount bands. The
  dealer's SIF/OEX export stays the eventual *gold* source. Synthetic data is now just test fixtures.
- **▣ Gate A:** reproduce a *known project's* BOM + budgetary total within ~10–15% of the actual
  quote — first on synthetic fixtures (DONE: 5.0% delta), then on real data once connectors land.
  *This proves the data thesis.*

### Phase 1 — Floor-plate ingestion + program intake + plan model
- **Vector ingest:** DXF (`ezdxf`) and IFC (`IfcOpenShell`) → extract boundary, columns, core, rooms.
- **Human-confirm step:** dealer reviews/corrects the extracted boundary/columns/scale (mitigates the
  #1 risk). Output: a clean internal **plan model** (polygons + scale, in real units).
- **Program intake form:** headcount, zone-mix ratios (workstations / private offices / meeting /
  collaboration / amenity), density target (RSF/person), code profile (ADA + IBC edition).
- **2D plan editor (Konva):** render the plate, let the dealer draw/adjust zones manually.
- **▣ Gate B:** ingest a real plate the dealer has fit before; our extracted geometry + manual zoning
  reproduces their usable area / seat-capacity envelope within tolerance.
  *Status: backend DONE — `app/floorplan/` ingests DXF (boundary/core/columns/usable area via
  ezdxf+Shapely) + capacity engine; `POST /api/floorplan/ingest`. Gate B passes on a real-format
  fixture (recovers 8,100 sf gross / 7,500 usable / 8 columns exactly). Still to do: IFC ingest,
  the 2D Konva confirm/zone editor (frontend), and validation on a real dealer plate.*

### Phase 2 — Generative test-fit engine v1  *(the moat, riskiest core)*
- **Zone blocking:** assign program areas to regions of the plate (objective: adjacency + daylight +
  circulation spine; constraints: fit, egress access).
- **Furniture placement within zones** via **OR-Tools CP-SAT** (`AddNoOverlap2D`): workstation grids,
  meeting rooms, offices — with **hard constraints** (ADA 36"/60", egress/corridor widths, column
  avoidance) and an **objective** (target density, adjacency, aisle regularity). Use **Shapely**
  offsets for clearance/egress checking; **rejection sampling** for constraints CP-SAT can't express.
- **Start narrow:** open-plan workstation fields + a handful of room types; expand typologies after.
- **Always human-editable:** output is a *starting* layout the dealer drags/tweaks (qbiq/CubiCasa
  pattern), not an autonomous final.
- **▣ Gate C:** on the dealer's real floor plates, auto-generated seat count / program mix matches
  their actual design within an agreed margin on a majority of test cases.
  *Status: v1 DONE — `app/testfit/layout.py` places an open-plan workstation field via procedural
  grid + Shapely constraint filter (containment, perimeter setback, core/column clearance, aisles,
  no-overlap — the WeWork-validated method). `POST /api/testfit`. Gate C passes geometrically (117
  desks on the fixture, all valid, 0 overlaps). Next: cross-aisle egress + rooms/offices via CP-SAT.*

### Phase 3 — Test-fit → BOM → quote + review UI (2D/3D)
- **Placement → SKU mapping → BOM:** each `FurnitureInstance` resolves to a catalog SKU; aggregate to BOM.
- **Live budgetary quote** updates as the dealer edits placements/quantities.
- **3D walkthrough:** react-three-fiber renders placed glTF furniture for the client-facing visual.
- **▣ Gate D:** end-to-end — plate + program in, edited test-fit + BOM + budgetary quote out, in one session.
  *Status: DONE end-to-end. Backend `POST /api/testfit/quote` chains plate → MIXED test-fit
  (workstations + offices + meeting rooms + collaboration) → per-type BOM → budgetary quote
  (fixture: 89 ws + 4 offices + 1 meeting + 1 collab → $176,613.60). Frontend `frontend/` — a
  minimal "test-fit studio" (React/Vite/TS): drop a .dxf → SVG plan renders, instances tint by
  type, panel shows areas/counts/budgetary total/BOM. Full stack verified live via `run.sh`.
  Still to do: in-browser placement/qty EDITING, 3D (r3f) review, IFC/raster ingest, CP-SAT packing.*

### Phase 4 — Round-trip export + pilot hardening
- **Export SIF / Excel** of the final BOM so the dealer pulls it straight into CET / their ERP to
  produce the *firm* quote — this is the differentiator vs laiout/qbiq (dealer-native, not a silo).
- **Pilot hardening:** auth, the one dealer's data loaded, error handling, basic telemetry on
  time-saved. Run live on real incoming projects.
- **▣ Gate E (pilot):** the dealer uses it on a *live* deal and it shortens their pre-sales test-fit +
  budgeting time vs their current CET-only flow.

---

## 4. Explicitly OUT of pilot scope (named, to prevent silent scope creep)
- Raster/PDF floor-plan vectorization (vector-only for pilot; CubiCasa API or in-house model later).
- ML / generative-AI layout (House-GAN/diffusion) — rules + optimization only.
- Multi-tenant, billing, broad manufacturer licensing / pricing redistribution.
- Stamped code-compliance certification (output is a design aid).
- Photoreal AI render (commodity API; add later if wanted).
- Raw OFML / pCon.update integration; becoming a Configura/CET partner.

---

## 5. Top risks & mitigations
1. **Messy floor-plate ingestion** → vector-only + human-confirm; defer raster.
2. **Layout quality / trust** → narrow typologies first, human-editable output, benchmark vs the
   dealer's real projects (Gates B/C).
3. **Pricing/catalog data licensing** → pilot consumes the *dealer's own* exports (their entitlement);
   legal read on redistribution **before** multi-dealer or productized pricing.
4. **Competition (laiout/qbiq)** → win on dealer-native round-trip (SIF → CET/ERP) + budgetary quote,
   not on the render.
5. **Code-compliance correctness across jurisdictions** → configurable rule set per edition; AHJ
   disclaimer.

---

## 6. GTM — landing the pilot dealer (parallel to Phase 0/1)
- **Target:** a mid-size, hungry independent contract-furniture dealer (≈10–50 people) with one
  overworked CET designer doing pre-sales test-fits. Not a big dealer (they have design teams and
  move slowly).
- **Find them:** manufacturer "find a dealer" locators (Steelcase/MillerKnoll/Haworth) per metro;
  LinkedIn for the principal/sales lead; warm intros via CRE brokers.
- **The ask (design partner, not a sale):** *"I'm building a tool that turns a floor plate into a
  test-fit + budgetary quote in minutes. Can I validate it on your real projects? You get early
  access and shape the product."* In exchange we need: their **catalog + price book** (SIF/pCon
  export), their **discount bands**, and **2–3 historical projects** (plate + final BOM + quote) to
  benchmark Gates A/C.
- **Value prop to them:** faster pre-sales → chase more deals; spend the CET designer's time only on
  deals that convert.

---

## 7. Recommended starting point
**Build Phase 0 first.** It's the highest-certainty, immediately-useful slice (SIF ingest → catalog →
budgetary quote), it proves the data path on the dealer's real data (Gate A), and it's the foundation
everything else feeds. The AI test-fit (Phase 2) is the moat but also the riskiest — we want the data
spine solid and a design-partner dealer's real exports in hand before we build it.

---

### Appendix — source pointers (selected, verified)
- pCon.basket export formats — easterngraphics.com/pcon/en/2025/01/29/an-overview-of-export-formats-in-pcon-basket/
- pCon OEX (priced order exchange) — basket.wiki.pcon-solutions.com (export_oex)
- OFML gating (DataClient/DLM) — update.easterngraphics.com/doc/help/dc/en/co_installcompofml.html
- SIF spec (free, public) — knowledge.designmanager.com (SIF file specification)
- WeWork procedural desk layout — journals.sagepub.com (Anderson et al., IJAC 16(2), 2018)
- Constraint + rejection-sampling layout — arXiv:1711.10939
- Floor-plate ingestion (IfcOpenShell/pythonOCC; raster→vector) — academy.ifcopenshell.org ; arXiv:2306.01642 ; arXiv:1904.01920 (CubiCasa5K)
- ADA clearances — access-board.gov (chapters 3–4); IBC occupant load — codes.iccsafe.org (Ch.10)
- Pricing (list excludes services) — hermanmiller.com GSA price books
- Competitors — laiout.co ; qbiq.ai ; OR-Tools CP-SAT AddNoOverlap2D
- Web 3D — react-three-fiber docs ; github.com/pmndrs/gltfjsx ; konvajs.org
