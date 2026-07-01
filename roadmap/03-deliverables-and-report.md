# 03 — Deliverables & the PDF Report

qbiq's output is a **branded, multi-page PDF report** plus a set of machine formats. This is the
commercial payload — what the client actually receives. We must produce the same set (INR/GST for us).

---

## The PDF report — page anatomy  ·  `reference/report-01…08`

Every page carries **qbiq logo (top-left)**, **client logo (top-right, "Royal Estate")**, and a
centered title "`<Section>`: Crystal Tower | Modern".

### 1. Cover  ·  `report-01`
Client logo (LINEAR SOLUTIONS), qbiq logo, project title block — **"Royal Estate / Crystal Tower |
Modern / via monteverde 1894 bologna italy / 6th Floor"** — over a large **building photo**, plus
"For more information visit qbiq.ai".
→ **We build:** cover from Property (name/address/floor/photo) + client logo + our wordmark.

### 2. 3D virtual tour page  ·  `report-02`
"3D virtual tour / **Alternative A**", a **line-drawing** of that alternative's plan, **"Click or
scan to watch"** with a **QR code** + a hero interior render. One per alternative.
→ **We build:** a tour page per alternative with QR → hosted 3D walkthrough + a hero render.

### 3. Per-alternative test-fit page  ·  `report-03/05` (A), `report-04/06` (B)
Left **metric sidebar** (icons + Fraunces-style numerals):
- **USF** (15,360), **Seats** (149), **Open Space** (141), **Offices** (7), **Conf Room** (12),
  **Density sqf/person** (103.09).
- Three bars vs the **Average**: **Daylight 85%**, **Privacy 5%**, **Efficiency 79%**.
Right: the **color-coded floor plan** + **scale bar** + **legend** — **Executive · Office · Open Space ·
Conf Room · Reception · Pantry · Amenities · Comfort Zone · IT Room**. Footer: "Design #… · For
Evaluation Purposes Only". (Alt B differs: 148 seats, 138 open, 5 offices, 11 conf, density 103.78,
daylight 92%, privacy 6%, efficiency 81% — proving each variant is independently scored.)
→ **We build:** one page per alternative — our metric rail (we compute seats/open/enclosed/density;
add daylight/privacy/efficiency from `metrics.py`) + color-coded plan + legend + scale.

### 4. Summary comparison  ·  `report-07`
- A **table** comparing **Alternative A / B / C** across **Seats, Open Space, Offices, Conf Room,
  Density, Daylight, Privacy**.
- A **radar/spider chart** overlaying the three on axes **Efficiency, Daylight, Density, Open Space,
  Rooms, Conferences, Privacy, Conference Seats**.
- A **"Space" stacked bar** per alternative: **Work · Shared Space · Amenities · Shared** proportions.
→ **We build:** the comparison table + radar + space-mix bars from the three variants' metrics.

### 5. Walkthrough renders  ·  `report-08`
Photoreal interior renders (reception, open space, conference) from the Visualization theme/finishes.
→ **We build:** renders via our Flux/Gemini proxy, themed by the finishes selection.

**Our codebase.** `routers/report.py` (PDF report — exists, extend to this page set),
`testfit/metrics.py` (usf/seats/density/daylight%/privacy%/efficiency% — exists), `metrics` +
`alternatives.py` for the comparison, `routers/render.py` for renders. Charts: render server-side
into the PDF (reportlab) — radar + stacked bars.

**Design.** The report is the one place we go **near-white for print**, but keep Fraunces numerals,
ink linework, terracotta accent, and our room-family legend. It should read as an editorial spec sheet.

---

## Downloads page  ·  `reference/38`

`.../project-details/.../download`. **Version** dropdown (V1 22-Oct-2025). Tiles:
- **Report (PDF)** with **Select Pages** checkboxes: Video · Space · Area · Departments · Comparison ·
  Empty Floor · Headcount · Original Plan → Download.
- **CAD** (dwg/dxf), **Program Summary (XLS)**, **Revit (RVT)**, **Quantity Take Off (XLS** — construction
  material amounts), **Rendered Photos (ZIP)**, **Images (PNG)**, **QR Image**.

**We build / our codebase.** We already export **DXF** (`testfit/dxf_export.py`), **IFC/BIM** (`ifc/`),
**Excel takeoff** (`takeoff/`), **PDF report** (`report.py`). Gaps: **page-selectable** PDF, **Program
Summary XLS**, **Rendered Photos ZIP**, **PNG image**, **QR → 3D tour**, **versioning**, and **Revit .RVT**
(hard — needs a Revit/APS bridge; defer, keep IFC as the BIM path). INR/GST on the takeoff (we already
honor a currency field).

---

## Plan Files modal  ·  `reference/46`

Per design: **PNG · CAD Preview · CAD + Revit · Virtual Tour · PDF Report**, plus **Edit in Studio /
Duplicate and Edit in Studio / Delete Plan**. A quick per-design export/fork menu.

**We build.** A per-design menu mirroring this: quick exports + Edit/Duplicate/Delete. Ties the
Review grid to Studio and Downloads.
