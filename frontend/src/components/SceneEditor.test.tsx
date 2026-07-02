import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, waitFor } from "@testing-library/react";
import type { Scene, SceneMetrics } from "../types";

// Spy on the one command boundary — every persistent edit still lands as exactly one validated
// command through applySceneCommand, so asserting its calls is asserting the editor's contract.
const applySpy = vi.fn();

vi.mock("../api", () => ({
  applySceneCommand: (scene: Scene, command: unknown) => applySpy(command) ?? Promise.resolve({ scene, metrics: METRICS }),
  sceneMetrics: () => Promise.resolve(METRICS),
  sceneFromFit: () => Promise.resolve({ scene: SCENE, metrics: METRICS }),
  fetchSettings: () => Promise.resolve([]),
  downloadRenderImage: () => Promise.resolve(),
  downloadSceneDxf: () => Promise.resolve(),
  downloadSceneTakeoff: () => Promise.resolve(),
  num: (n: number) => String(n),
}));
vi.mock("../Studio", () => ({
  ArrangementThumb: () => null,
  captureSvgJpeg: () => Promise.resolve(""),
  SLOT_CATS: new Set(["chair"]),
}));

import SceneEditor from "./SceneEditor";

const METRICS: SceneMetrics = {
  seats: 1, open_seats: 1, enclosed_seats: 0, usable_sf: 400, density_sf_per_person: 400, rooms: 0,
  rooms_by_type: {}, program: { headcount: null, density_rsf_per_person: null, lines: [] },
};

// Minimal valid scene: one open zone holding one placement with a single chair item.
const SCENE: Scene = {
  underlay: { boundary: [[0, 0], [20, 0], [20, 20], [0, 20]], cores: [], columns: [], base_doors: [] },
  zones: [{ id: "z1", polygon: [[0, 0], [20, 0], [20, 20], [0, 20]], room_type: "open", enclosed: false, program_line_ref: null, boundary_partition_ids: [] }],
  partitions: [],
  doors: [],
  placements: [{ id: "pl1", zone_id: "z1", plate_id: "p1", transform: { x: 8, y: 8, rotation: 0 }, items: [{ plate_item_ref: 0, transform_override: null, deleted: false }] }],
  plates: { p1: { id: "p1", room_type: "open", sqft: 4, width_ft: 2, height_ft: 2, capacity: 1, items: [{ category: "chair", model: null, dx: 0, dy: 0, w: 2, h: 2, rotation: 0 }] } },
  program_ref: { lines: [], headcount: null, density_rsf_per_person: null },
};

function renderEditor() {
  const utils = render(<SceneEditor savedScene={SCENE} projectId="p1" designId="d1" onExit={() => {}} />);
  return utils;
}

beforeEach(() => applySpy.mockClear());

describe("SceneEditor on-canvas gizmos", () => {
  // Regression: a bare click on the rotate grip (pointerdown→up, no move) used to dispatch nothing.
  it("rotates +90 on a bare grip click", async () => {
    const { container } = renderEditor();
    const item = await waitFor(() => {
      const el = container.querySelector(".layout-furn.is-movable");
      if (!el) throw new Error("item not rendered yet");
      return el;
    });
    fireEvent.click(item); // select
    const grip = await waitFor(() => {
      const el = container.querySelector(".rotate-grip circle");
      if (!el) throw new Error("grip not shown");
      return el;
    });
    fireEvent.pointerDown(grip, { pointerId: 1 });
    fireEvent.pointerUp(grip, { pointerId: 1 }); // no pointermove → a pure click
    expect(applySpy).toHaveBeenCalledWith(expect.objectContaining({ type: "rotate_item", delta: 90 }));
  });

  // Regression: the delete affordance didn't stopPropagation, so canvas pan-capture ate the click and
  // no delete_item fired. Here we assert (a) it stops pointer propagation and (b) it dispatches delete.
  it("deletes via the gizmo and stops pointer propagation", async () => {
    const { container } = renderEditor();
    const item = await waitFor(() => {
      const el = container.querySelector(".layout-furn.is-movable");
      if (!el) throw new Error("item not rendered yet");
      return el;
    });
    fireEvent.click(item); // select
    const del = await waitFor(() => {
      const el = container.querySelector(".item-delete");
      if (!el) throw new Error("delete affordance not shown");
      return el;
    });

    // (a) propagation: a pointerdown on the gizmo must not bubble past React's root (where the canvas
    // pan handler lives) — the fix that stopped pan-capture from eating the click. Observe on
    // `document`, above the render root, so React's synthetic stopPropagation is faithfully reflected.
    const ancestorSpy = vi.fn();
    document.addEventListener("pointerdown", ancestorSpy);
    fireEvent.pointerDown(del, { pointerId: 1 });
    document.removeEventListener("pointerdown", ancestorSpy);
    expect(ancestorSpy).not.toHaveBeenCalled();

    // (b) dispatch: clicking it commits exactly one delete_item command.
    fireEvent.click(del);
    expect(applySpy).toHaveBeenCalledWith(expect.objectContaining({ type: "delete_item", placement_id: "pl1", item_ref: 0 }));
  });
});
