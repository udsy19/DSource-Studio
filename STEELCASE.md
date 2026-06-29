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

## Proof-of-ingest findings (2026-06-28, 29 application 2D DWGs)

Ran the real Steelcase 2D DWGs (`APL*_PLAN.dwg`, e.g. APL00122 Private Office – Leadership)
through `cad_reader`. Two results:

1. **A real robustness bug found + fixed (kept).** `cad_reader` read DWG→DXF via `ezdxf.recover`
   only, which silently returns an **empty** modelspace for some real-world exports (incl. these),
   while the strict `ezdxf.readfile` reads them fine (and vice-versa for others). Added
   `_read_dxf_doc` — try both, keep whichever yields the most entities. The user's own plate still
   extracts 617 furniture; 189 backend tests pass. General CAD-reading win, independent of Steelcase.

2. **The Steelcase files are Configura CET exports, and LibreDWG can't convert them cleanly (BLOCKER).**
   Each furniture item is an anonymous block (`*C1..*C41`) on layer `A-FURN`/`CET Default`, carrying
   the geometry **and 130 ATTDEFs (the SKU/spec attributes)** — exactly what we want. BUT LibreDWG's
   `dwg2dxf` **truncates the modelspace INSERT references to `*C`** (dropping the digits), so they no
   longer resolve to their `*C{n}` definitions — geometry + placement can't be recovered. Confirmed
   across every output version (r14/r2000/r2010/r2013): `resolved=0`. So the payload is rich and the
   idea is sound; the only blocker is the converter.

### The unlock
Use a proper DWG→DXF converter that preserves anonymous-block references:
- **ODA File Converter** (free from the Open Design Alliance) — the standard fix; macOS GUI install.
  Next step: install it, then wire `_dwg_to_dxf_bytes` to prefer ODA and fall back to LibreDWG.
- or Autodesk DWG TrueView, or export from Configura CET / Steelcase in **DXF** directly.
Once converted cleanly, `cad_reader` should yield each application's furniture footprints + SKU
attributes — and the "applications as building blocks" plan proceeds.

## PROVEN with ODA File Converter (2026-06-28)

Installed ODA File Converter and wired `_dwg_to_dxf_bytes` to prefer it (LibreDWG fallback). It
preserves the anonymous-block linkage LibreDWG destroyed — **all 39 INSERTs in APL00122 resolve to
their definitions**. The applications now ingest, and each spec'd item carries its full product data
in CAP* block attributes:

```
*C32  CAPPD="Steelcase Series 2; Chair-Upholstered back"  CAPPN=436UPH
      CAPMG=Steelcase  CAPPL=$1,409.00  CAPQT=1
```

`cad_reader` now reads those attributes (`_cet_spec`): an anonymous `*C{n}` block resolves to a
**categorized, branded, SKU-tagged** FurnitureItem (category from CAPPD, brand=CAPMG, model=CAPPN,
name=CAPPD) — e.g. `[chair] Steelcase 442A40 — Gesture; Chair`, `[table] Steelcase OBBORDER05`. The
user's own plate is unaffected (still 617 items; locked by `test_cad_reader.py`). Across the 29 apps,
95 items carry full spec (the rest are geometry sub-parts). **The idea is validated end-to-end.**

### Still on the table (the BOM gold)
`CAPPL` (list price) + `CAPQT` (qty) are right there in the attributes. `FurnitureItem` has no price
field yet — adding one (or a parallel BOM extract) turns every ingested application into a **priced
bill of materials**, directly feeding Specify-mode quoting.

### Next: settings library + generator slotting
With clean ingestion proven, build the `settings` store (setting_type, sqft, footprint, furniture[]
with SKU+price, source_app_id) from these apps, then slot a matching application into each generated
program room. (Licensing gate still applies before harvesting at scale — these were specifier
downloads for a private proof-of-concept.)

## Proposed first step

Download 2-3 *Private Office* + *Workstation* applications as DWG and run them through `cad_reader` to
confirm they yield clean room + SKU-tagged furniture — and from that real output, decide the settings
library schema. Zero scale, zero redistribution, proves or kills the whole idea in one afternoon.
