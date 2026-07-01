# 02 — Review & Studio Editor (post-generation)

After Generate, the project goes **Ready** and produces **3 verified test-fits** plus any user-edited
copies. Opening one loads the **Studio editor** — the interactive, re-scoring, editable canvas.

---

## Design Alternatives grid  ·  `reference/39`

**qbiq does.** `.../project-details/.../design-alternatives`. Two sections:
- **qbiq verified** — **Design A / B / C** cards (color-coded plan thumbnails, "Created on …").
- **Edited designs** — "Copy of Design A" cards the user has forked and modified (avatar chip shows
  who edited). Each card opens the Studio editor.

**We build.** A Review screen listing the 3 generated variants + edited copies. Clicking → Studio.
Fork = "Duplicate and Edit in Studio."

**Our codebase.** `testfit/alternatives.py` gives A/B/C; persist edited copies against the project.

---

## The Studio editor  ·  `reference/40–45`

`plan.qbiq.ai/studio/.../testfit/<id>/design/<designId>`. Named "Copy of Design A" (rename inline).
Top-right: **Analyze Design**, undo/redo.

### Left rail — Metric + Program tree  ·  `ref 40`
- **Metric**: **Work seats** (98) with an **Open (85) / Enclosed (13)** split bar; **Density (ft²/seat)**
  140.47. Re-scores live on every edit.
- **Program** tree: Office · Open Space · Conference · Reception · Pantry · Support Area · Amenities ·
  Other — each expands to its room rows with **actual / target** counts (e.g. "Medium > 8-10 People
  4 / 2", "Board Room > 18-30 People 1 / 1", "Locker 2 / 30"). Over/under-target is visible.

### Canvas — color-coded test-fit
The full plan, rooms filled by department family over the CAD base (qbiq's legend: Executive, Office,
Open Space, Conf Room, Reception, Pantry, Amenities, Comfort Zone, IT Room). Bottom toolbar:
select / measure / dimension / align tools, zoom %, scale bar.

### Right panel — selected element  ·  `ref 41`
Select a room → panel shows **Department**, **Area (ft²) actual / target** (e.g. 361 / 240),
**Headcount** actual/target (14 / 12), **Dimensions (feet) L×W**, an **Open / Enclosed** toggle, and a
**Furniture** section with **Layouts / Items** tabs — a grid of **furniture-arrangement thumbnails** for
that room; click one to swap the room's furniture layout.

### The power interactions
- **Merge rooms** (`ref 41`): select two adjacent rooms (e.g. two conference rooms), **delete the wall/
  one room**, and they become **one larger space**. qbiq then **suggests it's now a closed space needing
  a bigger table** and surfaces the matching table options → a *context-aware furniture recommendation*.
- **Change Room Type** (`ref 42`): a searchable panel — "Support Area > Locker", "Conference > Focus
  Room", "Office > Executive", "Amenities > Training Room"… — retype any room; area/headcount targets
  update.
- **Swap furniture layout** (`ref 43,44`): the Layouts tab offers many arrangements per room type
  (e.g. Collaboration cluster variants); Items tab swaps individual pieces.
- **Move / rotate / edit doors** (`ref 42–45`): drag elements, **rotate in real time**, and edit
  **door position + swing direction**. Delete via the floating room toolbar (`ref 45`).
- **Analyze Design**: re-runs metrics/scoring on the edited plan.

**We build.** Extend our editable canvas from move/delete/swap to the full set:
1. **Select room → property panel** (Department, area actual/target, headcount, dims, Open/Enclosed).
2. **Furniture Layouts palette** per room type (pre-composed arrangements) + Items swap (piece-level).
3. **Merge rooms** (delete shared wall → union polygons → re-type + re-furnish) with a **context-aware
   suggestion** ("this is now a large enclosed room → suggest boardroom table").
4. **Change Room Type** searchable panel (re-type + re-target + re-color).
5. **Rotate** + **door edit** (position + swing side).
6. **Live re-score** (Work seats, open/enclosed, density) on every edit + program-tree actual/target.

**Our codebase.** We already have: drag-move, delete, furniture/room swap, live metrics
(`/api/layout/metrics`), room-family coloring, per-room `boundary_basis`/`confidence`. Gaps to build:
the **room property panel** (right rail), **furniture-layout palette** (pre-composed pods — needs a
layout library keyed by room type; source from the Steelcase settings library), **merge** (polygon
union + re-type + context suggestion), **change-room-type** panel, **rotate** + **door edit**, and the
**program tree with actual/target**. `testfit/metrics.py` + `layout_metrics.py` do the re-scoring;
`testfit/settings.py` (Steelcase Settings) is the furniture-layout source; `bom.py`/`pricing/engine.py`
re-price on swap.

**Design.** Right rail = calm property card on paper; layout thumbnails = ink mini-plans on `--paper-2`,
selected = terracotta ring. Program tree actual/target: under-target muted, over-target terracotta.
Merge/retype suggestions surface as a small terracotta callout, never auto-applied (honest).
