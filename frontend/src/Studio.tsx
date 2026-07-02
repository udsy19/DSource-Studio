import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  downloadDxfFromFit,
  downloadIfcFromFit,
  downloadReport,
  downloadTakeoffFromFit,
  downloadTakeoffFromLayout,
  fetchGeometry,
  fetchLayoutBom,
  fetchLayoutMetrics,
  fetchProducts,
  fetchSettings,
  generateDetailed,
  generateFromConcept,
  ingestCad,
  iterateDetailed,
  mergeRooms,
  money,
  num,
  renderEditView,
  renderStatus,
  renderView,
  type Bom,
  type RoomSeed,
  type SymbolGeometry,
} from "./api";
import Dropzone from "./components/Dropzone";
import { furnitureSymbol } from "./components/furnitureSymbols";
import PlanCanvas, { furnitureKey, instanceKey } from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented } from "./design/ui";
import WizardStepper, { type WizardStep } from "./components/WizardStepper";
import { layoutFromFit, rotatePoint } from "./fitToLayout";
import { type ProjectStatus, type WorkflowProject } from "./workflowProjects";
import type {
  Alternative,
  CatalogSetting,
  ConceptProgram,
  DetailedProgram,
  ExtractedDoor,
  ExtractedFurniture,
  ExtractedLayout,
  ExtractedRoom,
  Instance,
  LayoutMetrics,
  Metrics,
  Placement,
  Plan,
  Product,
  RoomType,
} from "./types";

// The component categories surfaced in the bill, in reading order; only non-zero rows render.
const INVENTORY_ROWS: { key: string; label: string }[] = [
  { key: "chair", label: "chairs" },
  { key: "workstation", label: "workstations" },
  { key: "desk", label: "desks" },
  { key: "table", label: "tables" },
  { key: "sofa", label: "lounge sofas" },
  { key: "stool", label: "stools" },
  { key: "panel", label: "glass panels" },
  { key: "storage", label: "storage" },
  { key: "tv", label: "screens" },
  { key: "planter", label: "planters" },
  { key: "door", label: "doors" },
];

// Concept brief option sets — labels for the user, values for the backend.
const PLANNING_STYLES: { value: ConceptProgram["planning_style"]; label: string }[] = [
  { value: "traditional", label: "Traditional" },
  { value: "modern", label: "Modern" },
  { value: "cowork", label: "Co-work" },
];
const DESK_TYPES: { value: ConceptProgram["desk_type"]; label: string }[] = [
  { value: "workstations", label: "Workstations" },
  { value: "benchings", label: "Benchings" },
];
const DESK_SIZES: { value: string; label: string; w: number; d: number }[] = [
  { value: "120x60", label: "120×60", w: 120, d: 60 },
  { value: "140x70", label: "140×70", w: 140, d: 70 },
  { value: "160x70", label: "160×70", w: 160, d: 70 },
  { value: "180x70", label: "180×70", w: 180, d: 70 },
];
const CLOSED_RATIOS = [0, 0.1, 0.2, 0.3, 0.4]; // share of seats in closed offices

const DEFAULT_CONCEPT: ConceptProgram = {
  planning_style: "modern",
  desk_type: "workstations",
  desk_width_cm: 140,
  desk_depth_cm: 70,
  closed_ratio: 0.2,
};

// Detailed mode — the room catalog (mirrors backend app/testfit/catalog.py), grouped by family.
// Each entry carries the placement that suits it; count 0 means "not requested".
const ROOM_CATALOG: {
  family: string;
  rooms: { type: RoomType; label: string; placement: Placement }[];
}[] = [
  {
    family: "Offices",
    rooms: [
      { type: "office_exec", label: "Executive", placement: "window" },
      { type: "office_large", label: "Large", placement: "window" },
      { type: "office_medium", label: "Medium", placement: "window" },
      { type: "office_small", label: "Small", placement: "window" },
      { type: "office_focus", label: "Focus", placement: "flexible" },
    ],
  },
  {
    family: "Team rooms",
    rooms: [
      { type: "team_2", label: "Team · 2", placement: "window" },
      { type: "team_4", label: "Team · 4", placement: "window" },
      { type: "team_6", label: "Team · 6", placement: "flexible" },
      { type: "team_8", label: "Team · 8", placement: "flexible" },
    ],
  },
  {
    family: "Conference",
    rooms: [
      { type: "conf_board", label: "Boardroom", placement: "flexible" },
      { type: "conf_xl", label: "XL conference", placement: "flexible" },
      { type: "conf_large", label: "Large", placement: "flexible" },
      { type: "conf_medium", label: "Medium", placement: "flexible" },
      { type: "conf_small", label: "Small / meeting", placement: "flexible" },
    ],
  },
  {
    family: "Collaboration",
    rooms: [
      { type: "huddle", label: "Huddle", placement: "core" },
      { type: "phone_booth", label: "Phone booth", placement: "core" },
      { type: "focus_room", label: "Focus room", placement: "flexible" },
    ],
  },
  {
    family: "Amenities",
    rooms: [
      { type: "reception", label: "Reception", placement: "window" },
      { type: "kitchen", label: "Kitchen / pantry", placement: "flexible" },
      { type: "wellness", label: "Wellness", placement: "core" },
      { type: "copy_print", label: "Copy / print", placement: "core" },
      { type: "storage", label: "Storage / IT", placement: "core" },
    ],
  },
];
// Room-marker palette (Space step): drop one on the plan to tell detection "this room is here".
// `type` is a Room.type the frontend colour-maps; `label` is what shows on the pin + room.
const MARKER_TYPES: { type: string; label: string }[] = [
  { type: "office", label: "Office" },
  { type: "meeting", label: "Meeting" },
  { type: "collab", label: "Collab" },
  { type: "storage", label: "IT / Storage" },
  { type: "kitchen", label: "Pantry" },
  { type: "reception", label: "Reception / Entry" },
];

// Change-room-type options (Room.type → label) for the editor's room property panel.
const ROOM_TYPES: { type: string; label: string }[] = [
  { type: "office", label: "Office" },
  { type: "meeting", label: "Meeting" },
  { type: "huddle", label: "Huddle" },
  { type: "open", label: "Open plan" },
  { type: "collab", label: "Collaboration" },
  { type: "reception", label: "Reception" },
  { type: "kitchen", label: "Pantry / Kitchen" },
  { type: "restroom", label: "Restroom / WC" },
  { type: "core", label: "Core / Service" },
  { type: "storage", label: "IT / Storage" },
  { type: "unknown", label: "Unspecified" },
];
// type -> short label for the room list; covers every Room.type the reader can emit.
const ROOM_TYPE_LABEL: Record<string, string> = Object.fromEntries(ROOM_TYPES.map((r) => [r.type, r.label]));
// Enclosed room types (for the Open/Enclosed readout) — the rest read as open.
const ENCLOSED_TYPES = new Set(["office", "meeting", "huddle", "storage", "kitchen", "restroom", "core"]);
// Merged area (sf) at or above which a merged room reads as boardroom-scale in the suggestion. Below
// it, the suggestion still offers the fitting layouts but calls them a larger meeting layout.
const BOARDROOM_MIN_SF = 200;

// Room family taxonomy for the Program tree. Both vocabularies fold in: the fine program types
// (ROOM_CATALOG groups them already) and the coarse types a read/adopted layout carries. Types
// outside any family (open, unknown) are open-plan, not program rooms — excluded from the tree.
const PROGRAM_FAMILIES = ROOM_CATALOG.map((f) => f.family);
const ROOM_FAMILY: Record<string, string> = {
  ...Object.fromEntries(ROOM_CATALOG.flatMap((f) => f.rooms.map((r) => [r.type, f.family]))),
  office: "Offices",
  meeting: "Conference",
  collab: "Collaboration",
  phone: "Collaboration",
  amenity: "Amenities",
};

const PLACEMENTS: { value: Placement; label: string }[] = [
  { value: "window", label: "Window" },
  { value: "core", label: "Core" },
  { value: "flexible", label: "Flexible" },
];

// A 3x3 grid of soft preferred spots on the plate (fraction of its bbox). Picking a cell biases
// where a room type lands; the generator weights it but never lets it override feasibility.
const PREFERRED_ZONES: { x: number; y: number; label: string }[] = [
  { x: 0.15, y: 0.15, label: "front-left" }, { x: 0.5, y: 0.15, label: "front" }, { x: 0.85, y: 0.15, label: "front-right" },
  { x: 0.15, y: 0.5, label: "left" }, { x: 0.5, y: 0.5, label: "centre" }, { x: 0.85, y: 0.5, label: "right" },
  { x: 0.15, y: 0.85, label: "back-left" }, { x: 0.5, y: 0.85, label: "back" }, { x: 0.85, y: 0.85, label: "back-right" },
];

// Visualization finishes — each selection's value is the phrase folded into the render prompt
// (empty = leave as-is). Mirrors the backend build_render_prompt keys (wall/floor/palette/style).
const FINISH_FIELDS: { key: string; label: string; options: { value: string; label: string }[] }[] = [
  { key: "wall", label: "Walls", options: [
    { value: "", label: "As-is" },
    { value: "white drywall", label: "White" },
    { value: "walnut wood panel", label: "Walnut" },
    { value: "exposed concrete", label: "Concrete" },
  ] },
  { key: "floor", label: "Floor", options: [
    { value: "", label: "As-is" },
    { value: "polished concrete", label: "Concrete" },
    { value: "light oak wood", label: "Oak" },
    { value: "grey carpet tile", label: "Carpet" },
  ] },
  { key: "palette", label: "Palette", options: [
    { value: "", label: "As-is" },
    { value: "warm neutral", label: "Warm" },
    { value: "cool grey", label: "Cool" },
    { value: "earthy biophilic", label: "Earthy" },
  ] },
  { key: "style", label: "Style", options: [
    { value: "", label: "Modern" },
    { value: "biophilic", label: "Biophilic" },
    { value: "industrial", label: "Industrial" },
    { value: "scandinavian", label: "Scandi" },
  ] },
];

// Preset finish THEMES — a named bundle of {wall, floor, palette, style} FINISH_FIELDS values,
// selectable as one gesture. Values must be real FINISH_FIELDS options so the Segmented controls
// reflect the pick. `swatch` is a 3-chip UI hint (wall / floor / palette), not a material claim.
const FINISH_THEMES: { name: string; finishes: Record<string, string>; swatch: [string, string, string] }[] = [
  { name: "Warm biophilic",
    finishes: { wall: "walnut wood panel", floor: "light oak wood", palette: "earthy biophilic", style: "biophilic" },
    swatch: ["#6b4a2f", "#c8a06a", "#7c8a5a"] },
  { name: "Cool minimal",
    finishes: { wall: "white drywall", floor: "polished concrete", palette: "cool grey", style: "" },
    swatch: ["#eae7e1", "#9a9a97", "#b7bcc0"] },
  { name: "Industrial loft",
    finishes: { wall: "exposed concrete", floor: "polished concrete", palette: "cool grey", style: "industrial" },
    swatch: ["#8f8b85", "#6f6f6d", "#54585c"] },
  { name: "Scandi light",
    finishes: { wall: "white drywall", floor: "light oak wood", palette: "warm neutral", style: "scandinavian" },
    swatch: ["#f2efe9", "#d8bd97", "#e5d8c6"] },
];

// Instance type → the natural room phrase a scoped Kontext edit names ("Change the walls of the
// meeting room…"). Only the enclosed/nameable scopes; anything unmapped isn't offered as a target.
const ROOM_SCOPE_PHRASE: Record<string, string> = {
  private_office: "private office",
  meeting_room: "meeting room",
  collaboration: "collaboration area",
  phone_booth: "phone booth",
  workstation: "open workstations",
};

const DEFAULT_DETAILED: DetailedProgram = {
  rooms: [
    { type: "office_medium", count: 4, placement: "window" },
    { type: "conf_small", count: 2, placement: "flexible" },
    { type: "huddle", count: 2, placement: "core" },
    { type: "phone_booth", count: 1, placement: "core" },
  ],
  desk_type: "workstations",
  desk_width_cm: 140,
  desk_depth_cm: 70,
};

// ── swap geometry ──
// Recognized furniture a room swap places — mirrors the backend _SLOT_CATS so Read-mode swaps and
// the generator agree on what a room contains (the rest are CET sub-component blocks / glass).
const SLOT_CATS = new Set<string>([
  "chair", "desk", "table", "sofa", "stool", "workstation", "storage", "tv", "planter",
]);

// Map a read room's type/label onto the setting catalog's type vocabulary.
function settingTypeForRoom(room: ExtractedRoom): string {
  const s = `${room.type} ${room.label}`.toLowerCase();
  if (/(office|cabin|director|manager|md\b)/.test(s)) return "private_office";
  if (/(meet|conf|board|huddle|discuss|interview)/.test(s)) return "meeting_room";
  return "collaboration"; // collab / lounge / breakout / anything else
}

// Re-anchor an outline (world-coord polylines) so its bbox centre lands on (cx, cy) — used to
// drop a swapped piece in at the same place, regardless of the catalog outline's own origin.
function placeOutline(
  outline: [number, number][][] | undefined,
  cx: number,
  cy: number,
): [number, number][][] | undefined {
  if (!outline?.length) return outline;
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  for (const ring of outline)
    for (const [x, y] of ring) {
      if (x < minx) minx = x;
      if (x > maxx) maxx = x;
      if (y < miny) miny = y;
      if (y > maxy) maxy = y;
    }
  const dx = cx - (minx + maxx) / 2;
  const dy = cy - (miny + maxy) / 2;
  return outline.map((ring) => ring.map(([x, y]) => [x + dx, y + dy] as [number, number]));
}

// ray-casting point-in-polygon — which furniture sits inside a room (its centre falls in the poly)
function pointInPolygon(px: number, py: number, poly: [number, number][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

// Rasterize the on-screen plan/3D SVG to a JPEG data URL for the render provider. The plan's fills
// are CSS var()s that don't resolve in a detached SVG, so the resolved :root custom properties are
// copied onto the clone (custom props inherit, so descendants then resolve against them).
async function captureSvgJpeg(svg: SVGSVGElement, scale = 2): Promise<string> {
  const vb = svg.viewBox.baseVal;
  const w = Math.max(1, vb.width || svg.clientWidth);
  const h = Math.max(1, vb.height || svg.clientHeight);

  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(w));
  clone.setAttribute("height", String(h));
  const rootStyle = getComputedStyle(document.documentElement);
  const vars: string[] = [];
  for (let i = 0; i < rootStyle.length; i++) {
    const prop = rootStyle[i];
    if (prop.startsWith("--")) vars.push(`${prop}:${rootStyle.getPropertyValue(prop)}`);
  }
  clone.setAttribute("style", vars.join(";"));

  const xml = new XMLSerializer().serializeToString(clone);
  const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("Could not rasterize the plan view."));
    img.src = src;
  });

  const canvas = document.createElement("canvas");
  canvas.width = w * scale;
  canvas.height = h * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D unavailable.");
  ctx.fillStyle = rootStyle.getPropertyValue("--paper").trim() || "#f4f1ea";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.92);
}

// Recount furniture categories for the elements grid after a room swap, keeping non-furniture
// tallies (doors) intact.
function recountInventory(
  prev: Record<string, number>,
  furniture: ExtractedFurniture[],
): Record<string, number> {
  const inv: Record<string, number> = prev.door ? { door: prev.door } : {};
  for (const f of furniture) inv[f.category] = (inv[f.category] ?? 0) + 1;
  return inv;
}

export default function Studio({
  project,
  onStatus,
}: {
  project?: WorkflowProject | null;
  onStatus?: (s: ProjectStatus) => void;
}) {
  // Guided pipeline: the current stage. Replaces the old read/generate toggle.
  const [step, setStep] = useState<WizardStep>("property");
  const [units, setUnits] = useState<"imperial" | "metric">("metric");

  // Read-layout state (the existing flow).
  const [layout, setLayout] = useState<ExtractedLayout | null>(null);
  const [layoutMetrics, setLayoutMetrics] = useState<LayoutMetrics | null>(null);
  const [file, setFile] = useState<File | null>(null);
  // Space-step room markers (seeds) + the pending marker type awaiting a click on the plan.
  const [markers, setMarkers] = useState<RoomSeed[]>([]);
  const [pendingMarker, setPendingMarker] = useState<{ type: string; label: string } | null>(null);
  // Space-step planning-area polygon (feet) + whether we're drawing it, and the keep-walls toggle.
  // Both re-run detection: the polygon clips the analyzed area, keep-walls skips gap-healing.
  const [planningArea, setPlanningArea] = useState<[number, number][]>([]);
  const [drawingArea, setDrawingArea] = useState(false);
  const [keepWalls, setKeepWalls] = useState(false);

  // Visualization (finishes → photoreal render). Gated on a configured provider key.
  const [finishes, setFinishes] = useState<Record<string, string>>({
    wall: "",
    floor: "",
    palette: "",
    style: "",
  });
  const [renderReady, setRenderReady] = useState(false);
  const [editConfigured, setEditConfigured] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [renderResult, setRenderResult] = useState<string | null>(null);
  // Per-room finish targeting: the room a refine edit is scoped to ("" = whole scene), and an
  // honest record of which finishes were applied to which room (inspectable/reportable).
  const [finishScope, setFinishScope] = useState<string>("");
  const [roomFinishes, setRoomFinishes] = useState<Record<string, Record<string, string>>>({});
  // The source version behind an ADOPTED layout — kept so it can still export report/BIM/CAD via
  // the from-fit endpoints (those read the plan + testfit, which the synthesized layout discards).
  const [adoptedFit, setAdoptedFit] = useState<{ plan: Plan; alternative: Alternative } | null>(null);

  // Generate state — Concept | Detailed sub-mode, kept separate from the read-layout state.
  const [genMode, setGenMode] = useState<"concept" | "detailed">("concept");
  const [concept, setConcept] = useState<ConceptProgram>(DEFAULT_CONCEPT);
  const [detailed, setDetailed] = useState<DetailedProgram>(DEFAULT_DETAILED);
  const [versions, setVersions] = useState<{ plan: Plan; alternatives: Alternative[] } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Instance[]>([]); // Detailed iterate: rooms kept across regenerations

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<"plan" | "space">("plan");
  const [exporting, setExporting] = useState<string | null>(null);
  const [bom, setBom] = useState<Bom | null>(null);

  // Swap state — the selected furniture item OR room, and the fetched alternatives for it.
  const [swapFurniture, setSwapFurniture] = useState<ExtractedFurniture | null>(null);
  const [swapRoom, setSwapRoom] = useState<ExtractedRoom | null>(null);
  const [selectedDoor, setSelectedDoor] = useState<number | null>(null);
  const [swapProducts, setSwapProducts] = useState<Product[] | null>(null);
  const [swapSettings, setSwapSettings] = useState<CatalogSetting[] | null>(null);
  const [swapTab, setSwapTab] = useState<"layouts" | "items">("layouts");
  const [appliedSettingId, setAppliedSettingId] = useState<string | null>(null);
  const [swapBusy, setSwapBusy] = useState(false);

  // Merge-rooms mode — pick two adjacent rooms then union them into one larger space. After a merge
  // the merged room's id + area seed a context-aware furnishing suggestion (never auto-applied).
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [mergeSuggestion, setMergeSuggestion] = useState<{ roomId: string; area: number } | null>(null);

  // Priced bill of materials — fetch when a layout with priced furniture (real SKUs) is shown.
  useEffect(() => {
    if (!layout || !layout.furniture.some((f) => f.list_price != null)) {
      setBom(null);
      return;
    }
    let live = true;
    fetchLayoutBom(layout).then((b) => live && setBom(b)).catch(() => live && setBom(null));
    return () => {
      live = false;
    };
  }, [layout]);

  // Piece-swap alternatives for the selected item's category.
  useEffect(() => {
    if (!swapFurniture) {
      setSwapProducts(null);
      return;
    }
    let live = true;
    setSwapBusy(true);
    fetchProducts(swapFurniture.category)
      .then((p) => live && setSwapProducts(p))
      .catch(() => live && setSwapProducts([]))
      .finally(() => live && setSwapBusy(false));
    return () => {
      live = false;
    };
  }, [swapFurniture]);

  // Room-swap settings that fit the selected room's footprint.
  useEffect(() => {
    if (!swapRoom) {
      setSwapSettings(null);
      return;
    }
    const xs = swapRoom.polygon.map((p) => p[0]);
    const ys = swapRoom.polygon.map((p) => p[1]);
    const w = Math.max(...xs) - Math.min(...xs);
    const h = Math.max(...ys) - Math.min(...ys);
    let live = true;
    setSwapBusy(true);
    fetchSettings(settingTypeForRoom(swapRoom), w, h)
      .then((s) => live && setSwapSettings(s))
      .catch(() => live && setSwapSettings([]))
      .finally(() => live && setSwapBusy(false));
    return () => {
      live = false;
    };
  }, [swapRoom]);

  // Live re-score: whenever the edited layout changes, ask the backend for seats/density/split so
  // the editor's metrics strip reflects the current geometry. Stale responses are ignored.
  useEffect(() => {
    if (!layout) {
      setLayoutMetrics(null);
      return;
    }
    let live = true;
    fetchLayoutMetrics(layout)
      .then((m) => live && setLayoutMetrics(m))
      .catch(() => live && setLayoutMetrics(null));
    return () => {
      live = false;
    };
  }, [layout]);

  // Move a piece to a new bbox min-corner (feet). Re-derive its room_id from the new centre so the
  // open/enclosed metric stays honest after the move.
  const moveFurniture = (key: string, x: number, y: number) => {
    setLayout((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        furniture: prev.furniture.map((f) => {
          if (furnitureKey(f) !== key) return f;
          const cx = x + f.w / 2;
          const cy = y + f.h / 2;
          const room = prev.rooms.find(
            (r) => r.polygon.length >= 3 && pointInPolygon(cx, cy, r.polygon),
          );
          return { ...f, x, y, room_id: room ? room.id : null };
        }),
      };
    });
  };

  // Rotate a piece to a new absolute orientation (degrees). Footprint pieces read their angle from
  // `rotation` alone; a real-outline piece has the angle baked into its polylines, so fold the delta
  // into the outline (about the piece centre) as we update rotation, keeping the two in step.
  const rotateFurniture = (key: string, rotation: number) => {
    setLayout((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        furniture: prev.furniture.map((f) => {
          if (furnitureKey(f) !== key) return f;
          if (!f.outline?.length) return { ...f, rotation };
          const cx = f.x + f.w / 2;
          const cy = f.y + f.h / 2;
          const outline = f.outline.map((ring) =>
            ring.map(([x, y]) => rotatePoint(x, y, cx, cy, rotation - f.rotation)),
          );
          return { ...f, rotation, outline };
        }),
      };
    });
  };

  // Delete a piece and recount the inventory so the elements grid + metrics stay in sync.
  const deleteFurniture = (key: string) => {
    setLayout((prev) => {
      if (!prev) return prev;
      const furniture = prev.furniture.filter((f) => furnitureKey(f) !== key);
      return { ...prev, furniture, inventory: recountInventory(prev.inventory, furniture) };
    });
    setSwapFurniture(null);
  };

  // Does a render provider have a key? Gate the Visualize action on it (never fake a render).
  // `editConfigured` gates the per-surface finish edits (Kontext) separately — they're Replicate-only.
  useEffect(() => {
    let live = true;
    renderStatus()
      .then((s) => {
        if (!live) return;
        setRenderReady(s.configured);
        setEditConfigured(s.edit_configured);
      })
      .catch(() => live && setRenderReady(false));
    return () => {
      live = false;
    };
  }, []);

  // Rasterize the current plan/3D view and send it + the selected finishes for a photoreal render.
  const visualize = async () => {
    // 2D plan lives in .plan-viewport svg; the 2.5D view is .axon-svg — capture whichever is open.
    const svg = document.querySelector<SVGSVGElement>(".plan-viewport svg, .axon-svg");
    if (!svg) {
      setErr("Open the plan or 3D view first.");
      return;
    }
    setRendering(true);
    setErr(null);
    try {
      const png = await captureSvgJpeg(svg);
      const active = Object.fromEntries(Object.entries(finishes).filter(([, v]) => v));
      const { image } = await renderView(png, active);
      if (image) setRenderResult(image);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Render failed.");
    } finally {
      setRendering(false);
    }
  };

  // Targeted per-surface edit — swap ONE finish on the current render via Kontext, leaving the rest
  // intact. Only meaningful once a base render exists; updates the render in place so the user sees
  // just that surface change. When `scope` names a room, the edit is confined to it and recorded in
  // `roomFinishes` (honest, per-room); a whole-scene edit records into `finishes` as before.
  const editSurface = async (field: string, value: string, scope: string) => {
    if (!renderResult || !value) return;
    setRendering(true);
    setErr(null);
    try {
      const { image } = await renderEditView(renderResult, field, value, scope || undefined);
      if (image) setRenderResult(image);
      if (scope) {
        setRoomFinishes((prev) => ({ ...prev, [scope]: { ...prev[scope], [field]: value } }));
      } else {
        setFinishes((prev) => ({ ...prev, [field]: value }));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Edit failed.");
    } finally {
      setRendering(false);
    }
  };

  // Keyboard-dismiss the render overlay (mouse-only dismiss strands keyboard users).
  useEffect(() => {
    if (!renderResult) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setRenderResult(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [renderResult]);

  // Change a room's type from the editor's property panel — recolours + re-scores immediately.
  const changeRoomType = (roomId: string, type: string) => {
    setLayout((prev) =>
      prev ? { ...prev, rooms: prev.rooms.map((r) => (r.id === roomId ? { ...r, type } : r)) } : prev,
    );
    setSwapRoom((r) => (r && r.id === roomId ? { ...r, type } : r));
  };

  // Drop the pending marker where the user clicked the plan (world feet).
  const placeMarker = (x: number, y: number) => {
    if (!pendingMarker) return;
    setMarkers((m) => [...m, { ...pendingMarker, x, y }]);
    setPendingMarker(null);
  };
  // Append a planning-area vertex where the user clicked the plan (world feet).
  const addAreaVertex = (x: number, y: number) => setPlanningArea((a) => [...a, [x, y]]);
  // Toggle planning-area draw mode. Starting clears any prior polygon (draw fresh) and cancels a
  // pending marker (one placement mode at a time); stopping discards a polygon too small to use.
  const toggleAreaDraw = () => {
    setPendingMarker(null);
    setDrawingArea((on) => {
      if (on) {
        setPlanningArea((a) => (a.length >= 3 ? a : []));
        return false;
      }
      setPlanningArea([]);
      return true;
    });
  };
  // Re-run detection: markers seed segmentation, the polygon clips the analyzed area, keep-walls
  // skips gap-healing (explicit — re-ingest is a few seconds).
  const reDetect = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    setDrawingArea(false);
    dismissSwap();
    try {
      setLayout(await ingestCad(file, markers, planningArea, keepWalls));
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  const selectFurniture = (f: ExtractedFurniture) => {
    setSwapRoom(null);
    setSelectedDoor(null);
    setSwapFurniture(f);
  };
  const selectRoom = (r: ExtractedRoom) => {
    setSwapFurniture(null);
    setSelectedDoor(null);
    setSwapRoom(r);
    setSwapTab("layouts");
    setAppliedSettingId(null);
  };
  const selectDoor = (index: number) => {
    setSwapFurniture(null);
    setSwapRoom(null);
    setSelectedDoor(index);
  };
  const dismissSwap = () => {
    setSwapFurniture(null);
    setSwapRoom(null);
    setSelectedDoor(null);
    setAppliedSettingId(null);
  };

  // Edit the selected door in place — flip its swing side, flip the swing direction (rotate the
  // opening 180°), or nudge it along its own wall (the leaf direction). Fully back-compatible: an
  // unset `flip` reads as false.
  const editDoor = (index: number, patch: Partial<ExtractedDoor>) => {
    setLayout((prev) =>
      prev ? { ...prev, doors: prev.doors.map((d, i) => (i === index ? { ...d, ...patch } : d)) } : prev,
    );
  };
  const nudgeDoorAlongWall = (index: number, feet: number) => {
    setLayout((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        doors: prev.doors.map((d, i) => {
          if (i !== index) return d;
          const rad = (d.rotation * Math.PI) / 180;
          return { ...d, x: d.x + feet * Math.cos(rad), y: d.y + feet * Math.sin(rad) };
        }),
      };
    });
  };

  // Merge mode is exclusive with the swap panels — entering it dismisses any open swap + suggestion,
  // leaving it clears the pending pick, so the two flows never fight over a room click.
  const toggleMergeMode = () => {
    dismissSwap();
    setMergeSuggestion(null);
    setMergeSelection([]);
    setMergeMode((on) => !on);
  };
  // Pick / unpick a room for the merge (max two — a third pick slides out the oldest).
  const toggleMergeRoom = (r: ExtractedRoom) => {
    setMergeSelection((sel) =>
      sel.includes(r.id)
        ? sel.filter((id) => id !== r.id)
        : sel.length < 2
          ? [...sel, r.id]
          : [sel[1], r.id],
    );
  };
  // Union the two picked rooms into one, then select the merged room's id + area to seed the
  // context-aware suggestion. Never auto-swaps furniture — the user chooses from the panel.
  async function applyMerge() {
    if (!layout || mergeSelection.length !== 2) return;
    const [idA, idB] = mergeSelection;
    setSwapBusy(true);
    setErr(null);
    try {
      const next = await mergeRooms(layout, idA, idB);
      setLayout(next);
      const merged = next.rooms.find((r) => r.id === idA);
      setMergeMode(false);
      setMergeSelection([]);
      if (merged) setMergeSuggestion({ roomId: merged.id, area: merged.area_sf ?? 0 });
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setSwapBusy(false);
    }
  }

  // Piece swap — replace the selected item with a catalog product, keeping its centre + rotation.
  // Applies INSTANTLY (footprint) so it feels real-time, then upgrades to the SKU's real plan shape
  // when the model library responds — both target the item by index so the second update lands.
  function applyPieceSwap(p: Product) {
    if (!layout || !swapFurniture) return;
    const key = furnitureKey(swapFurniture);
    const idx = layout.furniture.findIndex((f) => furnitureKey(f) === key);
    if (idx < 0) return;
    const cur = layout.furniture[idx];
    const cx = cur.x + cur.w / 2;
    const cy = cur.y + cur.h / 2;

    const at = (f: ExtractedFurniture, w: number, h: number, outline?: [number, number][][]) => ({
      ...f, brand: p.brand, model: p.model, list_price: p.list_price ?? null,
      w, h, x: cx - w / 2, y: cy - h / 2, outline,
    });
    setLayout({
      ...layout,
      furniture: layout.furniture.map((f, i) => (i === idx ? at(f, p.w, p.h) : f)),
    });
    dismissSwap();

    // Upgrade to real geometry in the background; ignore if the slot was swapped again meanwhile.
    fetchGeometry(p.model)
      .then((geo) => {
        if (!geo.outline?.length) return;
        setLayout((prev) => {
          if (!prev || prev.furniture[idx]?.model !== p.model) return prev;
          const out = placeOutline(geo.outline, cx, cy);
          return {
            ...prev,
            furniture: prev.furniture.map((f, i) => (i === idx ? at(f, geo.w, geo.h, out) : f)),
          };
        });
      })
      .catch(() => {/* keep the footprint box */});
  }

  // Room swap — drop a setting's furniture into the room (anchored to its bbox min-corner),
  // replacing every piece whose centre currently falls inside the room. Each placed piece gets its
  // SKU's real plan shape from the product-model library (footprint box when it doesn't resolve).
  async function applyRoomSwap(s: CatalogSetting) {
    if (!layout || !swapRoom) return;
    const poly = swapRoom.polygon;
    const minx = Math.min(...poly.map((p) => p[0]));
    const miny = Math.min(...poly.map((p) => p[1]));
    const kept = layout.furniture.filter(
      (f) => !pointInPolygon(f.x + f.w / 2, f.y + f.h / 2, poly),
    );

    // Only real furniture — drop the un-spec'd CET sub-component blocks (chair bases/brackets) and
    // glass panels/mullions, exactly as the backend slot_settings does, so a room swap doesn't
    // reintroduce the overlapping tangle.
    const pieces = s.furniture.filter((sf) => SLOT_CATS.has(sf.category));

    // Fetch each DISTINCT SKU's geometry once (5 identical chairs = 1 request); failures fall back.
    const skus = [...new Set(pieces.map((sf) => sf.model).filter(Boolean))];
    const geoms = new Map<string, SymbolGeometry>();
    await Promise.all(
      skus.map(async (sku) => {
        try {
          const g = await fetchGeometry(sku);
          if (g.outline?.length) geoms.set(sku, g);
        } catch {
          /* no model geometry — footprint box */
        }
      }),
    );

    const placed: ExtractedFurniture[] = pieces.map((sf) => {
      const geo = sf.model ? geoms.get(sf.model) : undefined;
      const w = geo ? geo.w : sf.w;
      const h = geo ? geo.h : sf.h;
      const cx = minx + sf.dx + sf.w / 2;
      const cy = miny + sf.dy + sf.h / 2;
      return {
        category: sf.category,
        block_name: "",
        brand: sf.brand,
        model: sf.model,
        list_price: sf.list_price ?? null,
        x: cx - w / 2,
        y: cy - h / 2,
        w,
        h,
        rotation: sf.rotation,
        outline: geo ? placeOutline(geo.outline, cx, cy) : undefined,
      };
    });
    const furniture = [...kept, ...placed];
    setLayout({ ...layout, furniture, inventory: recountInventory(layout.inventory, furniture) });
    // Keep the palette open so the applied arrangement reads as selected and others stay a click away.
    setAppliedSettingId(s.id);
  }

  async function readLayout(f: File) {
    setBusy(true);
    setErr(null);
    setLayout(null);
    setAdoptedFit(null);
    setMarkers([]);
    setPendingMarker(null);
    setPlanningArea([]);
    setDrawingArea(false);
    setKeepWalls(false);
    dismissSwap();
    setFile(f);
    try {
      // Read the REAL layout from the CAD — walls, rooms, and a furniture inventory straight from
      // the drawing's blocks. The 2D plan, 3D space, and inventory all read from this one object.
      setLayout(await ingestCad(f));
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function generate(f: File) {
    setBusy(true);
    setErr(null);
    setVersions(null);
    setSelectedId(null);
    setPinned([]);
    setAdoptedFit(null);
    setFile(f);
    onStatus?.("processing");
    try {
      // Generate scored test-fit versions from the plate + the program (Concept brief or the
      // explicit Detailed counts), then compare them side by side and open one in 2D / 3D.
      const res =
        genMode === "detailed"
          ? await generateDetailed(f, detailed)
          : await generateFromConcept(f, concept);
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
      if (res.alternatives.length === 0) {
        setErr("No test-fit versions could be generated for this plate + program. Try adjusting the program.");
      } else {
        onStatus?.("ready");
        setStep("review");
      }
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  // Iterate: regenerate Detailed versions keeping the pinned rooms (they persist at exact coords).
  async function regenerate() {
    if (!versions) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await iterateDetailed({ plan: versions.plan, program: detailed, locked: pinned });
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  // Adopt the selected generated version as a read-layout — synthesize the ExtractedLayout and
  // open it in Read mode, so the generated design gets the full room/wall/inventory treatment.
  function adoptLayout() {
    const sel = versions?.alternatives.find((a) => a.id === selectedId);
    if (!versions || !sel) return;
    dismissSwap();
    setLayout(layoutFromFit(versions.plan, sel.testfit.instances));
    setAdoptedFit({ plan: versions.plan, alternative: sel });
    setStep("review");
    setView("plan");
  }

  const togglePin = (it: Instance) => {
    const key = instanceKey(it);
    setPinned((prev) =>
      prev.some((p) => instanceKey(p) === key) ? prev.filter((p) => instanceKey(p) !== key) : [...prev, it],
    );
  };
  const pinnedKeys = useMemo(() => new Set(pinned.map(instanceKey)), [pinned]);
  const canPin = step === "review" && genMode === "detailed";

  // Which pipeline steps are reachable given progress (uploaded a plate / generated versions).
  const reachable = (s: WizardStep): boolean => {
    if (s === "property" || s === "space") return true;
    if (s === "review") return !!versions;
    return !!file; // program, visualize need a plate
  };
  const goStep = (s: WizardStep) => {
    if (!reachable(s)) return;
    setErr(null);
    dismissSwap();
    setStep(s);
  };

  async function runExport(kind: string, fn: () => Promise<void>) {
    if (!file) return;
    setErr(null);
    setExporting(kind);
    try {
      await fn();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setExporting(null);
    }
  }


  const building = file?.name.replace(/\.(dxf|dwg)$/i, "") ?? "Plan";
  const inv = layout?.inventory ?? {};
  const rooms = (layout?.rooms ?? []).filter((r) => r.label);
  const selected = versions?.alternatives.find((a) => a.id === selectedId) ?? null;

  // Rooms a finish edit can be scoped to — labelled rooms from a read layout, else the distinct
  // nameable room types in the selected generated version. Empty = only whole-scene edits offered.
  const finishScopes = Array.from(
    new Set(
      rooms.length
        ? rooms.map((r) => r.label!)
        : (selected?.testfit.instances ?? [])
            .map((i) => ROOM_SCOPE_PHRASE[i.type])
            .filter(Boolean),
    ),
  );

  const STEP_ORDER: WizardStep[] = ["property", "space", "program", "visualize", "review"];
  const stepIdx = STEP_ORDER.indexOf(step);
  const prevStep = stepIdx > 0 ? STEP_ORDER[stepIdx - 1] : null;
  const nextStep = stepIdx < STEP_ORDER.length - 1 ? STEP_ORDER[stepIdx + 1] : null;
  const reviewAdopted = step === "review" && !!adoptedFit;

  const viewToggle = (
    <div className="stage-tools">
      <Segmented
        value={view}
        onChange={setView}
        options={[
          { value: "plan", label: "Plan" },
          { value: "space", label: "3D Space" },
        ]}
      />
    </div>
  );

  const layoutStage = layout && (
    <>
      {viewToggle}
      {view === "space" ? (
        <SpaceView layout={layout} />
      ) : (
        <PlanCanvas
          layout={layout}
          selectedFurnitureKey={swapFurniture ? furnitureKey(swapFurniture) : null}
          onSelectFurniture={selectFurniture}
          selectedRoomId={swapRoom?.id ?? null}
          onSelectRoom={selectRoom}
          mergeSelection={mergeMode ? mergeSelection : undefined}
          onToggleMergeRoom={mergeMode ? toggleMergeRoom : undefined}
          onMoveFurniture={moveFurniture}
          onRotateFurniture={rotateFurniture}
          onDeleteFurniture={deleteFurniture}
          selectedDoorIndex={selectedDoor}
          onSelectDoor={selectDoor}
          markers={step === "space" ? markers : undefined}
          placing={step === "space" && !!pendingMarker}
          onPlacePoint={step === "space" ? placeMarker : undefined}
          planningArea={step === "space" && planningArea.length ? planningArea : undefined}
          drawingArea={step === "space" && drawingArea}
          onAreaPoint={step === "space" ? addAreaVertex : undefined}
        />
      )}
      {renderResult && (
        <div className="render-overlay" role="dialog" aria-label="Photoreal render" onClick={() => setRenderResult(null)}>
          <img className="render-result" src={renderResult} alt="Photoreal render of the layout" />
          <span className="render-dismiss-hint">Click or press Esc to dismiss</span>
        </div>
      )}
    </>
  );

  const fitStage = versions && selected && (
    <>
      {viewToggle}
      {view === "space" ? (
        <SpaceView plan={versions.plan} instances={selected.testfit.instances} />
      ) : (
        <PlanCanvas
          plan={versions.plan}
          instances={selected.testfit.instances}
          pinnedKeys={canPin ? pinnedKeys : undefined}
          onTogglePin={canPin ? togglePin : undefined}
        />
      )}
    </>
  );

  const emptyStage = (glyph: string, msg: string) => (
    <div className="empty">
      <div className="glyph">{glyph}</div>
      <p>{msg}</p>
    </div>
  );

  const stageBody =
    step === "review"
      ? reviewAdopted
        ? layoutStage
        : fitStage || emptyStage("◳", "Set a program and generate to lay out three scored test-fits.")
      : layout
        ? layoutStage
        : emptyStage(
            "⌟",
            step === "space"
              ? "Drop a floor plate — walls by type, rooms and a furniture inventory, straight from your CAD."
              : "Upload a floor plate in the Space step first.",
          );

  // Editing panels shared by Space (inspect the plate) and Review (edit an adopted design).
  const mergeableRooms = layout ? layout.rooms.filter((r) => r.polygon.length >= 3).length : 0;
  const mergedRoom =
    mergeSuggestion && layout
      ? layout.rooms.find((r) => r.id === mergeSuggestion.roomId) ?? null
      : null;
  const editingPanels = layout && (
    <>
      {mergeableRooms >= 2 && (
        <div className="merge-rooms">
          <div className="swap-head">
            <Eyebrow>Merge rooms</Eyebrow>
            <button
              type="button"
              className={`link-btn${mergeMode ? " is-on" : ""}`}
              aria-pressed={mergeMode}
              onClick={toggleMergeMode}
            >
              {mergeMode ? "Cancel" : "Start"}
            </button>
          </div>
          {mergeMode && (
            <>
              <p className="disclaim" style={{ marginBottom: 10 }}>
                Pick two adjacent rooms on the plan, then merge them into one larger space.
              </p>
              <button
                type="button"
                className="export-btn export-btn--primary"
                disabled={mergeSelection.length !== 2 || swapBusy}
                onClick={applyMerge}
              >
                <span className="export-btn-label">{swapBusy ? "Merging…" : "Merge these two rooms"}</span>
                <span className="export-btn-meta">{mergeSelection.length} of 2 picked</span>
              </button>
            </>
          )}
        </div>
      )}
      {mergeSuggestion && mergedRoom && (
        <Callout>
          This is now a {num(mergeSuggestion.area)} sf enclosed room —{" "}
          {mergeSuggestion.area >= BOARDROOM_MIN_SF ? "a boardroom-scale layout" : "a larger meeting layout"}{" "}
          fits here.{" "}
          <button
            type="button"
            className="link-btn"
            onClick={() => { selectRoom(mergedRoom); setMergeSuggestion(null); }}
          >
            Show layouts
          </button>
        </Callout>
      )}
      {swapFurniture && (
        <SwapPanel
          title={`Swap · ${swapFurniture.category}`}
          busy={swapBusy}
          empty={!!swapProducts && swapProducts.length === 0}
          preview={
            <>
              <ShapeThumb outline={swapFurniture.outline} w={swapFurniture.w} h={swapFurniture.h} />
              <span className="swap-current">
                {swapFurniture.model ? `${swapFurniture.brand} ${swapFurniture.model}` : "Selected piece"}
              </span>
            </>
          }
          onDismiss={dismissSwap}
        >
          <button type="button" className="export-btn is-danger" onClick={() => deleteFurniture(furnitureKey(swapFurniture))}>
            <span className="export-btn-label">Remove this piece</span>
            <span className="export-btn-meta">delete · drag on plan to move</span>
          </button>
          {swapProducts?.map((p, i) => (
            <button type="button" className="export-btn" key={`${p.brand}-${p.model}-${i}`} onClick={() => applyPieceSwap(p)}>
              <span className="export-btn-label">{p.brand} {p.model}</span>
              <span className="export-btn-meta">{priceMeta(p.list_price, swapFurniture.list_price)}</span>
            </button>
          ))}
        </SwapPanel>
      )}
      {swapRoom && (
        <SwapPanel
          title={`Room · ${swapRoom.label || "Room"}`}
          busy={swapBusy}
          empty={!!swapSettings && swapSettings.length === 0}
          onDismiss={dismissSwap}
        >
          <div className="room-props">
            <label className="brief-field">
              <span className="brief-label">Type</span>
              <select
                className="ds-input"
                value={ROOM_TYPES.some((t) => t.type === swapRoom.type) ? swapRoom.type : "unknown"}
                onChange={(e) => changeRoomType(swapRoom.id, e.target.value)}
              >
                {ROOM_TYPES.map((t) => (
                  <option key={t.type} value={t.type}>{t.label}</option>
                ))}
              </select>
            </label>
            <div className="prop-recap" style={{ marginTop: 4 }}>
              <div className="prop-row"><span className="prop-k">Area</span><span className="prop-v">{swapRoom.area_sf ? `${num(swapRoom.area_sf)} sf` : "—"}</span></div>
              {swapRoom.polygon.length >= 3 && (() => {
                const xs = swapRoom.polygon.map((p) => p[0]);
                const ys = swapRoom.polygon.map((p) => p[1]);
                const w = Math.max(...xs) - Math.min(...xs);
                const h = Math.max(...ys) - Math.min(...ys);
                return <div className="prop-row"><span className="prop-k">Dimensions</span><span className="prop-v">{num(w)}′ × {num(h)}′</span></div>;
              })()}
              <div className="prop-row"><span className="prop-k">Character</span><span className="prop-v">{ENCLOSED_TYPES.has(swapRoom.type) ? "Enclosed" : "Open"}</span></div>
            </div>
            <Eyebrow style={{ display: "block", margin: "16px 0 8px" }}>Swap furnishing</Eyebrow>
          </div>
          <Segmented
            options={[
              { value: "layouts", label: "Layouts" },
              { value: "items", label: "Items" },
            ]}
            value={swapTab}
            onChange={setSwapTab}
          />
          {swapTab === "layouts" ? (
            <div className="arr-palette" role="group" aria-label="Room layouts">
              {swapSettings?.map((s) => {
                const pcs = s.furniture.filter((sf) => SLOT_CATS.has(sf.category)).length;
                const selected = appliedSettingId === s.id;
                return (
                  <button
                    type="button"
                    key={s.id}
                    className={`arr-card${selected ? " is-selected" : ""}`}
                    aria-pressed={selected}
                    aria-label={`${settingLabel(s.setting_type)}, ${num(s.sqft)} square feet, ${pcs} pieces`}
                    onClick={() => applyRoomSwap(s)}
                  >
                    <ArrangementThumb setting={s} />
                    <span className="arr-label">{settingLabel(s.setting_type)}</span>
                    <span className="arr-meta">{num(s.sqft)} sf · {pcs} pcs</span>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="room-items">
              <p className="disclaim">Select a piece on the plan to swap it.</p>
              <div className="rooms-list">
                {layout.furniture
                  .filter(
                    (f) =>
                      SLOT_CATS.has(f.category) &&
                      pointInPolygon(f.x + f.w / 2, f.y + f.h / 2, swapRoom.polygon),
                  )
                  .map((f, i) => (
                    <div className="room-row" key={`${f.category}-${i}`}>
                      <span className="rm-label">{f.category}</span>
                      <span className="rm-area">{f.model ? `${f.brand} ${f.model}` : "—"}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}
        </SwapPanel>
      )}
      {selectedDoor != null && layout.doors[selectedDoor] && (() => {
        const idx = selectedDoor;
        const d = layout.doors[idx];
        return (
          <SwapPanel title="Door" busy={false} empty={false} onDismiss={dismissSwap}>
            <div className="room-props">
              <div className="prop-recap">
                <div className="prop-row"><span className="prop-k">Leaf</span><span className="prop-v">{(d.width * 12).toFixed(0)}″</span></div>
                <div className="prop-row"><span className="prop-k">Angle</span><span className="prop-v">{Math.round(((d.rotation % 360) + 360) % 360)}°</span></div>
              </div>
              <Eyebrow style={{ display: "block", margin: "16px 0 8px" }}>Swing</Eyebrow>
            </div>
            <button type="button" className="export-btn" onClick={() => editDoor(idx, { flip: !d.flip })}>
              <span className="export-btn-label">Flip swing side</span>
              <span className="export-btn-meta">mirror the arc</span>
            </button>
            <button type="button" className="export-btn" onClick={() => editDoor(idx, { rotation: (((d.rotation + 180) % 360) + 360) % 360 })}>
              <span className="export-btn-label">Flip swing direction</span>
              <span className="export-btn-meta">in / out</span>
            </button>
            <button type="button" className="export-btn" onClick={() => nudgeDoorAlongWall(idx, -0.5)}>
              <span className="export-btn-label">Nudge along wall</span>
              <span className="export-btn-meta">−6″</span>
            </button>
            <button type="button" className="export-btn" onClick={() => nudgeDoorAlongWall(idx, 0.5)}>
              <span className="export-btn-label">Nudge along wall</span>
              <span className="export-btn-meta">+6″</span>
            </button>
          </SwapPanel>
        );
      })()}
      <div>
        <Eyebrow style={{ display: "block", marginBottom: 14 }}>Elements · bill of components</Eyebrow>
        <div className="el-grid">
          {INVENTORY_ROWS.filter((r) => inv[r.key]).map((r) => (
            <ElCount key={r.key} n={inv[r.key]} k={r.label} />
          ))}
        </div>
        <p className="disclaim" style={{ marginTop: 12 }}>
          Read straight from the CAD — counted from named blocks, with brand &amp; model where the drawing carries it.
        </p>
      </div>
      {rooms.length > 0 && (
        <>
          <hr className="ds-rule" />
          <div>
            <Eyebrow style={{ display: "block", marginBottom: 12 }}>Rooms · {rooms.length}</Eyebrow>
            <div className="rooms-list">
              {rooms.map((r) => (
                <div className="room-row" key={r.id}>
                  <span className="rm-label">
                    {r.label}
                    {r.type && r.type !== "unknown" && (
                      <span className="rm-type">{ROOM_TYPE_LABEL[r.type] ?? r.type}</span>
                    )}
                  </span>
                  <span className="rm-area">{r.area_sf ? `${num(r.area_sf)} sf` : "—"}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
      {bom && bom.lines.length > 0 && (
        <>
          <hr className="ds-rule" />
          <div>
            <Eyebrow style={{ display: "block", marginBottom: 12 }}>Bill of materials · priced</Eyebrow>
            <div className="bom-list">
              {bom.lines.map((l, i) => (
                <div className="bom-line" key={`${l.model}-${i}`}>
                  <span className="bom-name">{l.qty}× {l.brand} {l.model}</span>
                  <span className="bom-amt">{money(l.line_total, bom.currency)}</span>
                </div>
              ))}
              <div className="bom-line bom-total">
                <span className="bom-name">Total · {bom.priced_items} priced</span>
                <span className="bom-amt">{money(bom.total, bom.currency)}</span>
              </div>
            </div>
          </div>
        </>
      )}
      {layout.needs_confirmation && (
        <Callout quiet>
          Room boundaries are best-effort where the drawing's walls don't fully close — labels and counts
          are exact; confirm boundaries before fabrication.
        </Callout>
      )}
    </>
  );

  // Live metric strip + program tree, shared by Space (the read plate) and Review (adopted design).
  // Target is the detailed program only when the layout was generated from it — read plates show
  // detected counts with no target.
  const editorMetrics = layout && layoutMetrics && (
    <>
      <LayoutMetricsStrip m={layoutMetrics} />
      <ProgramTree
        rooms={layout.rooms}
        target={layout.source === "generated" && genMode === "detailed" ? detailed : null}
      />
    </>
  );

  return (
    <main className="studio studio-wizard">
      <WizardStepper step={step} onStep={goStep} reachable={reachable} />

      <section className="stage">{stageBody}</section>

      <aside className="panel">
        {err && <div className="err" role="alert">{err}</div>}

        {step === "property" && (
          <div className="wizard-panel">
            <Eyebrow style={{ display: "block", marginBottom: 12 }}>Property</Eyebrow>
            <div className="prop-recap">
              <div className="prop-row"><span className="prop-k">Name</span><span className="prop-v">{project?.name ?? "—"}</span></div>
              <div className="prop-row"><span className="prop-k">Address</span><span className="prop-v">{project?.address || "—"}</span></div>
              <div className="prop-row"><span className="prop-k">Floor</span><span className="prop-v">{project?.floor || "—"}</span></div>
            </div>
            <div className="brief-field" style={{ marginTop: 16 }}>
              <span className="brief-label">Units</span>
              <Segmented
                value={units}
                onChange={setUnits}
                options={[
                  { value: "metric", label: "Metric · sqm" },
                  { value: "imperial", label: "Imperial · sqft" },
                ]}
              />
            </div>
            <p className="disclaim" style={{ marginTop: 14 }}>
              Working in {units === "metric" ? "square metres" : "square feet"}. Next: upload the floor plate.
            </p>
          </div>
        )}

        {step === "space" && (
          <>
            <Dropzone busy={busy} onFile={readLayout} />
            {editorMetrics}
            {layout && (
              <div className="markers">
                <Eyebrow style={{ display: "block", marginBottom: 10 }}>Mark rooms · guide detection</Eyebrow>
                <p className="disclaim" style={{ marginBottom: 10 }}>
                  Pick a type, then click the plan to place it — detection will treat that spot as that room.
                </p>
                <div className="marker-palette">
                  {MARKER_TYPES.map((m) => (
                    <button
                      key={m.type}
                      type="button"
                      className={`marker-chip${pendingMarker?.type === m.type ? " is-active" : ""}`}
                      onClick={() => { setDrawingArea(false); setPendingMarker(pendingMarker?.type === m.type ? null : m); }}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                {pendingMarker && (
                  <Callout>Click on the plan to place <b>{pendingMarker.label}</b>. <button type="button" className="link-btn" onClick={() => setPendingMarker(null)}>Cancel</button></Callout>
                )}
                {markers.length > 0 && (
                  <div className="markers-list">
                    {markers.map((m, i) => (
                      <div className="marker-row" key={i}>
                        <span className="marker-row-label">{m.label}</span>
                        <button type="button" className="marker-del" aria-label={`Remove ${m.label}`} onClick={() => setMarkers(markers.filter((_, j) => j !== i))}>×</button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="swap-head" style={{ marginTop: 16 }}>
                  <Eyebrow>Planning area</Eyebrow>
                  <button type="button" className={`link-btn${drawingArea ? " is-on" : ""}`} aria-pressed={drawingArea} onClick={toggleAreaDraw}>
                    {drawingArea ? "Cancel" : "Mark area"}
                  </button>
                </div>
                <p className="disclaim" style={{ marginBottom: 10 }}>
                  Draw a polygon to restrict analysis to that area — rooms, walls, and furniture outside it are dropped.
                </p>
                {drawingArea && (
                  <Callout>
                    Click the plan to add corners — <b>{planningArea.length}</b> placed{planningArea.length < 3 ? " (need 3+)" : ""}.
                    {planningArea.length > 0 && <> <button type="button" className="link-btn" onClick={() => setPlanningArea([])}>Clear</button></>}
                  </Callout>
                )}
                {!drawingArea && planningArea.length >= 3 && (
                  <div className="marker-row">
                    <span className="marker-row-label">Planning area · {planningArea.length} corners</span>
                    <button type="button" className="marker-del" aria-label="Remove planning area" onClick={() => setPlanningArea([])}>×</button>
                  </div>
                )}

                <div className="swap-head" style={{ marginTop: 16 }}>
                  <Eyebrow>Walls</Eyebrow>
                </div>
                <Segmented
                  value={keepWalls ? "keep" : "heal"}
                  onChange={(v) => setKeepWalls(v === "keep")}
                  options={[
                    { value: "heal", label: "Heal gaps" },
                    { value: "keep", label: "As drawn" },
                  ]}
                />
                <p className="disclaim" style={{ marginTop: 8 }}>
                  {keepWalls
                    ? "Walls are used exactly as drawn — near-miss partition gaps are left open."
                    : "Near-miss partition gaps are bridged so rooms separate cleanly."}
                </p>

                {(markers.length > 0 || planningArea.length >= 3 || keepWalls) && (
                  <button className="export-btn export-btn--primary" style={{ marginTop: 14, width: "100%" }} onClick={reDetect} disabled={busy}>
                    <span className="export-btn-label">{busy ? "Re-detecting…" : "Re-detect"}</span>
                    <span className="export-btn-meta">
                      {[
                        markers.length ? `${markers.length} marker${markers.length === 1 ? "" : "s"}` : null,
                        planningArea.length >= 3 ? "clipped" : null,
                        keepWalls ? "walls as drawn" : null,
                      ].filter(Boolean).join(" · ")}
                    </span>
                  </button>
                )}
              </div>
            )}
            {editingPanels}
          </>
        )}

        {step === "program" && (
          <>
            <div className="brief-field">
              <Segmented
                value={genMode}
                onChange={(m) => { setGenMode(m); setErr(null); }}
                options={[
                  { value: "concept", label: "Concept" },
                  { value: "detailed", label: "Detailed" },
                ]}
              />
            </div>
            {!file && <Callout quiet>Upload a floor plate in the Space step to enable generation.</Callout>}
            {genMode === "concept" ? (
              <ConceptForm concept={concept} onChange={setConcept} busy={busy} file={file} onGenerate={generate} hasVersions={!!versions} />
            ) : (
              <DetailedForm program={detailed} onChange={setDetailed} busy={busy} file={file} onGenerate={generate} hasVersions={!!versions} />
            )}
          </>
        )}

        {step === "visualize" && (
          renderReady ? (
            <FinishesPanel
              finishes={finishes}
              onChange={setFinishes}
              onVisualize={visualize}
              busy={rendering}
              hasRender={!!renderResult}
              editConfigured={editConfigured}
              onEditSurface={editSurface}
              scopes={finishScopes}
              scope={finishScope}
              onScope={setFinishScope}
              roomFinishes={roomFinishes}
            />
          ) : (
            <Callout quiet>
              Photoreal render needs a provider key (RENDER_API_KEY or REPLICATE_API_TOKEN) in the backend.
              You can still set finishes and generate the test-fits.
            </Callout>
          )
        )}

        {step === "review" && (
          reviewAdopted ? (
            <>
              <button type="button" className="link-btn" style={{ marginBottom: 12 }} onClick={() => { setAdoptedFit(null); dismissSwap(); }}>
                ← Back to versions
              </button>
              {editorMetrics}
              {editingPanels}
              <hr className="ds-rule" />
              <div className="exports">
                <Eyebrow style={{ display: "block", marginBottom: 14 }}>Export · deliverables</Eyebrow>
                <div className="export-actions">
                  <button className="export-btn export-btn--primary" onClick={() => runExport("takeoff", () => downloadTakeoffFromLayout(layout!))} disabled={!!exporting}>
                    <span className="export-btn-label">Quantity takeoff</span>
                    <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · 9 sheets"}</span>
                  </button>
                  {adoptedFit && (
                    <>
                      <button className="export-btn" onClick={() => runExport("report", () => downloadReport({ project: { client: project?.address ?? "", building, style: "Modern", floor: project?.floor ?? "" }, plan: adoptedFit.plan, alternatives: [adoptedFit.alternative] }))} disabled={!!exporting}>
                        <span className="export-btn-label">Space-planning report</span>
                        <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF"}</span>
                      </button>
                      <button className="export-btn" onClick={() => runExport("ifc", () => downloadIfcFromFit({ plan: adoptedFit.plan, testfit: adoptedFit.alternative.testfit }))} disabled={!!exporting}>
                        <span className="export-btn-label">BIM model</span>
                        <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                      </button>
                      <button className="export-btn" onClick={() => runExport("dxf", () => downloadDxfFromFit({ plan: adoptedFit.plan, testfit: adoptedFit.alternative.testfit }))} disabled={!!exporting}>
                        <span className="export-btn-label">CAD drawing</span>
                        <span className="export-btn-meta">{exporting === "dxf" ? "Preparing…" : "DXF"}</span>
                      </button>
                    </>
                  )}
                </div>
              </div>
            </>
          ) : (
            <>
              <VersionList versions={versions} selectedId={selectedId} onSelect={setSelectedId} />
              {canPin && versions && (
                <>
                  <hr className="ds-rule" />
                  <div className="iterate">
                    <Eyebrow style={{ display: "block", marginBottom: 10 }}>Iterate · pin &amp; regenerate</Eyebrow>
                    <p className="disclaim" style={{ marginBottom: 12 }}>
                      Click rooms on the plan to pin them, adjust the program, then regenerate — pinned rooms stay put.
                    </p>
                    <div className="iterate-head">
                      <span className="brief-label">{pinned.length} pinned</span>
                      {pinned.length > 0 && (
                        <button type="button" className="link-btn" onClick={() => setPinned([])}>Clear</button>
                      )}
                    </div>
                    <button className="export-btn export-btn--primary" style={{ marginTop: 10, width: "100%" }} onClick={regenerate} disabled={busy}>
                      <span className="export-btn-label">{busy ? "Regenerating…" : "Regenerate"}</span>
                      <span className="export-btn-meta">{pinned.length > 0 ? `keep ${pinned.length} pinned` : "re-place all"}</span>
                    </button>
                  </div>
                </>
              )}
              {versions && selected && (
                <>
                  <hr className="ds-rule" />
                  <div className="adopt">
                    <Eyebrow style={{ display: "block", marginBottom: 10 }}>Edit · adopt a version</Eyebrow>
                    <p className="disclaim" style={{ marginBottom: 12 }}>
                      Open version {selected.id} in the editor — rooms, partitions and desks become editable; swap, move and delete.
                    </p>
                    <button className="export-btn export-btn--primary" style={{ width: "100%" }} onClick={adoptLayout} disabled={busy}>
                      <span className="export-btn-label">Open in editor</span>
                      <span className="export-btn-meta">→ edit · swap · export</span>
                    </button>
                  </div>
                  <hr className="ds-rule" />
                  <div className="exports">
                    <Eyebrow style={{ display: "block", marginBottom: 14 }}>Export · version {selected.id}</Eyebrow>
                    <div className="export-actions">
                      <button className="export-btn export-btn--primary" onClick={() => runExport("report", () => downloadReport({ project: { client: project?.address ?? "", building, style: "Modern", floor: project?.floor ?? "" }, plan: versions.plan, alternatives: versions.alternatives }))} disabled={!!exporting}>
                        <span className="export-btn-label">Space-planning report</span>
                        <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF · 3 options"}</span>
                      </button>
                      <button className="export-btn" onClick={() => runExport("takeoff", () => downloadTakeoffFromFit({ plan: versions.plan, testfit: selected.testfit }))} disabled={!!exporting}>
                        <span className="export-btn-label">Quantity takeoff</span>
                        <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · BOM"}</span>
                      </button>
                      <button className="export-btn" onClick={() => runExport("ifc", () => downloadIfcFromFit({ plan: versions.plan, testfit: selected.testfit }))} disabled={!!exporting}>
                        <span className="export-btn-label">BIM model</span>
                        <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                      </button>
                      <button className="export-btn" onClick={() => runExport("dxf", () => downloadDxfFromFit({ plan: versions.plan, testfit: selected.testfit }))} disabled={!!exporting}>
                        <span className="export-btn-label">CAD drawing</span>
                        <span className="export-btn-meta">{exporting === "dxf" ? "Preparing…" : "DXF"}</span>
                      </button>
                    </div>
                    <p className="disclaim" style={{ marginTop: 12 }}>
                      Report compares all three versions; takeoff, BIM &amp; CAD export the selected one.
                    </p>
                  </div>
                </>
              )}
            </>
          )
        )}

        <div className="wizard-nav">
          {prevStep && (
            <button type="button" className="wizard-nav-btn" onClick={() => goStep(prevStep)}>← Back</button>
          )}
          {nextStep && (
            <button type="button" className="wizard-nav-btn is-next" onClick={() => goStep(nextStep)} disabled={!reachable(nextStep)}>
              Next →
            </button>
          )}
        </div>
      </aside>
    </main>
  );
}

function ElCount({ n, k }: { n: number; k: string }) {
  return (
    <div className="el-count">
      <span className="el-n">{num(n)}</span>
      <span className="el-k">{k}</span>
    </div>
  );
}

// Price + delta-vs-current for a swap alternative ("$1,240 · +$180"); "—" when unpriced.
// A $0 list price means "no standalone price" (CET sub-component), never free — show it as unpriced.
function priceMeta(price?: number | null, current?: number | null): string {
  if (!price || price <= 0) return "—";
  const base = money(price); // Steelcase catalog is USD
  if (!current || current <= 0 || current === price) return base;
  const d = price - current;
  return `${base} · ${d > 0 ? "+" : "−"}${money(Math.abs(d))}`;
}

// "private_office" → "Private Office"
const settingLabel = (t: string) =>
  t.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

// Swap chooser — keyboard-accessible (focusable buttons, Enter applies, Esc/Done dismisses),
// tokens only, mirroring the side-panel section + export-btn list styling.
// A small true-shape preview of the selected piece — its real outline, or its footprint as a fallback.
function ShapeThumb({ outline, w, h }: { outline?: [number, number][][]; w: number; h: number }) {
  const S = 54;
  const pad = 6;
  let minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
  if (outline?.length) {
    for (const ring of outline)
      for (const [x, y] of ring) {
        minx = Math.min(minx, x); maxx = Math.max(maxx, x);
        miny = Math.min(miny, y); maxy = Math.max(maxy, y);
      }
  } else {
    minx = 0; miny = 0; maxx = w; maxy = h;
  }
  const bw = Math.max(maxx - minx, 0.1);
  const bh = Math.max(maxy - miny, 0.1);
  const k = Math.min((S - pad * 2) / bw, (S - pad * 2) / bh);
  const ox = (S - bw * k) / 2 - minx * k;
  const oy = (S - bh * k) / 2 - miny * k;
  const tx = (x: number) => x * k + ox;
  const ty = (y: number) => S - (y * k + oy); // y-flip so the thumbnail reads like the plan
  return (
    <svg className="swap-thumb" width={S} height={S} viewBox={`0 0 ${S} ${S}`} aria-hidden="true">
      {outline?.length ? (
        outline.map((ring, i) => (
          <polyline key={i} points={ring.map(([x, y]) => `${tx(x)},${ty(y)}`).join(" ")} />
        ))
      ) : (
        <rect x={tx(minx)} y={ty(maxy)} width={bw * k} height={bh * k} />
      )}
    </svg>
  );
}

// A mini-plan of a setting's arrangement — its placed furniture drawn in the room's own footprint,
// ink hairlines on a paper field, y-flipped so it reads like PlanCanvas. Powers the Layouts palette.
// Filters to SLOT_CATS so the thumbnail shows exactly what applyRoomSwap will drop in.
function ArrangementThumb({ setting }: { setting: CatalogSetting }) {
  const pieces = setting.furniture.filter((sf) => SLOT_CATS.has(sf.category));
  const W = Math.max(setting.width_ft || Math.max(0.1, ...pieces.map((p) => p.dx + p.w)), 0.1);
  const H = Math.max(setting.height_ft || Math.max(0.1, ...pieces.map((p) => p.dy + p.h)), 0.1);
  const boxW = 120, boxH = 88, pad = 7;
  const k = Math.min((boxW - pad * 2) / W, (boxH - pad * 2) / H);
  const ox0 = (boxW - W * k) / 2;
  const oy0 = (boxH - H * k) / 2;
  return (
    <svg className="arr-thumb" viewBox={`0 0 ${boxW} ${boxH}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true">
      {pieces.map((sf, i) => {
        const ox = ox0 + sf.dx * k;
        const oy = oy0 + (H - sf.dy - sf.h) * k; // y-flip: world +y is up, screen +y is down
        return (
          <g key={i} transform={`translate(${ox} ${oy}) scale(${k}) rotate(${-sf.rotation} ${sf.w / 2} ${sf.h / 2})`}>
            {furnitureSymbol(sf.category, sf.w, sf.h)}
          </g>
        );
      })}
    </svg>
  );
}

// Live metrics under the editable plan — seats, open/enclosed split, usable area, density. Re-scored
// by the backend after every move / delete / swap, so the numbers always match the geometry on screen.
function LayoutMetricsStrip({ m }: { m: LayoutMetrics }) {
  const cells: { label: string; value: string }[] = [
    { label: "seats", value: String(m.seats) },
    { label: "open", value: String(m.open_seats) },
    { label: "enclosed", value: String(m.enclosed_seats) },
    { label: "rooms", value: String(m.rooms) },
    { label: "usable", value: `${num(m.usable_sf)} sf` },
    { label: "density", value: m.seats ? `${num(m.density_sf_per_person)} sf/seat` : "—" },
  ];
  return (
    <div className="layout-metrics" role="group" aria-label="Live layout metrics">
      {cells.map((c) => (
        <div className="layout-metric" key={c.label}>
          <span className="layout-metric-value">{c.value}</span>
          <span className="layout-metric-label">{c.label}</span>
        </div>
      ))}
    </div>
  );
}

// Program tree — rooms grouped by family, actual vs the requested program (qbiq's ref-40 left
// rail). Actual counts the enclosed rooms on the plan; target sums the program's per-room counts.
// Target only when the layout was generated from that program — a read plate has no target, so it
// shows detected counts alone (honest). Off-target surfaces a dot: over = terracotta, under = muted.
function ProgramTree({ rooms, target }: { rooms: ExtractedRoom[]; target: DetailedProgram | null }) {
  const actual: Record<string, number> = {};
  for (const r of rooms) {
    const fam = ROOM_FAMILY[r.type];
    if (fam) actual[fam] = (actual[fam] ?? 0) + 1;
  }
  const want: Record<string, number> = {};
  if (target)
    for (const r of target.rooms) {
      const fam = ROOM_FAMILY[r.type];
      if (fam) want[fam] = (want[fam] ?? 0) + r.count;
    }
  const families = PROGRAM_FAMILIES.filter((f) => actual[f] || want[f]);
  if (!families.length) return null;
  return (
    <div className="program-tree" role="group" aria-label="Program — rooms by family">
      <Eyebrow style={{ display: "block", marginBottom: 10 }}>Program · {target ? "actual / target" : "detected"}</Eyebrow>
      {families.map((f) => {
        const a = actual[f] ?? 0;
        const t = want[f];
        const off = target && t !== undefined ? (a > t ? "over" : a < t ? "under" : null) : null;
        return (
          <div className={`prog-row${off ? ` is-${off}` : ""}`} key={f}>
            <span className="prog-fam">{f}</span>
            <span className="prog-count">
              {a}
              {target ? <span className="prog-target"> / {t ?? 0}</span> : null}
              {off && <span className="prog-dot" aria-label={`${off} target`} />}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Visualization finishes selector — composes the render prompt and triggers a photoreal render of
// the current view. Only shown when a provider key is configured (else there's nothing to call).
function FinishesPanel({
  finishes,
  onChange,
  onVisualize,
  busy,
  hasRender,
  editConfigured,
  onEditSurface,
  scopes,
  scope,
  onScope,
  roomFinishes,
}: {
  finishes: Record<string, string>;
  onChange: (f: Record<string, string>) => void;
  onVisualize: () => void;
  busy: boolean;
  hasRender: boolean;
  editConfigured: boolean;
  onEditSurface: (field: string, value: string, scope: string) => void;
  scopes: string[];
  scope: string;
  onScope: (s: string) => void;
  roomFinishes: Record<string, Record<string, string>>;
}) {
  // Once a base render exists and the edit model is configured, the finish controls become TARGETED
  // edits: picking a value swaps just that surface on the current render (Kontext), rather than
  // re-composing the whole prompt. Before then they seed the full-scene "Visualize" render.
  const refining = hasRender && editConfigured;
  // A theme is a whole-scene concept, so it's active when its bundle matches the scene finishes.
  const activeTheme = FINISH_THEMES.find((t) =>
    FINISH_FIELDS.every((f) => (finishes[f.key] ?? "") === (t.finishes[f.key] ?? "")),
  )?.name;
  // When refining a specific room, the controls reflect that room's recorded finishes.
  const shown = refining && scope ? roomFinishes[scope] ?? {} : finishes;
  return (
    <div className="brief finishes-panel">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Theme</Eyebrow>
      <div className="theme-gallery" role="radiogroup" aria-label="Finish theme">
        {FINISH_THEMES.map((t) => {
          const active = t.name === activeTheme;
          return (
            <button
              key={t.name}
              type="button"
              role="radio"
              aria-checked={active}
              className="theme-card"
              data-active={active}
              onClick={() => onChange({ ...finishes, ...t.finishes })}
            >
              <span className="theme-swatch" aria-hidden="true">
                {t.swatch.map((c, i) => (
                  <span key={i} style={{ background: c }} />
                ))}
              </span>
              <span className="theme-name">{t.name}</span>
            </button>
          );
        })}
      </div>

      <Eyebrow style={{ display: "block", margin: "16px 0 12px" }}>
        {refining ? "Refine · per surface" : "Visualize · finishes"}
      </Eyebrow>
      {refining && scopes.length > 0 && (
        <div className="brief-field">
          <span className="brief-label">Apply to</span>
          <Segmented
            value={scope}
            onChange={onScope}
            options={[{ value: "", label: "Whole scene" }, ...scopes.map((s) => ({ value: s, label: s }))]}
          />
        </div>
      )}
      {FINISH_FIELDS.map((f) => (
        <div className="brief-field" key={f.key}>
          <span className="brief-label">{f.label}</span>
          <Segmented
            value={shown[f.key] ?? ""}
            onChange={(v) => (refining ? onEditSurface(f.key, v, scope) : onChange({ ...finishes, [f.key]: v }))}
            options={f.options}
          />
        </div>
      ))}
      {refining ? (
        <p className="disclaim" style={{ marginTop: 4 }}>
          {busy
            ? "Editing that surface…"
            : scope
              ? `Pick a finish to change just the ${scope} — everything else stays put.`
              : "Pick a finish to change just that surface — the layout stays put."}
        </p>
      ) : (
        <button className="ds-btn ds-btn--primary brief-go" onClick={onVisualize} disabled={busy}>
          {busy ? "Rendering…" : "Visualize"}
        </button>
      )}
    </div>
  );
}

function SwapPanel({
  title,
  busy,
  empty,
  preview,
  onDismiss,
  children,
}: {
  title: string;
  busy: boolean;
  empty: boolean;
  preview?: ReactNode;
  onDismiss: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className="swap-panel"
      role="group"
      aria-label={title}
      onKeyDown={(e) => {
        if (e.key === "Escape") onDismiss();
      }}
    >
      <div className="swap-head">
        <Eyebrow>{title}</Eyebrow>
        <button type="button" className="link-btn" onClick={onDismiss}>
          Done
        </button>
      </div>
      {preview && <div className="swap-preview">{preview}</div>}
      {busy ? (
        <p className="disclaim">Finding alternatives…</p>
      ) : empty ? (
        <p className="disclaim">No alternatives in the catalog yet.</p>
      ) : (
        <div className="swap-list">{children}</div>
      )}
    </div>
  );
}

function ConceptForm({
  concept,
  onChange,
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  concept: ConceptProgram;
  onChange: (c: ConceptProgram) => void;
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  const sizeValue = `${concept.desk_width_cm}x${concept.desk_depth_cm}`;
  const ratioPct = Math.round(concept.closed_ratio * 100);

  return (
    <div className="brief">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Program · brief</Eyebrow>

      <div className="brief-field">
        <span className="brief-label">Planning style</span>
        <Segmented
          value={concept.planning_style}
          onChange={(v) => onChange({ ...concept, planning_style: v })}
          options={PLANNING_STYLES}
        />
      </div>

      <div className="brief-field">
        <span className="brief-label">Desk type</span>
        <Segmented
          value={concept.desk_type}
          onChange={(v) => onChange({ ...concept, desk_type: v })}
          options={DESK_TYPES}
        />
      </div>

      <div className="brief-field">
        <span className="brief-label">Desk size · cm</span>
        <Segmented
          value={sizeValue}
          onChange={(v) => {
            const s = DESK_SIZES.find((d) => d.value === v);
            if (s) onChange({ ...concept, desk_width_cm: s.w, desk_depth_cm: s.d });
          }}
          options={DESK_SIZES.map((s) => ({ value: s.value, label: s.label }))}
        />
      </div>

      <div className="brief-field">
        <label className="brief-label" htmlFor="closed-ratio">
          Closed offices vs open · <span className="brief-val">{ratioPct}%</span>
        </label>
        <input
          id="closed-ratio"
          className="brief-slider"
          type="range"
          min={0}
          max={CLOSED_RATIOS.length - 1}
          step={1}
          value={CLOSED_RATIOS.indexOf(concept.closed_ratio)}
          onChange={(e) =>
            onChange({ ...concept, closed_ratio: CLOSED_RATIOS[Number(e.target.value)] })
          }
          aria-valuetext={`${ratioPct}% closed offices`}
        />
        <div className="brief-ticks" aria-hidden="true">
          {CLOSED_RATIOS.map((r) => (
            <span key={r}>{Math.round(r * 100)}</span>
          ))}
        </div>
      </div>

      <GenerateButton busy={busy} file={file} onGenerate={onGenerate} hasVersions={hasVersions} />
    </div>
  );
}

function DetailedForm({
  program,
  onChange,
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  program: DetailedProgram;
  onChange: (p: DetailedProgram) => void;
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  const sizeValue = `${program.desk_width_cm}x${program.desk_depth_cm}`;
  // Upsert a room by type (count 0 prunes it); placement defaults to the catalog entry's.
  const setCount = (type: RoomType, fallback: Placement, count: number) => {
    const others = program.rooms.filter((r) => r.type !== type);
    const existing = program.rooms.find((r) => r.type === type);
    onChange({
      ...program,
      rooms:
        count > 0
          ? [...others, { ...existing, type, count, placement: existing?.placement ?? fallback }]
          : others,
    });
  };
  const setPlacement = (type: RoomType, placement: Placement) =>
    onChange({
      ...program,
      rooms: program.rooms.map((r) => (r.type === type ? { ...r, placement } : r)),
    });
  // Set (or clear) a room type's soft preferred spot — a bias the generator weights, never a pin.
  const setPreferred = (type: RoomType, x: number | undefined, y: number | undefined) =>
    onChange({
      ...program,
      rooms: program.rooms.map((r) =>
        r.type === type ? { ...r, preferred_x: x, preferred_y: y } : r,
      ),
    });

  // Live tally of the requested program — the enclosed-room count per family, updating as the
  // steppers change (qbiq's Program Summary, pre-generation). Density/headcount need the plate
  // area, so they surface per-version after generation (VersionList metrics), not here.
  const familyTally = ROOM_CATALOG.map(({ family, rooms }) => ({
    family,
    count: rooms.reduce(
      (n, rc) => n + (program.rooms.find((r) => r.type === rc.type)?.count ?? 0),
      0,
    ),
  })).filter((f) => f.count > 0);
  const totalRooms = familyTally.reduce((n, f) => n + f.count, 0);

  return (
    <div className="brief">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Program · rooms</Eyebrow>

      <div className="program-summary" role="group" aria-label="Requested program">
        <span className="program-summary-total">{totalRooms}</span>
        <span className="program-summary-unit">enclosed room{totalRooms === 1 ? "" : "s"}</span>
        {familyTally.map((f) => (
          <span className="program-summary-fam" key={f.family}>
            {f.family} · {f.count}
          </span>
        ))}
      </div>

      {ROOM_CATALOG.map(({ family, rooms }) => (
        <div className="room-family" key={family}>
          <span className="room-family-label">{family}</span>
          <div className="room-reqs">
            {rooms.map(({ type, label, placement }) => {
              const room = program.rooms.find((r) => r.type === type);
              const count = room?.count ?? 0;
              return (
                <div className="room-req" key={type} data-active={count > 0}>
                  <div className="room-req-head">
                    <span className="brief-label">{label}</span>
                    <div className="room-stepper" role="group" aria-label={`${label} count`}>
                      <button
                        type="button"
                        className="room-step"
                        aria-label={`Fewer ${label}`}
                        disabled={count <= 0}
                        onClick={() => setCount(type, placement, Math.max(0, count - 1))}
                      >
                        −
                      </button>
                      <span className="room-count" aria-live="polite">
                        {num(count)}
                      </span>
                      <button
                        type="button"
                        className="room-step"
                        aria-label={`More ${label}`}
                        onClick={() => setCount(type, placement, count + 1)}
                      >
                        +
                      </button>
                    </div>
                  </div>
                  {count > 0 && (
                    <>
                      <Segmented
                        value={room?.placement ?? placement}
                        onChange={(v) => setPlacement(type, v)}
                        options={PLACEMENTS}
                      />
                      <div className="pref-zone" role="group" aria-label={`${label} preferred zone`}>
                        {PREFERRED_ZONES.map((z) => {
                          const active = room?.preferred_x === z.x && room?.preferred_y === z.y;
                          return (
                            <button
                              key={z.label}
                              type="button"
                              className="pref-cell"
                              data-active={active}
                              aria-pressed={active}
                              aria-label={`Prefer ${z.label}`}
                              onClick={() =>
                                setPreferred(type, active ? undefined : z.x, active ? undefined : z.y)
                              }
                            />
                          );
                        })}
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="brief-field">
        <span className="brief-label">Desk type</span>
        <Segmented
          value={program.desk_type}
          onChange={(v) => onChange({ ...program, desk_type: v })}
          options={DESK_TYPES}
        />
      </div>

      <div className="brief-field">
        <span className="brief-label">Desk size · cm</span>
        <Segmented
          value={sizeValue}
          onChange={(v) => {
            const s = DESK_SIZES.find((d) => d.value === v);
            if (s) onChange({ ...program, desk_width_cm: s.w, desk_depth_cm: s.d });
          }}
          options={DESK_SIZES.map((s) => ({ value: s.value, label: s.label }))}
        />
      </div>

      <GenerateButton busy={busy} file={file} onGenerate={onGenerate} hasVersions={hasVersions} />
    </div>
  );
}

function GenerateButton({
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  return (
    <button
      className="ds-btn ds-btn--primary brief-go"
      onClick={() => file && onGenerate(file)}
      disabled={!file || busy}
    >
      {busy ? "Generating…" : hasVersions ? "Regenerate versions" : "Generate versions"}
    </button>
  );
}

function VersionList({
  versions,
  selectedId,
  onSelect,
}: {
  versions: { plan: Plan; alternatives: Alternative[] } | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!versions || versions.alternatives.length === 0) return null;
  return (
    <>
      <hr className="ds-rule" />
      <div>
        <Eyebrow style={{ display: "block", marginBottom: 12 }}>
          Versions · {versions.alternatives.length}
        </Eyebrow>
        <div className="versions" role="list">
          {versions.alternatives.map((alt) => (
            <VersionCard
              key={alt.id}
              alt={alt}
              plan={versions.plan}
              selected={alt.id === selectedId}
              onSelect={() => onSelect(alt.id)}
            />
          ))}
        </div>
      </div>
    </>
  );
}

function VersionCard({
  alt,
  plan,
  selected,
  onSelect,
}: {
  alt: Alternative;
  plan: Plan;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="listitem"
      className={`version-card ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="version-thumb">
        <PlanCanvas plan={plan} instances={alt.testfit.instances} compact />
      </span>
      <span className="version-meta">
        <span className="version-seats">
          <span className="version-seats-n">{num(alt.metrics.seats)}</span>
          <span className="version-seats-k">seats</span>
        </span>
        <MetricRow label="Density" value={`${num(alt.metrics.density_sf_per_person)} sf/p`} />
        <MetricRow label="Daylight" value={pct(alt.metrics.daylight_pct)} />
        <MetricRow label="Privacy" value={pct(alt.metrics.privacy_pct)} />
        <MetricRow label="Efficiency" value={pct(alt.metrics.efficiency_pct)} />
      </span>
    </button>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <span className="version-row">
      <span className="version-row-k">{label}</span>
      <span className="version-row-v">{value}</span>
    </span>
  );
}

const pct = (n: Metrics["daylight_pct"]) => `${Math.round(n * 100)}%`;

