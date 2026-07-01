# DSource Studio — Roadmap & qbiq Reference

This folder is our **north star**: a detailed, end-to-end breakdown of how [qbiq](https://qbiq.ai)
takes an office from a raw CAD plate to priced, sourceable, color-coded test-fits — captured
screen-by-screen from a live product demo — mapped to **how we build the same on our stack and
grounded to our own design system**.

We are cloning qbiq's *workflow and structure*, **not** its visual language. qbiq is a clean blue/white
enterprise SaaS. DSource Studio is warm paper + ink + a single terracotta ember (Fraunces numerals,
Inter body). Every screen we recreate is re-skinned to `frontend/src/design/` — see
[design-grounding](#design-grounding) below.

## The workflow feels broken today because it isn't a workflow yet

Right now the app is two disconnected modes ("Read layout" / "Generate") behind a segmented toggle.
qbiq is a **single guided pipeline** with a persistent left-rail stepper. Fixing that — turning the
app into one legible Property → Space → Program → Visualization → Summary → Generate → Review →
Download flow — is the point of this roadmap.

## The end-to-end pipeline (the spine)

```
Projects dashboard  ──►  New Project (5-step wizard)  ──►  Generate  ──►  Review & Edit  ──►  Download
    (grid of cards)          │                                (async)      │                    │
                             ├─ 1. Property   name / address / units / photo
                             ├─ 2. Space      upload CAD/PDF → mark planning area → tag rooms → wall controls
                             ├─ 3. Program    style + desks + seat split → room-type cards (± qty) → live summary → preferred locations
                             ├─ 4. Visualization  facade + theme + finishes (live 3D render per room)
                             └─ 5. Summary    confirm everything → Generate
                                                                          │
                                             3 verified test-fits (A/B/C) + edited copies
                                                                          │
                                             Studio editor: select room · merge · change type ·
                                             swap furniture layout · move/rotate · edit doors · re-score
                                                                          │
                                             PDF report · CAD · Revit · Excel BOM/takeoff · renders · 3D tour · QR
```

## Files in this folder

| File | Covers | qbiq images |
|---|---|---|
| [01-workflow.md](01-workflow.md) | The full guided pipeline, stage by stage — every screen described, qbiq behavior, our build target, our-codebase mapping | dashboard → wizard → summary |
| [02-studio-editor.md](02-studio-editor.md) | The post-generation editable canvas — select/merge/retype/relayout/move/rotate/edit-doors/analyze | 40–45 |
| [03-deliverables-and-report.md](03-deliverables-and-report.md) | The PDF report page anatomy + every export format | report-01…08, 38, 46 |
| [04-build-plan.md](04-build-plan.md) | Gap analysis vs our repo, phased build order, open research questions | — |
| [reference/](reference/) | All 43 screenshots you captured, in workflow order | — |

## Design grounding

Everything we build from these references must obey `frontend/src/design/` and the CLAUDE.md design
rules. When a doc says "recreate qbiq's X," it means the *structure/behavior*, re-skinned as:

- **Surface:** warm paper `--paper #f4f1ea` (not qbiq's white); panels `--paper-2/3`.
- **Ink:** `--ink #1a1813` linework + text; never pure black.
- **Accent:** one terracotta ember `--accent #b8552f` (qbiq uses blue — we do **not**).
- **Type:** Fraunces for display + **all numerals** (`--t-numeral`); Inter for body/labels.
- **Room color families (already in tokens):** `--room-open` (neutral), `--room-office` (ochre),
  `--room-meeting` (slate), `--room-collab` (terracotta), `--room-amenity` (sage). This is our
  warm-paper translation of qbiq's Executive/Office/Open/Conf/Reception/Pantry/Amenities/Comfort/IT legend.
- **Never fabricate data** — every metric/price/room carries `{value, confidence, basis}`
  (rooms already do: `boundary_basis` + `confidence`). qbiq shows hard numbers; we show honest ones.

## How we use this folder

1. Read `01-workflow.md` end to end — it is the spec for the guided pipeline.
2. `04-build-plan.md` sequences the work against what already exists in the repo (a lot does).
3. Each build phase gets its own branch + tests + in-browser verification, per the working method.
