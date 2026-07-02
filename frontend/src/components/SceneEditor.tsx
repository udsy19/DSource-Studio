import { useCallback, useEffect, useMemo, useState } from "react";
import {
  applySceneCommand,
  downloadSceneDxf,
  fetchSettings,
  num,
  sceneFromFit,
} from "../api";
import { ArrangementThumb, SLOT_CATS } from "../Studio";
import { closeRing } from "../fitToLayout";
import { Callout, Eyebrow, Segmented } from "../design/ui";
import type {
  Alternative,
  CatalogSetting,
  FurnitureCategory,
  Plan,
  Scene,
  SceneCommand,
  SceneMetrics,
  SceneState,
  SceneZone,
} from "../types";
import { furnitureSymbol } from "./furnitureSymbols";
import {
  doorSwingPath,
  FAMILY_FILL,
  FURN,
  PlanStage,
  pocheBands,
  useView,
  WALL,
  type PlanApi,
  type RoomFamily,
} from "./PlanCanvas";

// The scene's own room-type vocabulary → the quiet program-family tint (reusing PlanCanvas's
// --room-* palette). `open` is the workstation field's quiet neutral.
const ZONE_FAMILY: Record<string, RoomFamily> = {
  private_office: "office",
  meeting_room: "meeting",
  collaboration: "collab",
  open: "open",
};
// The change-room-type options — the four scene room types.
const SCENE_ROOM_TYPES: { value: string; label: string }[] = [
  { value: "private_office", label: "Private office" },
  { value: "meeting_room", label: "Meeting room" },
  { value: "collaboration", label: "Collaboration" },
  { value: "open", label: "Open plan" },
];
const roomTypeLabel = (rt: string) =>
  SCENE_ROOM_TYPES.find((t) => t.value === rt)?.label ?? rt;

type WorldItem = { category: string; x: number; y: number; w: number; h: number; rotation: number };

// Every non-deleted placed item in world feet — the frontend mirror of scene.geometry.resolved_items:
// placement origin + the plate item's local pose (or its per-item override).
function resolveItems(scene: Scene): WorldItem[] {
  const out: WorldItem[] = [];
  for (const pl of scene.placements) {
    const plate = scene.plates[pl.plate_id];
    if (!plate) continue;
    for (const it of pl.items) {
      const base = plate.items[it.plate_item_ref];
      if (it.deleted || !base) continue;
      const t = it.transform_override;
      out.push({
        category: base.category,
        x: pl.transform.x + (t ? t.x : base.dx),
        y: pl.transform.y + (t ? t.y : base.dy),
        w: base.w,
        h: base.h,
        rotation: t ? t.rotation : base.rotation,
      });
    }
  }
  return out;
}

const polygonBounds = (pts: [number, number][]): [number, number, number, number] => {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
};

// Shoelace area (sf) of a zone polygon.
function polygonArea(pts: [number, number][]): number {
  let a = 0;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    a += pts[j][0] * pts[i][1] - pts[i][0] * pts[j][1];
  }
  return Math.abs(a) / 2;
}

const zoneCentroid = (pts: [number, number][]): [number, number] => [
  pts.reduce((s, p) => s + p[0], 0) / pts.length,
  pts.reduce((s, p) => s + p[1], 0) / pts.length,
];

// The renderer: the locked gray underlay + tinted editable zones + resolved furniture + generated
// walls & door swings. Reuses PlanCanvas's pan/zoom shell (PlanStage), poché bands, family tints and
// door-swing path so it reads identically to the test-fit plan.
function SceneCanvas({
  scene,
  selectedZoneId,
  onSelectZone,
}: {
  scene: Scene;
  selectedZoneId: string | null;
  onSelectZone: (id: string) => void;
}) {
  const [minX, minY, maxX, maxY] = polygonBounds(scene.underlay.boundary as [number, number][]);
  const view = useView(minX, minY, maxX, maxY);
  const items = useMemo(() => resolveItems(scene), [scene]);
  const partitionById = useMemo(
    () => new Map(scene.partitions.map((p) => [p.id, p] as const)),
    [scene.partitions],
  );

  // A door swing at a world hinge + world-CCW angle — the leaf line + the quarter-circle arc, drawn
  // in the door's local frame (same convention as PlanCanvas's LayoutPlan doors).
  const doorSwing = (key: string, hx: number, hy: number, angle: number, width: number, flip: boolean, locked: boolean) => (
    <g
      key={key}
      transform={`translate(${view.fx(hx)} ${view.fy(hy)}) rotate(${-angle})`}
      stroke={locked ? "var(--furn-line-faint)" : "var(--wall-door)"}
      fill="none"
      vectorEffect="non-scaling-stroke"
    >
      <line x1={0} y1={0} x2={width} y2={0} vectorEffect="non-scaling-stroke" />
      <path d={doorSwingPath(width, flip)} strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />
    </g>
  );

  return (
    <PlanStage
      view={view}
      span={maxX - minX}
      title="STUDIO SCENE"
      kind="EDITABLE DESIGN"
      draw={(api: PlanApi) => (
        <>
          {/* editable zones — tinted by room family; a click selects, the terracotta ring marks it */}
          {scene.zones.map((z) => {
            const fam = ZONE_FAMILY[z.room_type] ?? "open";
            const name = roomTypeLabel(z.room_type);
            const area = polygonArea(z.polygon);
            const pts = z.polygon
              .map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`)
              .join(" ");
            const [cx, cy] = zoneCentroid(z.polygon);
            return (
              <g
                key={`zone-${z.id}`}
                className={`layout-room${selectedZoneId === z.id ? " is-selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={selectedZoneId === z.id}
                aria-label={`Select ${name}, ${Math.round(area)} square feet`}
                {...api.bindRoom(name, area)}
                onClick={() => { if (!api.didDrag()) onSelectZone(z.id); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectZone(z.id); }
                }}
              >
                <polygon
                  className="room-shape"
                  points={pts}
                  fill={`var(${FAMILY_FILL[fam]})`}
                  stroke="var(--room-line)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
                <text className="room-label" x={view.fx(cx)} y={view.fy(cy)} textAnchor="middle">
                  {name}
                </text>
              </g>
            );
          })}

          {/* locked base building — cores, columns, base doors, boundary. Muted, never interactive. */}
          <g className="scene-underlay" aria-hidden="true">
            {scene.underlay.cores.map((c, i) => (
              <g key={`core-${i}`}>
                <polygon
                  points={(c as [number, number][]).map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ")}
                  fill="var(--poche-core)"
                  fillOpacity={0.12}
                />
                {pocheBands(closeRing(c as [number, number][]), WALL.core.thickness, view.fx, view.fy).map((band, j) => (
                  <polygon key={j} className="poche-band" points={band} fill="var(--poche-core)" vectorEffect="non-scaling-stroke" />
                ))}
              </g>
            ))}
            {scene.underlay.columns.map(([x, y], i) => (
              <circle key={`col-${i}`} cx={view.fx(x)} cy={view.fy(y)} r={0.9} fill="var(--ink)" opacity={0.55} />
            ))}
            {scene.underlay.base_doors.map((d, i) =>
              doorSwing(`bd-${i}`, d.x, d.y, d.rotation, d.width, false, true),
            )}
          </g>

          {/* resolved furniture — each placed item as its plan symbol at its world pose */}
          {items.map((it, i) => {
            const cat = it.category as FurnitureCategory;
            const ox = view.fx(it.x);
            const oy = view.fy(it.y + it.h);
            const cx = view.fx(it.x + it.w / 2);
            const cy = view.fy(it.y + it.h / 2);
            return (
              <g
                key={`item-${i}`}
                transform={`translate(${ox} ${oy}) rotate(${-it.rotation} ${cx - ox} ${cy - oy})`}
                fill={`var(${FURN[cat] ?? "--furn-other"})`}
                fillOpacity={0.14}
              >
                {furnitureSymbol(cat, it.w, it.h)}
              </g>
            );
          })}

          {/* generated partitions — the editable interior walls, drywall poché */}
          {scene.partitions.map((p) => (
            <g key={`part-${p.id}`}>
              {pocheBands([p.segment[0], p.segment[1]], WALL.drywall.thickness, view.fx, view.fy).map((band, j) => (
                <polygon key={j} className="poche-band" points={band} fill="var(--poche-drywall)" vectorEffect="non-scaling-stroke" />
              ))}
            </g>
          ))}

          {/* generated door swings — hosted on a generated partition, positioned by offset along it */}
          {scene.doors.map((d) => {
            const host = partitionById.get(d.host_partition_id);
            if (!host) return null;
            const [[x1, y1], [x2, y2]] = host.segment;
            const len = Math.hypot(x2 - x1, y2 - y1) || 1;
            const ux = (x2 - x1) / len;
            const uy = (y2 - y1) / len;
            const angle = (Math.atan2(uy, ux) * 180) / Math.PI;
            return doorSwing(`door-${d.id}`, x1 + ux * d.offset, y1 + uy * d.offset, angle, d.width, d.swing === "right", false);
          })}

          {/* building edge — one closed perimeter poché wall, drawn last on top */}
          <g className="scene-underlay" aria-hidden="true">
            {pocheBands(closeRing(scene.underlay.boundary as [number, number][]), WALL.perimeter.thickness, view.fx, view.fy).map((band, j) => (
              <polygon key={`b-${j}`} className="poche-band" points={band} fill="var(--poche-perimeter)" vectorEffect="non-scaling-stroke" />
            ))}
          </g>
        </>
      )}
    />
  );
}

// The program scoreboard — seats/density + per-room-type actual/target (reusing the program-tree
// styling: under-target reads muted, over reads terracotta). Every number comes from the scene.
function SceneScoreboard({ metrics }: { metrics: SceneMetrics }) {
  const cells: { label: string; value: string }[] = [
    { label: "seats", value: String(metrics.seats) },
    { label: "open", value: String(metrics.open_seats) },
    { label: "enclosed", value: String(metrics.enclosed_seats) },
    { label: "density", value: metrics.seats ? `${num(metrics.density_sf_per_person)} sf/seat` : "—" },
  ];
  return (
    <div>
      <div className="layout-metrics" role="group" aria-label="Scene metrics">
        {cells.map((c) => (
          <div className="layout-metric" key={c.label}>
            <span className="layout-metric-value">{c.value}</span>
            <span className="layout-metric-label">{c.label}</span>
          </div>
        ))}
      </div>
      {metrics.program.lines.length > 0 && (
        <div className="program-tree" role="group" aria-label="Program — actual vs target">
          <Eyebrow style={{ display: "block", margin: "16px 0 10px" }}>Program · actual / target</Eyebrow>
          {metrics.program.lines.map((ln) => {
            const off = ln.actual > ln.target ? "over" : ln.actual < ln.target ? "under" : null;
            return (
              <div className={`prog-row${off ? ` is-${off}` : ""}`} key={ln.room_type}>
                <span className="prog-fam">{ln.label ?? roomTypeLabel(ln.room_type)}</span>
                <span className="prog-count">
                  {ln.actual}
                  <span className="prog-target"> / {ln.target}</span>
                  {off && <span className="prog-dot" aria-label={`${off} target`} />}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// The selected-zone panel — change room type, area + capacity vs the program target, and the Layouts
// palette (settings that fit the zone footprint; picking one swaps the zone's plate).
function ZonePanel({
  zone,
  scene,
  metrics,
  settings,
  busy,
  onChangeType,
  onSwapPlate,
}: {
  zone: SceneZone;
  scene: Scene;
  metrics: SceneMetrics;
  settings: CatalogSetting[] | null;
  busy: boolean;
  onChangeType: (type: string) => void;
  onSwapPlate: (settingId: string) => void;
}) {
  const placement = scene.placements.find((p) => p.zone_id === zone.id);
  const plate = placement ? scene.plates[placement.plate_id] : undefined;
  const area = polygonArea(zone.polygon);
  const [w, h] = (() => {
    const [minx, miny, maxx, maxy] = polygonBounds(zone.polygon);
    return [maxx - minx, maxy - miny];
  })();
  const line = metrics.program.lines.find((l) => l.room_type === zone.room_type);
  return (
    <div className="swap-panel" role="group" aria-label={`Zone ${roomTypeLabel(zone.room_type)}`}>
      <div className="swap-head">
        <Eyebrow>Zone · {roomTypeLabel(zone.room_type)}</Eyebrow>
      </div>
      <div className="room-props">
        <label className="brief-field">
          <span className="brief-label">Room type</span>
          <Segmented
            label="Room type"
            value={SCENE_ROOM_TYPES.some((t) => t.value === zone.room_type) ? zone.room_type : "open"}
            onChange={onChangeType}
            options={SCENE_ROOM_TYPES}
          />
        </label>
        <div className="prop-recap" style={{ marginTop: 8 }}>
          <div className="prop-row"><span className="prop-k">Area</span><span className="prop-v">{num(area)} sf</span></div>
          <div className="prop-row"><span className="prop-k">Dimensions</span><span className="prop-v">{num(w)}′ × {num(h)}′</span></div>
          <div className="prop-row"><span className="prop-k">Capacity</span><span className="prop-v">{plate ? `${plate.capacity} seats` : "—"}</span></div>
          {line && (
            <div className="prop-row"><span className="prop-k">Program</span><span className="prop-v">{line.actual} / {line.target} rooms</span></div>
          )}
        </div>
        <Eyebrow style={{ display: "block", margin: "16px 0 8px" }}>Layouts · fit this footprint</Eyebrow>
      </div>
      {busy ? (
        <p className="disclaim">Finding layouts…</p>
      ) : settings && settings.length === 0 ? (
        <p className="disclaim">No catalog layouts fit this zone yet.</p>
      ) : (
        <div className="arr-palette" role="group" aria-label="Zone layouts">
          {settings?.map((s) => {
            const pcs = s.furniture.filter((sf) => SLOT_CATS.has(sf.category)).length;
            const isCurrent = placement?.plate_id === s.id;
            return (
              <button
                type="button"
                key={s.id}
                className={`arr-card${isCurrent ? " is-selected" : ""}`}
                aria-pressed={isCurrent}
                aria-label={`${s.title}, ${s.capacity} seats, ${num(s.sqft)} square feet, ${pcs} pieces`}
                onClick={() => onSwapPlate(s.id)}
              >
                <ArrangementThumb setting={s} />
                <span className="arr-label">{s.title}</span>
                <span className="arr-meta">{s.capacity} seats · {num(s.sqft)} sf · {pcs} pcs</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// The scene editor surface — qbiq Studio layout in our design system: the scene canvas on the left,
// the right rail carrying Undo/Redo + the program scoreboard + the selected-zone panel + Layouts.
// Client-side undo/redo: a stack of {scene, metrics} snapshots; every apply pushes the new one.
export default function SceneEditor({
  plan,
  testfit,
  program,
  onExit,
}: {
  plan: Plan;
  testfit: Alternative["testfit"];
  program?: unknown;
  onExit: () => void;
}) {
  const [history, setHistory] = useState<SceneState[]>([]);
  const [index, setIndex] = useState(-1);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [settings, setSettings] = useState<CatalogSetting[] | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const current = index >= 0 ? history[index] : null;
  const scene = current?.scene ?? null;
  const metrics = current?.metrics ?? null;
  const canUndo = index > 0;
  const canRedo = index >= 0 && index < history.length - 1;

  // Build the editable scene once, from the generated version.
  useEffect(() => {
    let live = true;
    setBusy(true);
    setErr(null);
    sceneFromFit(plan, testfit, program)
      .then((s) => {
        if (!live) return;
        setHistory([s]);
        setIndex(0);
      })
      .catch((e) => live && setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => live && setBusy(false));
    return () => {
      live = false;
    };
  }, [plan, testfit, program]);

  const undo = useCallback(() => setIndex((i) => (i > 0 ? i - 1 : i)), []);
  const redo = useCallback(() => setIndex((i) => (i < history.length - 1 ? i + 1 : i)), [history.length]);

  // Cmd/Ctrl+Z undo · Shift+Cmd/Ctrl+Z redo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const selectedZone = useMemo(
    () => scene?.zones.find((z) => z.id === selectedZoneId) ?? null,
    [scene, selectedZoneId],
  );

  // Layouts that fit the selected zone's footprint.
  useEffect(() => {
    if (!selectedZone) {
      setSettings(null);
      return;
    }
    const [minx, miny, maxx, maxy] = polygonBounds(selectedZone.polygon);
    let live = true;
    setSettingsBusy(true);
    fetchSettings(selectedZone.room_type, maxx - minx, maxy - miny)
      .then((s) => live && setSettings(s))
      .catch(() => live && setSettings([]))
      .finally(() => live && setSettingsBusy(false));
    return () => {
      live = false;
    };
  }, [selectedZone]);

  // Apply one command server-side; on success push the new snapshot (truncating any redo tail), on
  // rejection surface the reason and keep the current snapshot.
  const apply = useCallback(
    async (command: SceneCommand) => {
      if (!scene) return;
      setBusy(true);
      setErr(null);
      try {
        const next = await applySceneCommand(scene, command);
        setHistory((h) => [...h.slice(0, index + 1), next]);
        setIndex((i) => i + 1);
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [scene, index],
  );

  const changeType = (type: string) => {
    if (selectedZoneId) apply({ type: "change_room_type", zone_id: selectedZoneId, new_type: type });
  };
  const swapPlate = (settingId: string) => {
    const placement = scene?.placements.find((p) => p.zone_id === selectedZoneId);
    if (placement) apply({ type: "swap_plate", placement_id: placement.id, plate_id: settingId });
  };

  const exportDxf = async () => {
    if (!scene) return;
    setBusy(true);
    setErr(null);
    try {
      await downloadSceneDxf(scene);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="studio">
      <section className="stage">
        {scene ? (
          <SceneCanvas scene={scene} selectedZoneId={selectedZoneId} onSelectZone={setSelectedZoneId} />
        ) : (
          <div className="empty">
            <div className="glyph">◳</div>
            <p>{busy ? "Building the editable scene…" : "No scene."}</p>
          </div>
        )}
      </section>

      <aside className="panel">
        <div className="scene-toolbar">
          <button type="button" className="link-btn" onClick={onExit}>← Done</button>
          <div className="scene-toolbar-actions">
            <button type="button" className="link-btn" onClick={undo} disabled={!canUndo} aria-label="Undo">↶ Undo</button>
            <button type="button" className="link-btn" onClick={redo} disabled={!canRedo} aria-label="Redo">↷ Redo</button>
          </div>
        </div>

        {err && <div className="err" role="alert">{err}</div>}

        {metrics && <SceneScoreboard metrics={metrics} />}

        {scene && metrics && selectedZone ? (
          <>
            <hr className="ds-rule" />
            <ZonePanel
              zone={selectedZone}
              scene={scene}
              metrics={metrics}
              settings={settings}
              busy={settingsBusy}
              onChangeType={changeType}
              onSwapPlate={swapPlate}
            />
          </>
        ) : (
          scene && <Callout quiet>Select a zone on the plan to change its room type or swap its layout.</Callout>
        )}

        <hr className="ds-rule" />
        <div className="exports">
          <Eyebrow style={{ display: "block", marginBottom: 12 }}>Export</Eyebrow>
          <button type="button" className="export-btn" onClick={exportDxf} disabled={!scene || busy}>
            <span className="export-btn-label">CAD drawing</span>
            <span className="export-btn-meta">{busy ? "Preparing…" : "DXF"}</span>
          </button>
        </div>
      </aside>
    </main>
  );
}
