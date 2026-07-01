# 04 — Build Plan, Gaps & Research

How we turn the qbiq workflow into our product. The good news: the **engine is ~built**; the gap is
mostly **the guided pipeline shell, a few CAD-stage interactions, and deliverable breadth**.

## What already exists (reuse — do not rebuild)

| Capability | Where |
|---|---|
| CAD/DWG/PDF ingest → `ExtractedLayout` (walls/doors/rooms/furniture, feet) | `floorplan/dxf_ingest.py`, `ingestion/cad_reader.py`, `routers/ingest_cad.py`, `floorplan_raster.py` |
| **Label-seeded room segmentation** + per-room `boundary_basis`/`confidence` | `ingestion/room_segment.py` |
| Procedural test-fit + **3 variants A/B/C** + concept/detailed modes | `testfit/{layout,rooms,zones,alternatives,concept,detailed}.py` |
| Metrics: usf/seats/open/enclosed/density/**daylight%/privacy%/efficiency%** | `testfit/metrics.py`, `ingestion/layout_metrics.py` |
| Steelcase **Settings** library (furnished rooms → furniture layouts source) | `testfit/settings.py`, `routers/library.py` |
| Editable canvas: move / delete / **furniture+room swap** / live re-score / color-coding | `frontend/src/components/PlanCanvas.tsx`, `Studio.tsx`, `/api/layout/metrics` |
| Program editor: category ± steppers + live summary | `Studio.tsx` `DetailedProgramEditor` |
| Render proxy (Flux/Gemini) + finishes→prompt + finishes UI | `routers/render.py`, `Studio.tsx` `FinishesPanel` |
| Exports: DXF · IFC/BIM · Excel takeoff · PDF report · priced BOM/quote (currency-aware) | `testfit/dxf_export.py`, `ifc/`, `takeoff/`, `routers/report.py`, `pricing/engine.py`, `testfit/bom.py` |
| Projects CRUD | `routers/projects.py`, `procurement/models.py` |
| Design system (warm paper / ink / terracotta / Fraunces+Inter) | `frontend/src/design/` |

## The real gaps (ranked)

1. **The guided pipeline shell** — replace the two-mode toggle with one left-rail stepper
   (Property → Space → Program → Visualization → Summary → Generate) + a **Projects dashboard** home
   with Draft/Processing/Ready states. *This is the "it feels broken" fix.*
2. **Space stage interactions** — (a) **mark planning-area polygon** (clip the plate), (b) **drag room
   markers** (IT/Pantry/WC/Entrance/Stairs/Outdoor) as **segmentation seeds**, (c) infer bathrooms/cores,
   (d) **keep-walls** toggles.
3. **Studio editor depth** — room **property panel** (dept/area/headcount/dims/open-enclosed),
   **furniture-layout palette** per room type, **merge rooms** + context suggestion, **change-room-type**
   panel, **rotate** + **door edit**, **program tree** with actual/target.
4. **Program stage** — planning style / desk type+size / seat-split controls; live **% + density**
   summary pre-generate; **preferred-location** soft constraint; custom-room add.
5. **Visualization depth** — per-space material sets (ceiling/floor/wall/partition/door), theme gallery,
   live per-room render preview, facade/ceiling-height/client-logo/virtual-tour setup.
6. **Deliverables breadth** — page-selectable PDF with the qbiq page set (cover, 3D-tour, per-alt
   test-fit, comparison table + radar + space-mix), Program Summary XLS, Rendered-Photos ZIP, PNG,
   **QR → hosted 3D tour**, version dropdown, per-design Plan Files modal.
7. **Async generation as a job** — Processing→Ready status, not synchronous.
8. **Hard/deferred** — **Revit .RVT** (needs Revit/APS bridge; keep IFC), true real-time 3D walkthrough
   video (qbiq renders a hosted tour), multi-floor.

## Phased build order (each phase = branch + tests + in-browser verify)

- **Phase A — Pipeline shell & Projects home.** Left-rail stepper + Projects dashboard + Draft/
  Processing/Ready + resumable wizard. Wire existing Space/Program/Generate screens into it. *Biggest
  perceived-quality win; unblocks everything.*
- **Phase B — Space stage.** Planning-area polygon + room-marker seeds (into `room_segment`) +
  keep-walls + bathroom/core inference surfaced.
- **Phase C — Studio editor depth.** Property panel + furniture-layout palette + change-room-type +
  merge + rotate + door edit + program tree actual/target.
- **Phase D — Program + Visualization depth.** Style/desk/seat controls + live %/density + preferred
  location; per-space finishes + theme gallery + live render.
- **Phase E — Deliverables.** qbiq report page set + Program Summary XLS + ZIP/PNG/QR + versioning +
  Plan Files modal.
- **Cross-cutting — UI robustness & design adherence.** Audit every screen against `frontend/src/
  design/` tokens (no stray colors, Fraunces numerals everywhere, terracotta-only accent, a11y focus
  states), loading/empty/error states, and the honest-data discipline (`{value, confidence, basis}`).

## Research questions (how qbiq does it — to inform our build)

- **Room detection / classification** from arbitrary CAD: qbiq nails it on curved/gappy plates. Our
  label-seeded watershed is the analog; study whether they use trained models + a big plan corpus
  (their marketing says "hundreds of millions of sq ft") vs deterministic. We stay deterministic +
  catalog-grounded, honest about confidence.
- **Generation**: qbiq = generative + optimization + ML on a plan corpus. We = constraint/heuristic
  placement over the real catalog (WeWork-style procedural is proven). Where does ML help us later?
- **Furniture-layout library**: qbiq has many pre-composed arrangements per room type. Ours must come
  from the Steelcase Settings library — audit coverage per room type; fill gaps.
- **Preferred-location constraint**: how strongly to weight a user's dragged placement (soft vs hard).
- **3D tour hosting**: qbiq hosts a walkthrough behind a QR (`view.qbiq.ai/viewer`). Our render is
  still-image; a hosted tour is a later, heavier build (start with a render carousel + QR to it).
- **Revit/APS**: the one true infra gap for `.RVT`. Evaluate Autodesk Platform Services vs staying IFC.

## Non-negotiables carried from CLAUDE.md

- Structured catalog scene is the source of truth; AI is the beauty layer.
- India-first: INR + GST; Indian vendors; default Metric with Imperial toggle.
- Never fabricate — every metric/price/room carries `{value, confidence, basis}`; no-match is flagged.
- One design system (`frontend/src/design/`); no new visual language; warm paper + terracotta, not
  qbiq blue.
- Keep tests green; add tests per new module; commit per change; no bloat.
