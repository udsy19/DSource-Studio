# 01 — The Guided Pipeline (end to end)

The whole product is **one linear, resumable pipeline** with a persistent left-rail stepper, not the
two-mode toggle we have now. Each stage below is documented as: **qbiq does** (from the demo) →
**we build** (target) → **our codebase** (what to reuse/extend) → **design** (warm-paper translation).

Wizard URL shape (qbiq): `.../project-wizard/NEW/hd-program/<step>-wizard/...` with left-rail steps
**Property · Space · Program · Visualization · Summary**, a "New office" breadcrumb, and Save Draft / Next.

---

## Stage 0 — Projects dashboard  ·  `reference/12,13`

**qbiq does.** `plan.qbiq.ai/.../main-view/projects`. Left nav: **Projects · Themes**, workspace
switcher ("Sales Demo"). Header: **+ New Project**, search, "All Projects" filter, "By: Last Created"
sort. Body: **My Projects** — a grid of cards. Each card = `#ID` + status pill
(**Draft / Processing / Ready**), a floor-plan thumbnail (grey placeholder while processing, real plan
outline when ready), name, address, floor, created date, `⋯` menu.

**We build.** A projects grid as the app home. Card states drive everything: Draft → resume wizard;
Processing → async generation running (poll); Ready → open Review. Status is the honest signal that
generation is a *job*, not instant.

**Our codebase.** `backend/app/routers/projects.py` (`Project` CRUD) + `procurement/models.py` project
model. Frontend: new `Projects.tsx` home; `Studio.tsx` becomes the wizard/review host, not the entry.

**Design.** Cards on `--paper-2` with `--line` hairline, `--r2` radius; status pill in terracotta
(Processing) / sage (Ready) / muted (Draft); numerals + dates in Fraunces.

---

## Stage 1 — Property  ·  `reference/14`

**qbiq does.** "Property Info": **Property Name**, **Property Address**, **Units** toggle
(Imperial sqft / Metric sqm), and a large **Property Image** (building photo). Simple form; Next.

**We build.** Same form. Units toggle threads through the entire pipeline (all areas/dimensions).
India-first: default **Metric (sqm)** but keep the toggle. Address feeds the (later) vendor/serviceability layer.

**Our codebase.** New `property` fields on the project record. Units flag already implied by
`ExtractedLayout.units` — make it a first-class project setting.

**Design.** `design/ui.tsx` Input + Segmented (units). Image dropzone reuses `Dropzone.tsx` styling.

---

## Stage 2 — Space (CAD import + classify)  ·  `reference/15,16,17`

The single most important stage — it's where the plate becomes a structured, taggable scene.

**qbiq does.**
- **Space Info**: Single Floor / Multi Floor; **Floor Number**; **Floor File (CAD/PDF)** upload;
  area basis **RSF (rentable) vs USF (usable)** radio; **Planning Area** (auto-filled, e.g. 13,336 USF).
- Uploaded plan renders on a canvas with **interior walls cyan, perimeter red/orange, door swings
  green arcs, furniture/fixtures magenta**. Bottom toolbar: Undo/Redo/Reset/Rotate/Reset Zoom + zoom %.
- **Mark planning area** (`ref 16`): a popup — "To define your partial planning area, click to create
  a closed polygon." The user **draws a polygon** directly on the plan; the enclosed region becomes the
  blue-highlighted working area. *This is how the AI is told "plan only inside here"* — critical for
  partial floors / multi-tenant plates.
- **Room markers** (`ref 17`): a top toolbar of draggable tags — **Partial Floor, Outdoor Space,
  IT Room, Pantry, WC, Interior Stairs, View, Entrance, Keep Room Walls, Keep All Interior Walls**.
  The user **drags a marker onto the plan** to say "the IT room is *here*", "pantry *here*", "WC *here*".
  qbiq also **infers bathrooms/cores from the CAD** automatically. "Keep Room Walls / Keep All Interior
  Walls" tell the generator which existing partitions to preserve vs. clear.

**We build.**
1. **Upload → parse** (done): DXF/DWG/PDF → `ExtractedLayout` (walls/doors/rooms/furniture, feet).
2. **Mark planning area**: a polygon-draw tool on our SVG canvas; store as a clip polygon; the
   generator/segmenter only operates inside it. (New — see build plan.)
3. **Drag room markers**: draggable IT/Pantry/WC/Entrance/Stairs/Outdoor pins that write a typed,
   located hint onto the scene; feed them as seeds into our label-seeded segmenter so a dragged "IT"
   pin becomes an IT room. **Infer bathrooms/cores** from layer/'core' hints (we already detect cores/columns).
4. **Wall-keep toggles**: per-wall or global "keep" flags carried into generation.

**Our codebase.** `floorplan/dxf_ingest.py` (boundary/core/columns), `ingestion/cad_reader.py`
(walls/doors/furniture + `room_segment.py` label-seeded segmentation — the dragged markers become
extra seeds!), `routers/ingest_cad.py`, `routers/floorplan_raster.py` (PDF/JPG). The **planning-area
polygon** clips the plate before segmentation; the **room-marker seeds** slot directly into
`segment_regions(seed_points=...)`. Frontend: `PlanCanvas.tsx` already renders walls-by-type + supports
pointer interaction (we added drag/select) — extend with polygon-draw + marker-drop.

**Design.** Keep our warm-paper CAD sheet + wall-type legend. Planning-area polygon = terracotta
dashed stroke + faint terracotta fill. Room markers = small ink pills with a category glyph.

---

## Stage 3 — Program (the space brief)  ·  `reference/18–30`

Headcount-and-mix driven program, with a live summary — the input to generation.

**qbiq does.**
- **Detailed / Floor Plan Profile** (`ref 18`): **Selected planning style** (`ref 19`:
  **Traditional** = privacy-first; **Modern** = open, collaborative; **Co-Work** = blend) with
  descriptions; **Open Space Desk Type** (`ref 20`: Benching / Workstation); **Open Space Desk Size**
  (`ref 21`: 72"×30" … 36"×24"); **Seat Distribution** slider (% Offices vs % Open Space).
- **Category tabs**: **Office · Open Space · Conference · Reception · Pantry · Support Area ·
  Amenities · Other** (`ref 22–29`). Each tab = a grid of **room-type cards**, each with an icon
  (mini plan), an editable **sqft** (or people/desk-size), and a **− N +** quantity stepper:
  - Office: Executive 330, Large 200, Medium 150, Small 85, Double 105, 8/6/4/3/2-People.
  - Open Space: Workstation XL/L/M/S/XS + Bench L/M/S/XS/XXS with dimensions.
  - Conference: Board Room (18–30), XLarge, Large (10–16), Medium (8–10), Small (4–6),
    Huddle (2–4), Focus Room (1), Meeting Booth.
  - Reception: Double. Pantry: Employee Lounge L/S. Support Area: Collaboration, Print Hub, Locker,
    Phone Booth, Lounge, Closed Collaboration.
  - Amenities: Yoga, Library, Game, Wellness, Training, Gym, Multipurpose, Cleaning, Mail, IT,
    Coat Closet, Storage.
  - Other (`ref 28,29`): Shower, WC, **+ Add New Room** ("we might not have furniture for this room").
- **Program Summary** right rail (`ref 18,22`): **People** total, **Density 1:X sqft**, a **Program**
  bar (Total / Departments tabs) and a live **% breakdown per department** (Office 24%, Open Space 29%,
  Conference 7%…) with per-room **Quantity** + **Total Area**. Updates live as steppers change.
- **Preferred Location** (`ref 30`): "Locate a maximum of 5 rooms." A room card's **Placement
  Preference** = Flexible / **Place on plan**; choosing Place-on-plan opens the plan and lets you
  **drag that room to a preferred spot** — the generator treats it as a soft constraint.

**We build.** This is our detailed program editor — which **already largely exists**. Add: the
planning-style / desk-type / desk-size / seat-split controls, the full category tab set with per-room
cards, the live Program Summary with % + density, custom-room add, and the **preferred-location drag**
(a soft placement constraint fed to the generator).

**Our codebase.** `Studio.tsx` `DetailedProgramEditor` (category-grouped ± stepper cards — exists),
`ProgramPanel`/`LayoutMetricsStrip` (summary — exists, extend to % + density pre-generate), backend
`testfit/detailed.py` + `capacity.py` (explicit counts + density — exists). Preferred-location =
a soft-constraint list of `{room_type, x, y}` consumed by `testfit/layout.py` placement (extend).

**Design.** Cards on paper with ink mini-plan glyphs; stepper in terracotta; the department % bar
uses the room-family tints. Program summary rail mirrors qbiq's but warm.

---

## Stage 4 — Visualization (finishes → render)  ·  `reference/31–36`

The "make it beautiful" leg — drives the 3D render + report imagery.

**qbiq does.**
- **Setup** (`ref 31`): **Project Info** — **Virtual Tour** checkbox, **3D After Design** toggle;
  **Client Logo** upload (appears on the tour/report); **Property Specs** — **Gross Ceiling Height**;
  **Facade Style** (Curtain Wall / Window S/M/L / 1T / 2T Curtain wall); **Frame Finish**
  (Black/White/Aluminium/Wood); **Perimeter Convectors** (None / Perimeter convectors).
- **Design** (`ref 32`): a **theme gallery** — Start From Scratch, Modern, Luxurious, Industrial,
  Basic, Traditional, Urban, White, Natural — with a live **preview panel per room** and **Adjust Theme**.
- **Select Finishes** modal (`ref 33–36`): per-material pickers split by **Shared / Enclosed /
  Reception** spaces — **Ceiling** (Drywall, Suspended 60×60/120, Linear white/wood, Wood Wool, exposed
  metal), **Floor** (Parquet variants, Concrete, Terrazzo, Tile, Carpet, Marble), **Wall** (linear/
  wood panels, concrete, acoustic fabric, brick, Red/Blue/Yellow), **Partition** (Frameless / Drywall /
  Glass&drywall / Half drywall / Glass) + **Partition Finish** (Black/White/Aluminum/Wood),
  **Door** (Solid/Glass), **Kitchen Carpentry**. Right side shows a **live photoreal render** of the
  selected room (Reception / Open-Space / Conference), paginated across views.
- **Report Preview** tab.

**We build.** A finishes selector that composes a render prompt + material set, with a live render
per room. We already have the render proxy and a finishes→prompt builder; extend to per-space
material sets (ceiling/floor/wall/partition/door) and the theme gallery, and wire the live preview.

**Our codebase.** `routers/render.py` (Flux/Gemini proxy + `build_render_prompt(finishes)` — exists),
frontend `FinishesPanel` + `renderView` (exists, extend to full material sets + per-room preview +
theme presets). `config.py` holds swappable model names.

**Design.** Theme/finish swatches on paper; selected = terracotta ring. Render preview framed like a
gallery print. Keep it tasteful, not the dense qbiq grid.

---

## Stage 5 — Summary → Generate  ·  `reference/37`

**qbiq does.** "Summary": **Delivery Date** ("Test-Fit delivery on business days only"), and cards for
**Property** (photo/address), **Space** (area + floor + plan thumbnail), **Client Logo**, **Program**
(Seatcount, Density, Desk Size + the detailed program breakdown), **Visualization** (Theme name +
render thumb). Confirm → **Generate**. Generation is **async** — the project goes **Processing**, then
**Ready** (with 3 alternatives), and delivery is queued, not instant.

**We build.** A read-only confirmation of every stage's inputs, then Generate → create a job, flip the
project to Processing, run the 3-variant generation, flip to Ready. Honest about async + timing.

**Our codebase.** `testfit/alternatives.py` (3 variants A/B/C — exists), `testfit/metrics.py`
(scoring — exists). Wrap generation as a background job tied to project status.

**Design.** Summary = calm review cards on paper. Generate = the one primary terracotta button.
