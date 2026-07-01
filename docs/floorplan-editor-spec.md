# Floor-Plan Editor — Spec

**Branch:** `floorplan-editor` · **Status:** draft, awaiting approval · **Companion:** `PLAN.md`, `ROADMAP.md`

## Goal

Recreate the qbiq layout pipeline inside DSource Studio: **import a CAD plan → detect & color-code rooms and walls → generate/refine a furnished test-fit → make it look good → edit it interactively (move, resize, swap, delete) → export.** Reference spec captured screen-by-screen in memory `qbiq-platform-ui-spec`.

The engine principle holds: **the structured scene is the source of truth; AI is the beauty layer.** Detected/generated geometry is real or flagged, never faked (`needs_confirmation`, `real=False` discipline continues).

## Scope / non-goals

- **In:** CAD room detection, an editable 2D canvas, department color-coding, a program-spec panel, finishes→render wiring.
- **Out (this effort):** Revit `.RVT` export (needs a .NET/Revit bridge — defer), ML-scored optimization, multi-user real-time collaboration, ceiling/MEP/lighting simulation, mobile UI. These are logged as gaps, not built now.

## Reuse inventory (do not rebuild)

| Capability | Lives in | Reused for |
|---|---|---|
| DXF/DWG ingest, unit→feet, boundary/core/columns | `backend/app/floorplan/dxf_ingest.py`, `cad_geometry.py` | Phase 1 input |
| Normalized element schema (`walls`, `doors`, `rooms`, `furniture`) | `backend/app/ingestion/schema.py` (`ExtractedLayout`, `Room`) | Phase 1 output target |
| Procedural test-fit, 3 variants, concept/detailed modes, metrics | `backend/app/testfit/*`, `metrics.py`, `capacity.py` | Phases 2–3 |
| 2D SVG canvas w/ select + color palettes; 2.5D view | `frontend/src/components/PlanCanvas.tsx`, `SpaceView.tsx` | Phases 1–2 |
| Library API (settings/products/geometry) | `backend/app/routers/library.py` | Phase 2 swap |
| Photoreal render proxy (Flux/Gemini) | `backend/app/routers/render.py` | Phase 4 |
| Export DXF/IFC/Excel/PDF | `testfit/dxf_export.py`, `ifc/`, `takeoff/`, `report.py` | Phase 4 |

---

## Phase 1 — CAD → detected, color-coded rooms

**Requirement.** Given an uploaded DXF, close its walls into room polygons, classify each room's type, and render them color-coded on the existing canvas — the qbiq "Space" step.

**Add:** `backend/app/floorplan/room_detect.py` — `detect_rooms(paths, boundary) -> list[Room]`. Wall graph from `cad_geometry` paths + boundary → `shapely.polygonize` → closed polygons; classify `type` from area + enclosed furniture hints; centroid as `center`. Reuse the wall-hint layer logic already in `cad_geometry.py`.

**Change:** `routers/ingest_cad.py` to populate `ExtractedLayout.rooms` via `detect_rooms`. Frontend: render detected rooms in `PlanCanvas` (color-code path already exists — verify types map to `--room-*` tokens).

**Data model.** No new schema; fills existing `Room` (`schema.py:25`).

**Acceptance criteria.**
- AC1: A DXF with N enclosed spaces yields N room polygons; each polygon is closed and non-overlapping.
- AC2: Rooms outside the boundary or inside a core are excluded.
- AC3: When walls don't close, that region is reported in `notes` and not faked (empty/`unknown`), honoring `needs_confirmation`.
- AC4: Uploading the sample plan shows filled, color-coded rooms in the canvas.

**Tests.** `backend/tests/test_room_detect.py` — closure count on a fixture DXF, no-overlap, exclusion of core/out-of-bounds, open-wall→note (no crash, no fabricated room).

---

## Phase 2 — Editable canvas (headline)

**Requirement.** Select any room or furniture instance and **move, resize, delete** it; **swap** a piece for a catalog-compatible alternate; metrics re-score live. The qbiq test-fit editor.

**Change:** `PlanCanvas.tsx` — drag-move + resize handles + delete on rooms/instances (extends existing select). `Studio.tsx` — edit-state (dirty instances) + undo/redo. Reuse existing containment/overlap validators from `testfit/` for legal-move checks.

**Add:** `POST /api/testfit/validate` (or extend an existing testfit route) — takes edited instances, returns validity flags + re-scored `metrics`. Swap uses existing `/api/library/products` + `/geometry`.

**Acceptance criteria.**
- AC1: Dragging a room updates its position; an illegal drop (overlap/out-of-bounds) is rejected or flagged, never silently overlapping.
- AC2: Resizing updates area and re-scores headcount/density in the side panel.
- AC3: Swapping furniture replaces the instance's SKU/geometry and re-prices via the existing quote path.
- AC4: Undo reverts the last edit; metrics recompute.

**Tests.** Backend validate/rescore endpoint test; frontend interaction test for move/resize/delete legality.

---

## Phase 3 — Program panel + department color-coding

**Requirement.** A qbiq-style program spec: room-type **cards with ± quantity steppers** + live density/percentage summary, feeding the existing detailed generator. Color rooms by **department** (blue=open / yellow=collab / green=focus), with a legend.

**Add:** `frontend/src/components/ProgramPanel.tsx` (drives existing `POST /api/generate/detailed`). `department` field on `Room` + palette tokens + legend. Backend `detailed.py`/`capacity.py` already accept explicit counts + density — wire, don't rewrite.

**Acceptance criteria.**
- AC1: Changing a room-type count re-derives the live density/percentage summary before generating.
- AC2: Generate produces a layout honoring the requested counts (within placement feasibility; shortfalls reported, not faked).
- AC3: Rooms render in department colors with a legend matching the video's scheme.

**Tests.** Program→spec translation test; department palette snapshot.

---

## Phase 4 — Finishes → render + export parity

**Requirement.** A finishes selector (wall/partition/door/materials) that maps to a render prompt via the existing `render.py`; confirm export set (DXF/IFC/Excel/PDF) covers qbiq's outputs minus Revit.

**Acceptance criteria.**
- AC1: Selecting finishes changes the render prompt and returns an updated image.
- AC2: Export produces DXF + IFC + Excel BOM + PDF for the edited layout; Revit gap documented.

**Tests.** Finishes→prompt mapping unit test; export smoke test on an edited fit.

---

## Working method

Per `CLAUDE.md`: one phase at a time, small commits, tests green after each, stop for approval before starting the next phase. Every new module gets tests; bug fixes get a regression test first.

---

## Shipped (branch `floorplan-editor`)

Reading the actual code corrected several spec assumptions — the codebase already had more than the initial map suggested, so each phase reused rather than rebuilt.

**Phase 1 — CAD → coloured rooms.** Room detection ALREADY existed (`cad_reader.py:_read_rooms`, a mask-subtraction that deliberately avoids `polygonize` on double-line walls). No `room_detect.py` created. Delta: unlabeled rooms fell to `type="unknown"` (no colour) — added `_infer_room_types` (reuses `settings.infer_setting_type`) + frontend `roomFill` colours by `type`. `+ test_cad_reader::test_unlabeled_room_type_inferred_from_furniture`.

**Phase 2 — editable canvas.** Furniture + room *swap* already existed. Delta: backend `/api/layout/metrics` (`ingestion/layout_metrics.py`, tested) + frontend drag-to-move, delete, and a live metrics strip. **Resize / room-polygon reshape DEFERRED** (ambiguous for non-rectangular detected polygons; needs browser verification). Drag uses `getScreenCTM`; builds + typechecks but was **not browser-verified** in the build env.

**Phase 3 — program + colour.** The ± quantity-stepper program editor already existed. Delta: a room-family colour **legend** + a live program tally. Kept the warm-paper/terracotta design system (NOT qbiq's blue/yellow/green — design-system rule). Density/headcount surface post-generate (they need plate area).

**Phase 4 — finishes → render + export.** Export set (PDF/Excel/IFC/DXF) already achieved qbiq parity; **Revit `.RVT` deferred**. Delta: backend `build_render_prompt(finishes)` (tested) + `finishes` on the render request; frontend finishes selector + Visualize (rasterizes the plan SVG, inlining `:root` CSS vars) → render overlay, gated on `/api/render/status`. Render itself needs a provider key + a browser to verify end-to-end.

**Deferred (logged, not built):** furniture/room resize, room-polygon reshape, Revit export, ML-scored optimization. **Not browser-verified in this env:** the drag interaction and the finishes render round-trip.
