# Steelcase as a catalog-backed building-block source

Branch: `steelcase` · Status: **ideation** (no commitment to scale until licensing is cleared)

## The opportunity in one line

Steelcase publishes two things we lack: **(1) a curated library of complete, professionally-designed
room "applications"** at known setting-type + square-footage, and **(2) thousands of real product CAD
models** with true geometry + SKU. Both are exactly what our generator is missing today — it places
*parametric placeholder boxes* (a `private_office` is a 10×12 rectangle with a synthesized desk), when
it could place *real, vendor-validated rooms made of real furniture*. This is the project's north star:
**the structured, catalog-backed scene is the source of truth.**

## Two assets, two uses

| Source | What it is | Use |
|---|---|---|
| [space-planning-ideas](https://www.steelcase.com/resources/space-planning-ideas/industry/workplace/) — "applications" (e.g. *Private Office – Leadership – APL00122*, *Conference Room – Hybrid Boardroom – APL00127*, *Two-Pack Workstation – APL00123*) | A **complete furnished SETTING** at a known setting-type (Private Office, Meeting, Workstation, Café, Focus Room…) and sq-ft band (0-250 / 251-500 / …), downloadable as CAD | **Generative building blocks** — slot a real setting into each program room instead of synthesizing a box |
| [3d-models-cad](https://www.steelcase.com/resources/3d-models-cad/) — individual products (Table, Worksurface, Seating, Screens, Storage, Panel…) | A real **SKU** with true geometry + dimensions | **Real 3D geometry**, **exact BOM/takeoff**, and the **back-match catalog** |

## The elegant reuse (why this is cheap to start)

The applications **download as CAD (DWG/DXF)**, and our existing `backend/app/ingestion/cad_reader.py`
already turns a DWG into an `ExtractedLayout` — **rooms + furniture, with the Steelcase SKU carried in
`FurnitureItem.block_name`/`brand`/`model`**. So *the same reader that parses a user's plate parses a
Steelcase application into a reusable, SKU-tagged furnished-room template.* We already have the ingestion.

## Ranked uses (highest leverage first)

1. **Application-driven generation (headline).** The generator picks the program (X offices, Y meeting
   rooms, Z workstation pods), then for each room **slots in a matching Steelcase application** (by
   setting-type + footprint) instead of a parametric box. Output: test-fits built from real,
   vendor-validated rooms with real furniture — instantly realistic *and* BOM-ready.
2. **Real BOM + price (Specify mode).** Each application/product carries real SKUs → exact quantity
   takeoff, and (with a price list) a real quote. Directly serves the Specify half of the engine.
3. **Real 3D geometry.** Convert product CAD → GLB; render real furniture in 3D instead of procedural
   boxes. The genuine path to hyper-realism (vs. our current box approximations).
4. **Explore back-match target.** Embed Steelcase product images/CAD (CLIP) → one of the real catalogs
   the Explore-mode back-match resolves AI-generated elements against.

## Build path (phased, each step verifiable)

1. **Proof-of-ingest** — manually download 2-3 applications (Private Office + Workstation, DWG) and run
   them through `cad_reader`. Prove they parse into clean `ExtractedLayout`s with real SKU block names.
   *This also reveals the real download format + whether the SKU naming is usable.*
2. **Settings library** — from (1), define a small `settings` store: `{setting_type, sqft, footprint,
   furniture[] (SKU + pose), source_app_id}`. Ingest a starter set per setting-type.
3. **Slot into generation** — wire the test-fit generator to place a matching application into one room
   type first (e.g. private office), behind a flag, alongside the existing parametric path.
4. **Real takeoff** — surface the application's SKUs in the quantity takeoff for slotted rooms.
5. **Later** — product GLBs for 3D; CLIP embeddings for back-match.

## Risks / gating (decide before harvesting at scale)

- **Licensing — the gate.** Steelcase CAD/applications are published for *design/specification* use.
  Powering a commercial generative product with them needs reviewing Steelcase's Terms of Use (and
  likely a conversation with them / a dealer). **Do not scrape at scale before this is cleared.** A
  handful of files for a private proof-of-concept is a different risk class than redistribution.
- **Formats.** Downloads may be DWG / Revit `.rfa` / SketchUp `.skp` / pCon. Our reader handles
  **DWG/DXF**; `.rfa`/`.skp` need conversion; **pCon/OFML is the licensing wall we already avoid**
  (see `memory.md` → SIF data path). Target the DWG/DXF downloads first.
- **India-first.** The product is India-first (`data/india/manufacturers.csv` = 95 vetted India
  suppliers is the primary catalog). Steelcase is **US/global** → a complementary catalog track on the
  same engine ("architected to expand"), not a replacement for the India catalog.

## Proposed first step

Download 2-3 *Private Office* + *Workstation* applications as DWG and run them through `cad_reader` to
confirm they yield clean room + SKU-tagged furniture — and from that real output, decide the settings
library schema. Zero scale, zero redistribution, proves or kills the whole idea in one afternoon.
