import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  downloadDxfFromFit,
  downloadIfc,
  downloadIfcFromFit,
  downloadLayoutTakeoff,
  downloadReport,
  downloadTakeoffFromFit,
  downloadTakeoffFromLayout,
  generateAlternatives,
  fetchGeometry,
  fetchLayoutBom,
  fetchProducts,
  fetchSettings,
  generateDetailed,
  generateFromConcept,
  ingestCad,
  iterateDetailed,
  num,
  type Bom,
  type SymbolGeometry,
} from "./api";
import Dropzone from "./components/Dropzone";
import PlanCanvas, { furnitureKey, instanceKey } from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented } from "./design/ui";
import { layoutFromFit } from "./fitToLayout";
import type {
  Alternative,
  CatalogSetting,
  ConceptProgram,
  DetailedProgram,
  ExtractedFurniture,
  ExtractedLayout,
  ExtractedRoom,
  Instance,
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
const PLACEMENTS: { value: Placement; label: string }[] = [
  { value: "window", label: "Window" },
  { value: "core", label: "Core" },
  { value: "flexible", label: "Flexible" },
];

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

export default function Studio() {
  const [studioMode, setStudioMode] = useState<"read" | "generate">("read");

  // Read-layout state (the existing flow).
  const [layout, setLayout] = useState<ExtractedLayout | null>(null);
  const [file, setFile] = useState<File | null>(null);
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
  const [swapProducts, setSwapProducts] = useState<Product[] | null>(null);
  const [swapSettings, setSwapSettings] = useState<CatalogSetting[] | null>(null);
  const [swapBusy, setSwapBusy] = useState(false);

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

  const selectFurniture = (f: ExtractedFurniture) => {
    setSwapRoom(null);
    setSwapFurniture(f);
  };
  const selectRoom = (r: ExtractedRoom) => {
    setSwapFurniture(null);
    setSwapRoom(r);
  };
  const dismissSwap = () => {
    setSwapFurniture(null);
    setSwapRoom(null);
  };

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

    // Fetch each DISTINCT SKU's geometry once (5 identical chairs = 1 request); failures fall back.
    const skus = [...new Set(s.furniture.map((sf) => sf.model).filter(Boolean))];
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

    const placed: ExtractedFurniture[] = s.furniture.map((sf) => {
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
    dismissSwap();
  }

  async function readLayout(f: File) {
    setBusy(true);
    setErr(null);
    setLayout(null);
    setAdoptedFit(null);
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
    try {
      // Generate scored test-fit versions from the plate + the program (Concept brief or the
      // explicit Detailed counts), then compare them side by side and open one in 2D / 3D.
      const res =
        genMode === "detailed"
          ? await generateDetailed(f, detailed)
          : await generateFromConcept(f, concept);
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
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
    setStudioMode("read");
    setView("plan");
  }

  const togglePin = (it: Instance) => {
    const key = instanceKey(it);
    setPinned((prev) =>
      prev.some((p) => instanceKey(p) === key) ? prev.filter((p) => instanceKey(p) !== key) : [...prev, it],
    );
  };
  const pinnedKeys = useMemo(() => new Set(pinned.map(instanceKey)), [pinned]);
  const canPin = studioMode === "generate" && genMode === "detailed";

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

  async function exportReport() {
    if (!file) return;
    const alts = await generateAlternatives(file);
    await downloadReport({
      project: { client: "", building: file.name.replace(/\.(dxf|dwg)$/i, ""), style: "Modern", floor: "" },
      plan: alts.plan,
      alternatives: alts.alternatives,
    });
  }

  const building = file?.name.replace(/\.(dxf|dwg)$/i, "") ?? "Plan";
  const inv = layout?.inventory ?? {};
  const rooms = (layout?.rooms ?? []).filter((r) => r.label);
  const selected = versions?.alternatives.find((a) => a.id === selectedId) ?? null;

  return (
    <main className="studio">
      <section className="stage">
        {studioMode === "read" ? (
          layout ? (
            <>
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
              {view === "space" ? (
                <SpaceView layout={layout} />
              ) : (
                <PlanCanvas
                  layout={layout}
                  selectedFurnitureKey={swapFurniture ? furnitureKey(swapFurniture) : null}
                  onSelectFurniture={selectFurniture}
                  selectedRoomId={swapRoom?.id ?? null}
                  onSelectRoom={selectRoom}
                />
              )}
            </>
          ) : (
            <div className="empty">
              <div className="glyph">⌟</div>
              <p>
                Drop a floor plate. DSource Studio reads the real layout — walls by type, rooms, and a
                furniture inventory — straight from your CAD, in 2D and 3D.
              </p>
            </div>
          )
        ) : versions && selected ? (
          <>
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
        ) : (
          <div className="empty">
            <div className="glyph">◳</div>
            <p>
              Pick a program and generate. DSource Studio lays out multiple test-fit versions on your
              plate, scores each, and lets you compare them — then open one in 2D and 3D.
            </p>
          </div>
        )}
      </section>

      <aside className="panel">
        <div className="mode-toggle">
          <Segmented
            value={studioMode}
            onChange={(m) => {
              setStudioMode(m);
              setErr(null);
              dismissSwap();
            }}
            options={[
              { value: "read", label: "Read layout" },
              { value: "generate", label: "Generate" },
            ]}
          />
        </div>

        {err && <div className="err">{err}</div>}

        {studioMode === "read" ? (
          <>
            <Dropzone busy={busy} onFile={readLayout} />

            {layout && (
              <>
                {swapFurniture && (
                  <SwapPanel
                    title={`Swap · ${swapFurniture.category}`}
                    busy={swapBusy}
                    empty={!!swapProducts && swapProducts.length === 0}
                    preview={
                      <>
                        <ShapeThumb
                          outline={swapFurniture.outline}
                          w={swapFurniture.w}
                          h={swapFurniture.h}
                        />
                        <span className="swap-current">
                          {swapFurniture.model
                            ? `${swapFurniture.brand} ${swapFurniture.model}`
                            : "Selected piece"}
                        </span>
                      </>
                    }
                    onDismiss={dismissSwap}
                  >
                    {swapProducts?.map((p, i) => (
                      <button
                        type="button"
                        className="export-btn"
                        key={`${p.brand}-${p.model}-${i}`}
                        onClick={() => applyPieceSwap(p)}
                      >
                        <span className="export-btn-label">
                          {p.brand} {p.model}
                        </span>
                        <span className="export-btn-meta">
                          {priceMeta(p.list_price, swapFurniture.list_price)}
                        </span>
                      </button>
                    ))}
                  </SwapPanel>
                )}

                {swapRoom && (
                  <SwapPanel
                    title={`Swap room · ${swapRoom.label || "Room"}`}
                    busy={swapBusy}
                    empty={!!swapSettings && swapSettings.length === 0}
                    onDismiss={dismissSwap}
                  >
                    {swapSettings?.map((s) => (
                      <button
                        type="button"
                        className="export-btn"
                        key={s.id}
                        onClick={() => applyRoomSwap(s)}
                      >
                        <span className="export-btn-label">{settingLabel(s.setting_type)}</span>
                        <span className="export-btn-meta">
                          {num(s.sqft)} sf · {s.furniture.length} pcs
                        </span>
                      </button>
                    ))}
                  </SwapPanel>
                )}

                <div>
                  <Eyebrow style={{ display: "block", marginBottom: 14 }}>
                    Elements · bill of components
                  </Eyebrow>
                  <div className="el-grid">
                    {INVENTORY_ROWS.filter((r) => inv[r.key]).map((r) => (
                      <ElCount key={r.key} n={inv[r.key]} k={r.label} />
                    ))}
                  </div>
                  <p className="disclaim" style={{ marginTop: 12 }}>
                    Read straight from the CAD — counted from named blocks, with brand &amp; model where
                    the drawing carries it.
                  </p>
                </div>

                {rooms.length > 0 && (
                  <>
                    <hr className="ds-rule" />
                    <div>
                      <Eyebrow style={{ display: "block", marginBottom: 12 }}>
                        Rooms · {rooms.length}
                      </Eyebrow>
                      <div className="rooms-list">
                        {rooms.map((r) => (
                          <div className="room-row" key={r.id}>
                            <span className="rm-label">{r.label}</span>
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
                      <Eyebrow style={{ display: "block", marginBottom: 12 }}>
                        Bill of materials · priced
                      </Eyebrow>
                      <div className="bom-list">
                        {bom.lines.map((l, i) => (
                          <div className="bom-line" key={`${l.model}-${i}`}>
                            <span className="bom-name">
                              {l.qty}× {l.brand} {l.model}
                            </span>
                            <span className="bom-amt">${num(Math.round(l.line_total))}</span>
                          </div>
                        ))}
                        <div className="bom-line bom-total">
                          <span className="bom-name">Total · {bom.priced_items} priced</span>
                          <span className="bom-amt">${num(Math.round(bom.total))}</span>
                        </div>
                      </div>
                      <p className="disclaim" style={{ marginTop: 10 }}>
                        Manufacturer list prices read straight from the drawing’s spec attributes
                        {bom.unpriced_items > 0
                          ? ` · ${bom.unpriced_items} item(s) carry no price`
                          : ""}
                        .
                      </p>
                    </div>
                  </>
                )}

                {layout.needs_confirmation && (
                  <Callout quiet>
                    Room boundaries are best-effort where the drawing's walls don't fully close — labels
                    and counts are exact; confirm boundaries before fabrication.
                  </Callout>
                )}

                <hr className="ds-rule" />
                {layout.source === "generated" ? (
                  <div className="exports">
                    <Eyebrow style={{ display: "block", marginBottom: 14 }}>Export · deliverables</Eyebrow>
                    <div className="export-actions">
                      <button
                        className="export-btn export-btn--primary"
                        onClick={() => runExport("takeoff", () => downloadTakeoffFromLayout(layout))}
                        disabled={!!exporting}
                      >
                        <span className="export-btn-label">Quantity takeoff</span>
                        <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · 9 sheets"}</span>
                      </button>
                      {adoptedFit && (
                        <>
                          <button
                            className="export-btn"
                            onClick={() =>
                              runExport("report", () =>
                                downloadReport({
                                  project: { client: "", building, style: "Modern", floor: "" },
                                  plan: adoptedFit.plan,
                                  alternatives: [adoptedFit.alternative],
                                }),
                              )
                            }
                            disabled={!!exporting}
                          >
                            <span className="export-btn-label">Space-planning report</span>
                            <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF"}</span>
                          </button>
                          <button
                            className="export-btn"
                            onClick={() =>
                              runExport("ifc", () =>
                                downloadIfcFromFit({ plan: adoptedFit.plan, testfit: adoptedFit.alternative.testfit }),
                              )
                            }
                            disabled={!!exporting}
                          >
                            <span className="export-btn-label">BIM model</span>
                            <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                          </button>
                          <button
                            className="export-btn"
                            onClick={() =>
                              runExport("dxf", () =>
                                downloadDxfFromFit({ plan: adoptedFit.plan, testfit: adoptedFit.alternative.testfit }),
                              )
                            }
                            disabled={!!exporting}
                          >
                            <span className="export-btn-label">CAD drawing</span>
                            <span className="export-btn-meta">{exporting === "dxf" ? "Preparing…" : "DXF"}</span>
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="exports">
                    <Eyebrow style={{ display: "block", marginBottom: 14 }}>Export · deliverables</Eyebrow>
                    <div className="export-actions">
                      <button
                        className="export-btn export-btn--primary"
                        onClick={() => runExport("report", exportReport)}
                        disabled={!!exporting}
                      >
                        <span className="export-btn-label">Space-planning report</span>
                        <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF · 3 options"}</span>
                      </button>
                      <button
                        className="export-btn"
                        onClick={() => runExport("takeoff", () => downloadLayoutTakeoff(file!))}
                        disabled={!!exporting}
                      >
                        <span className="export-btn-label">Quantity takeoff</span>
                        <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · 9 sheets"}</span>
                      </button>
                      <button
                        className="export-btn"
                        onClick={() => runExport("ifc", () => downloadIfc(file!))}
                        disabled={!!exporting}
                      >
                        <span className="export-btn-label">BIM model</span>
                        <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <>
            <div className="brief-field">
              <Segmented
                value={genMode}
                onChange={(m) => {
                  setGenMode(m);
                  setErr(null);
                }}
                options={[
                  { value: "concept", label: "Concept" },
                  { value: "detailed", label: "Detailed" },
                ]}
              />
            </div>

            <Dropzone busy={busy} onFile={generate} />
            {file && <p className="disclaim">{file.name}</p>}

            {genMode === "concept" ? (
              <ConceptForm
                concept={concept}
                onChange={setConcept}
                busy={busy}
                file={file}
                onGenerate={generate}
                hasVersions={!!versions}
              />
            ) : (
              <DetailedForm
                program={detailed}
                onChange={setDetailed}
                busy={busy}
                file={file}
                onGenerate={generate}
                hasVersions={!!versions}
              />
            )}

            <VersionList
              versions={versions}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />

            {canPin && versions && (
              <>
                <hr className="ds-rule" />
                <div className="iterate">
                  <Eyebrow style={{ display: "block", marginBottom: 10 }}>Iterate · pin & regenerate</Eyebrow>
                  <p className="disclaim" style={{ marginBottom: 12 }}>
                    Click rooms on the plan to pin them, adjust the program above, then regenerate —
                    pinned rooms stay put while the rest re-places.
                  </p>
                  <div className="iterate-head">
                    <span className="brief-label">
                      {pinned.length} pinned
                    </span>
                    {pinned.length > 0 && (
                      <button type="button" className="link-btn" onClick={() => setPinned([])}>
                        Clear
                      </button>
                    )}
                  </div>
                  <button
                    className="export-btn export-btn--primary"
                    style={{ marginTop: 10, width: "100%" }}
                    onClick={regenerate}
                    disabled={busy}
                  >
                    <span className="export-btn-label">
                      {busy ? "Regenerating…" : "Regenerate"}
                    </span>
                    <span className="export-btn-meta">
                      {pinned.length > 0 ? `keep ${pinned.length} pinned` : "re-place all"}
                    </span>
                  </button>
                </div>
              </>
            )}

            {versions && selected && (
              <>
                <hr className="ds-rule" />
                <div className="adopt">
                  <Eyebrow style={{ display: "block", marginBottom: 10 }}>Layout · adopt version</Eyebrow>
                  <p className="disclaim" style={{ marginBottom: 12 }}>
                    Move version {selected.id} into Read layout — its rooms, partitions, and desks
                    become a full layout you can inspect in 2D, 3D, and the inventory.
                  </p>
                  <button
                    className="export-btn export-btn--primary"
                    style={{ width: "100%" }}
                    onClick={adoptLayout}
                    disabled={busy}
                  >
                    <span className="export-btn-label">Open in Read layout</span>
                    <span className="export-btn-meta">→ rooms · walls · inventory</span>
                  </button>
                </div>

                <hr className="ds-rule" />
                <div className="exports">
                  <Eyebrow style={{ display: "block", marginBottom: 14 }}>
                    Export · version {selected.id}
                  </Eyebrow>
                  <div className="export-actions">
                    <button
                      className="export-btn export-btn--primary"
                      onClick={() =>
                        runExport("report", () =>
                          downloadReport({
                            project: { client: "", building, style: "Modern", floor: "" },
                            plan: versions.plan,
                            alternatives: versions.alternatives,
                          }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">Space-planning report</span>
                      <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF · 3 options"}</span>
                    </button>
                    <button
                      className="export-btn"
                      onClick={() =>
                        runExport("takeoff", () =>
                          downloadTakeoffFromFit({ plan: versions.plan, testfit: selected.testfit }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">Quantity takeoff</span>
                      <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · BOM"}</span>
                    </button>
                    <button
                      className="export-btn"
                      onClick={() =>
                        runExport("ifc", () =>
                          downloadIfcFromFit({ plan: versions.plan, testfit: selected.testfit }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">BIM model</span>
                      <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                    </button>
                    <button
                      className="export-btn"
                      onClick={() =>
                        runExport("dxf", () =>
                          downloadDxfFromFit({ plan: versions.plan, testfit: selected.testfit }),
                        )
                      }
                      disabled={!!exporting}
                    >
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
        )}
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
  const base = `$${num(price)}`;
  if (!current || current <= 0 || current === price) return base;
  const d = price - current;
  return `${base} · ${d > 0 ? "+" : "−"}$${num(Math.abs(d))}`;
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
          ? [...others, { type, count, placement: existing?.placement ?? fallback }]
          : others,
    });
  };
  const setPlacement = (type: RoomType, placement: Placement) =>
    onChange({
      ...program,
      rooms: program.rooms.map((r) => (r.type === type ? { ...r, placement } : r)),
    });

  return (
    <div className="brief">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Program · rooms</Eyebrow>

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
                    <Segmented
                      value={room?.placement ?? placement}
                      onChange={(v) => setPlacement(type, v)}
                      options={PLACEMENTS}
                    />
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
