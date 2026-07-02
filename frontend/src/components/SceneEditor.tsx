import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applySceneCommand,
  downloadRenderImage,
  downloadSceneDxf,
  downloadSceneTakeoff,
  fetchSettings,
  num,
  sceneFromFit,
  sceneMetrics,
} from "../api";
import { ArrangementThumb, captureSvgJpeg, SLOT_CATS } from "../Studio";
import { saveEditedDesign } from "../workflowProjects";
import { closeRing } from "../fitToLayout";
import { Callout, Eyebrow, Segmented } from "../design/ui";
import type {
  Alternative,
  CatalogSetting,
  FurnitureCategory,
  Plan,
  Scene,
  SceneCommand,
  SceneDoor,
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
  rotationToPointer,
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

// Stable identity for a placed item — the placement it belongs to + its plate-item ref, so a
// selection survives moves/rotates (those change the pose, never the ref).
const itemKey = (placementId: string, itemRef: number) => `${placementId}:${itemRef}`;
type ItemSelection = { placement_id: string; item_ref: number };

// Normalize a rotation delta to (-180, 180] so a grip-drag sends the short way round.
const normalizeDelta = (deg: number) => {
  const x = ((deg % 360) + 360) % 360;
  return x > 180 ? x - 360 : x;
};

// The backend snaps every rotation to 45° (_snap_45), so the live grip preview snaps to the same
// grid — a small drag visibly clicks to the next detent instead of silently rounding home (which
// read as "rotate is broken"). A bare click on the grip (no drag) rotates +90°, a Canva idiom.
const CLICK_ROTATE_DEG = 90;
const snap45 = (deg: number) => (((Math.round(deg / 45) * 45) % 360) + 360) % 360;

type WorldItem = {
  key: string;
  placement_id: string;
  zone_id: string;
  item_ref: number;
  category: string;
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
};

// Keep a dragged item inside its zone's bounding box (a UX hint mirroring the server's
// clamp_local_into_zone — the server stays the authority; this only stops furniture visually
// crossing a wall mid-drag). Returns the delta clamped so the item's footprint stays within bounds.
const clampDeltaToZone = (
  it: WorldItem,
  [zx0, zy0, zx1, zy1]: [number, number, number, number],
  dx: number,
  dy: number,
): { dx: number; dy: number } => {
  const nx = Math.min(Math.max(it.x + dx, zx0), Math.max(zx0, zx1 - it.w));
  const ny = Math.min(Math.max(it.y + dy, zy0), Math.max(zy0, zy1 - it.h));
  return { dx: nx - it.x, dy: ny - it.y };
};

// Every non-deleted placed item in world feet — the frontend mirror of scene.geometry.resolved_items:
// placement origin + the plate item's local pose (or its per-item override). Carries the placement +
// plate-item ref so a canvas click resolves straight to a move/rotate/delete command target.
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
        key: itemKey(pl.id, it.plate_item_ref),
        placement_id: pl.id,
        zone_id: pl.zone_id,
        item_ref: it.plate_item_ref,
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
// door-swing path so it reads identically to the test-fit plan. Zones, placement items and generated
// doors are selectable/editable — the underlay stays locked. The move/rotate/delete idiom (drag +
// preview transform, north-edge rotate grip, snap steps) mirrors PlanCanvas's LayoutPlan furniture.
function SceneCanvas({
  scene,
  selectedZoneId,
  onSelectZone,
  mergeMode,
  mergeSelection,
  onToggleMergeZone,
  selectedItem,
  onSelectItem,
  onMoveItem,
  onRotateItem,
  onDeleteItem,
  selectedDoorId,
  onSelectDoor,
  onSlideDoor,
  onFlipDoor,
}: {
  scene: Scene;
  selectedZoneId: string | null;
  onSelectZone: (id: string) => void;
  mergeMode: boolean;
  mergeSelection: string[];
  onToggleMergeZone: (id: string) => void;
  selectedItem: ItemSelection | null;
  onSelectItem: (sel: ItemSelection) => void;
  onMoveItem: (sel: ItemSelection, dx: number, dy: number) => void;
  onRotateItem: (sel: ItemSelection, delta: number) => void;
  onDeleteItem: (sel: ItemSelection) => void;
  selectedDoorId: string | null;
  onSelectDoor: (id: string) => void;
  onSlideDoor: (id: string, offset: number) => void;
  onFlipDoor: (id: string) => void;
}) {
  const [minX, minY, maxX, maxY] = polygonBounds(scene.underlay.boundary as [number, number][]);
  const view = useView(minX, minY, maxX, maxY);
  const items = useMemo(() => resolveItems(scene), [scene]);
  const partitionById = useMemo(
    () => new Map(scene.partitions.map((p) => [p.id, p] as const)),
    [scene.partitions],
  );
  const zoneBoundsById = useMemo(
    () => new Map(scene.zones.map((z) => [z.id, polygonBounds(z.polygon)] as const)),
    [scene.zones],
  );
  const selectedItemKey = selectedItem ? itemKey(selectedItem.placement_id, selectedItem.item_ref) : null;

  // Active drag of a placement item: its key + the live world-feet offset (for the preview
  // transform). A move commits on pointer-up; a drag past MOVE_MIN_FT suppresses the select click.
  const [drag, setDrag] = useState<{ key: string; dx: number; dy: number } | null>(null);
  const dragStart = useRef<{ x: number; y: number; key: string; moved: boolean } | null>(null);
  const MOVE_MIN_FT = 0.25;
  // Live rotation of the selected item via its grip: the previewed degrees, committed on pointer-up.
  const [rotating, setRotating] = useState<{ key: string; deg: number } | null>(null);
  const rotateStart = useRef<{ key: string; moved: boolean } | null>(null);

  // Active slide of a door along its host wall: the door id + live offset (feet from segment start),
  // committed on pointer-up. Mirrors the item-drag idiom; the offset is clamped to the jamb bound.
  const [doorDrag, setDoorDrag] = useState<{ id: string; offset: number } | null>(null);
  const doorDragStart = useRef<{ id: string; moved: boolean } | null>(null);

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
          {/* editable zones — tinted by room family; a click selects (or, in merge mode, picks the
              zone), the terracotta ring marks the selection */}
          {scene.zones.map((z) => {
            const fam = ZONE_FAMILY[z.room_type] ?? "open";
            const name = roomTypeLabel(z.room_type);
            const area = polygonArea(z.polygon);
            const picked = mergeMode ? mergeSelection.includes(z.id) : selectedZoneId === z.id;
            const pts = z.polygon
              .map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`)
              .join(" ");
            const [cx, cy] = zoneCentroid(z.polygon);
            const activate = () => (mergeMode ? onToggleMergeZone(z.id) : onSelectZone(z.id));
            return (
              <g
                key={`zone-${z.id}`}
                className={`layout-room${picked ? " is-selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={picked}
                aria-label={
                  mergeMode
                    ? `${picked ? "Remove" : "Add"} ${name} ${picked ? "from" : "to"} merge selection, ${Math.round(area)} square feet`
                    : `Select ${name}, ${Math.round(area)} square feet`
                }
                {...api.bindRoom(name, area)}
                onClick={() => { if (!api.didDrag()) activate(); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(); }
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

          {/* resolved furniture — each placed item as its plan symbol at its world pose. Selectable;
              the selected item can be dragged (live preview) and rotated by its grip, mirroring the
              LayoutPlan furniture interaction. */}
          {items.map((it) => {
            const cat = it.category as FurnitureCategory;
            const selected = selectedItemKey === it.key;
            const dragging = drag?.key === it.key;
            const rot = rotating?.key === it.key ? rotating.deg : it.rotation;
            const ox = view.fx(it.x);
            const oy = view.fy(it.y + it.h);
            const csx = view.fx(it.x + it.w / 2);
            const csy = view.fy(it.y + it.h / 2);
            const previewT = dragging ? `translate(${drag!.dx} ${-drag!.dy}) ` : "";
            const sel: ItemSelection = { placement_id: it.placement_id, item_ref: it.item_ref };
            return (
              <g
                key={`item-${it.key}`}
                className={`layout-furn is-movable${selected ? " is-selected" : ""}${dragging ? " is-dragging" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                aria-label={`Move or delete ${cat}`}
                transform={`${previewT}rotate(${-rot} ${csx} ${csy}) translate(${ox} ${oy})`}
                fill={`var(${FURN[cat] ?? "--furn-other"})`}
                fillOpacity={0.14}
                onClick={() => {
                  if (api.didDrag() || dragStart.current?.moved) return;
                  onSelectItem(sel);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectItem(sel); }
                  else if (e.key === "[" || e.key === "]") { e.preventDefault(); onRotateItem(sel, e.key === "]" ? 45 : -45); }
                  else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); onDeleteItem(sel); }
                }}
                onPointerDown={(e) => {
                  e.stopPropagation(); // begin an item drag, not a canvas pan
                  (e.currentTarget as Element).setPointerCapture(e.pointerId);
                  dragStart.current = { x: e.clientX, y: e.clientY, key: it.key, moved: false };
                }}
                onPointerMove={(e) => {
                  const s = dragStart.current;
                  if (!s || s.key !== it.key) return;
                  const d = api.worldDelta({ x: s.x, y: s.y }, { x: e.clientX, y: e.clientY });
                  if (Math.abs(d.dx) > MOVE_MIN_FT || Math.abs(d.dy) > MOVE_MIN_FT) s.moved = true;
                  const zb = zoneBoundsById.get(it.zone_id);
                  const c = zb ? clampDeltaToZone(it, zb, d.dx, d.dy) : d;
                  setDrag({ key: it.key, dx: c.dx, dy: c.dy });
                }}
                onPointerUp={() => {
                  const s = dragStart.current;
                  if (s && s.key === it.key && s.moved && drag && drag.key === it.key) {
                    onMoveItem(sel, drag.dx, drag.dy);
                  }
                  setDrag(null); // dragStart kept so the trailing onClick sees `moved` and skips select
                }}
              >
                {furnitureSymbol(cat, it.w, it.h)}
              </g>
            );
          })}

          {/* rotate grip — a handle just outside the selected item's bbox; drag it to spin the item
              about its centre (live preview, snap on Shift), or use ←/→ · [ ] for 45° steps. */}
          {selectedItemKey && (() => {
            const it = items.find((g) => g.key === selectedItemKey);
            if (!it) return null;
            const sel: ItemSelection = { placement_id: it.placement_id, item_ref: it.item_ref };
            const rot = rotating?.key === it.key ? rotating.deg : it.rotation;
            const wcx = it.x + it.w / 2;
            const wcy = it.y + it.h / 2;
            const reach = Math.max(it.w, it.h) / 2 + 2.4;
            const ang = ((90 + rot) * Math.PI) / 180;
            const gx = view.fx(wcx + reach * Math.cos(ang));
            const gy = view.fy(wcy + reach * Math.sin(ang));
            const cx = view.fx(wcx);
            const cy = view.fy(wcy);
            return (
              <g className="rotate-grip">
                <line x1={cx} y1={cy} x2={gx} y2={gy} stroke="var(--accent)" strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />
                <circle
                  cx={gx}
                  cy={gy}
                  r={1.3}
                  fill="var(--accent)"
                  role="slider"
                  tabIndex={0}
                  aria-label={`Rotate ${it.category}`}
                  aria-valuenow={Math.round(rot)}
                  aria-valuemin={0}
                  aria-valuemax={360}
                  onKeyDown={(e) => {
                    if (e.key === "ArrowLeft" || e.key === "[") { e.preventDefault(); onRotateItem(sel, -45); }
                    else if (e.key === "ArrowRight" || e.key === "]") { e.preventDefault(); onRotateItem(sel, 45); }
                  }}
                  onPointerDown={(e) => {
                    e.stopPropagation(); // rotate, not a canvas pan or item move
                    (e.currentTarget as Element).setPointerCapture(e.pointerId);
                    rotateStart.current = { key: it.key, moved: false };
                  }}
                  onPointerMove={(e) => {
                    if (rotateStart.current?.key !== it.key) return;
                    rotateStart.current.moved = true;
                    const p = api.worldPoint({ x: e.clientX, y: e.clientY });
                    setRotating({ key: it.key, deg: snap45(rotationToPointer(wcx, wcy, p.x, p.y)) });
                  }}
                  onPointerUp={() => {
                    const rs = rotateStart.current;
                    if (rs?.key === it.key) {
                      if (!rs.moved) {
                        onRotateItem(sel, CLICK_ROTATE_DEG); // bare click → +90° detent
                      } else if (rotating?.key === it.key) {
                        const delta = normalizeDelta(rotating.deg - it.rotation);
                        if (delta !== 0) onRotateItem(sel, delta);
                      }
                    }
                    rotateStart.current = null;
                    setRotating(null);
                  }}
                />
              </g>
            );
          })()}

          {/* delete affordance — the selected item's floating toolbar, pinned at its top-left corner
              (screen space, so it never rotates away). Del/Backspace does the same. */}
          {selectedItemKey && (() => {
            const it = items.find((g) => g.key === selectedItemKey);
            if (!it) return null;
            const sel: ItemSelection = { placement_id: it.placement_id, item_ref: it.item_ref };
            const bx = view.fx(it.x) - 1.6;
            const by = view.fy(it.y + it.h) - 1.6;
            const r = 1.3;
            return (
              <g
                className="item-delete"
                role="button"
                tabIndex={0}
                aria-label={`Delete ${it.category}`}
                onPointerDown={(e) => e.stopPropagation()} // delete, not a canvas pan (pan capture would eat the click)
                onClick={() => onDeleteItem(sel)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " " || e.key === "Delete" || e.key === "Backspace") {
                    e.preventDefault();
                    onDeleteItem(sel);
                  }
                }}
              >
                <circle cx={bx} cy={by} r={r} fill="var(--paper)" stroke="var(--accent)" vectorEffect="non-scaling-stroke" />
                <line x1={bx - 0.5} y1={by - 0.5} x2={bx + 0.5} y2={by + 0.5} stroke="var(--accent)" vectorEffect="non-scaling-stroke" />
                <line x1={bx - 0.5} y1={by + 0.5} x2={bx + 0.5} y2={by - 0.5} stroke="var(--accent)" vectorEffect="non-scaling-stroke" />
              </g>
            );
          })()}

          {/* generated partitions — the editable interior walls, drywall poché */}
          {scene.partitions.map((p) => (
            <g key={`part-${p.id}`}>
              {pocheBands([p.segment[0], p.segment[1]], WALL.drywall.thickness, view.fx, view.fy).map((band, j) => (
                <polygon key={j} className="poche-band" points={band} fill="var(--poche-drywall)" vectorEffect="non-scaling-stroke" />
              ))}
            </g>
          ))}

          {/* generated door swings — hosted on a generated partition, positioned by offset along it.
              Drag the door along its wall (offset committed on release, clamped to the jamb bound like
              the server), tap its ⟲ grip to flip the swing. Selection happens on press. */}
          {scene.doors.map((d) => {
            const host = partitionById.get(d.host_partition_id);
            if (!host) return null;
            const [[x1, y1], [x2, y2]] = host.segment;
            const len = Math.hypot(x2 - x1, y2 - y1) || 1;
            const ux = (x2 - x1) / len;
            const uy = (y2 - y1) / len;
            const angle = (Math.atan2(uy, ux) * 180) / Math.PI;
            const maxOffset = Math.max(0, len - d.width); // jamb bound — mirrors EditDoor's server clamp
            const off = doorDrag?.id === d.id ? doorDrag.offset : d.offset;
            const hx = x1 + ux * off;
            const hy = y1 + uy * off;
            const selected = selectedDoorId === d.id;
            return (
              <g
                key={`door-${d.id}`}
                className={`layout-door${selected ? " is-selected" : ""}`}
                role="button"
                tabIndex={0}
                aria-pressed={selected}
                aria-label={`Move door, ${(d.width * 12).toFixed(0)} inch leaf`}
                transform={`translate(${view.fx(hx)} ${view.fy(hy)}) rotate(${-angle})`}
                stroke={selected ? "var(--accent)" : "var(--wall-door)"}
                fill="none"
                vectorEffect="non-scaling-stroke"
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectDoor(d.id); }
                  else if (e.key === "f" || e.key === "F") { e.preventDefault(); onFlipDoor(d.id); }
                }}
                onPointerDown={(e) => {
                  e.stopPropagation(); // slide the door, not a canvas pan
                  (e.currentTarget as Element).setPointerCapture(e.pointerId);
                  onSelectDoor(d.id);
                  doorDragStart.current = { id: d.id, moved: false };
                }}
                onPointerMove={(e) => {
                  if (doorDragStart.current?.id !== d.id) return;
                  const p = api.worldPoint({ x: e.clientX, y: e.clientY });
                  const proj = (p.x - x1) * ux + (p.y - y1) * uy;
                  const next = Math.min(Math.max(proj, 0), maxOffset);
                  if (Math.abs(next - d.offset) > MOVE_MIN_FT) doorDragStart.current.moved = true;
                  setDoorDrag({ id: d.id, offset: next });
                }}
                onPointerUp={() => {
                  const ds = doorDragStart.current;
                  if (ds?.id === d.id && ds.moved && doorDrag?.id === d.id) {
                    onSlideDoor(d.id, doorDrag.offset);
                  }
                  doorDragStart.current = null;
                  setDoorDrag(null);
                }}
              >
                {/* wide transparent band so the thin leaf is easy to grab */}
                <line x1={0} y1={0} x2={d.width} y2={0} stroke="transparent" strokeWidth={16} vectorEffect="non-scaling-stroke" />
                <line x1={0} y1={0} x2={d.width} y2={0} vectorEffect="non-scaling-stroke" />
                <path d={doorSwingPath(d.width, d.swing === "right")} strokeOpacity={0.5} vectorEffect="non-scaling-stroke" />
                {selected && (
                  <circle
                    className="door-flip-grip"
                    cx={d.width / 2}
                    cy={-2}
                    r={1.2}
                    fill="var(--accent)"
                    stroke="none"
                    role="button"
                    aria-label="Flip door swing"
                    onPointerDown={(e) => { e.stopPropagation(); /* flip, not a slide */ }}
                    onClick={(e) => { e.stopPropagation(); onFlipDoor(d.id); }}
                  />
                )}
              </g>
            );
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

// The selected-zone panel — room type, open/enclosed, area + capacity vs the program target, and the
// Layouts palette (settings that fit the zone footprint; picking one swaps the zone's plate).
function ZonePanel({
  zone,
  scene,
  metrics,
  settings,
  busy,
  onChangeType,
  onSetEnclosed,
  onSwapPlate,
}: {
  zone: SceneZone;
  scene: Scene;
  metrics: SceneMetrics;
  settings: CatalogSetting[] | null;
  busy: boolean;
  onChangeType: (type: string) => void;
  onSetEnclosed: (enclosed: boolean) => void;
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
        <label className="brief-field" style={{ marginTop: 12 }}>
          <span className="brief-label">Enclosure</span>
          <Segmented
            label="Enclosure"
            value={zone.enclosed ? "enclosed" : "open"}
            onChange={(v) => onSetEnclosed(v === "enclosed")}
            options={[
              { value: "open", label: "Open" },
              { value: "enclosed", label: "Enclosed" },
            ]}
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

// The selected-door panel — properties only. Sliding along the wall and flipping the swing are
// direct on-canvas gestures now (drag the door, tap its flip grip), so the panel just recaps.
function DoorPanel({ door }: { door: SceneDoor }) {
  return (
    <div className="swap-panel" role="group" aria-label="Door">
      <div className="swap-head">
        <Eyebrow>Door</Eyebrow>
      </div>
      <div className="room-props">
        <div className="prop-recap">
          <div className="prop-row"><span className="prop-k">Leaf</span><span className="prop-v">{num(door.width * 12)}″</span></div>
          <div className="prop-row"><span className="prop-k">Offset</span><span className="prop-v">{num(door.offset)}′</span></div>
          <div className="prop-row"><span className="prop-k">Swing</span><span className="prop-v">{door.swing}</span></div>
        </div>
        <p className="disclaim" style={{ marginTop: 12 }}>Drag the door along its wall to reposition it; tap its ⟲ grip to flip the swing.</p>
      </div>
    </div>
  );
}

// The scene editor surface — qbiq Studio layout in our design system: the scene canvas on the left,
// the right rail carrying Undo/Redo + Merge + the program scoreboard + the selection panel + Layouts.
// Client-side undo/redo: a stack of {scene, metrics} snapshots; every apply pushes the new one.
export default function SceneEditor({
  plan,
  testfit,
  program,
  savedScene,
  projectId,
  designId,
  designName,
  forkedFrom,
  onExit,
}: {
  plan?: Plan;
  testfit?: Alternative["testfit"];
  program?: unknown;
  // Reopen an already-saved edited design: seed the editor from this scene instead of from-fit.
  savedScene?: Scene;
  projectId?: string;
  designId?: string;
  designName?: string;
  forkedFrom?: string | null;
  onExit: () => void;
}) {
  const [history, setHistory] = useState<SceneState[]>([]);
  const [index, setIndex] = useState(-1);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [selectedZoneId, setSelectedZoneId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<ItemSelection | null>(null);
  const [selectedDoorId, setSelectedDoorId] = useState<string | null>(null);
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelection, setMergeSelection] = useState<string[]>([]);
  const [settings, setSettings] = useState<CatalogSetting[] | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const current = index >= 0 ? history[index] : null;
  const scene = current?.scene ?? null;
  const metrics = current?.metrics ?? null;
  const canUndo = index > 0;
  const canRedo = index >= 0 && index < history.length - 1;

  // Seed the editor once: reopen a saved design (fresh undo stack from its scene) or build a fresh
  // scene from the generated version. The undo history is session-scoped — a saved design never
  // carries its stack, so reopening always starts clean at the saved state.
  useEffect(() => {
    let live = true;
    setBusy(true);
    setErr(null);
    const load: Promise<SceneState> = savedScene
      ? sceneMetrics(savedScene).then((m) => ({ scene: savedScene, metrics: m }))
      : plan && testfit
        ? sceneFromFit(plan, testfit, program)
        : Promise.reject(new Error("Nothing to edit — open a generated version or a saved design."));
    load
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
  }, [plan, testfit, program, savedScene]);

  const undo = useCallback(() => setIndex((i) => (i > 0 ? i - 1 : i)), []);
  const redo = useCallback(() => setIndex((i) => (i < history.length - 1 ? i + 1 : i)), [history.length]);

  const clearSelection = useCallback(() => {
    setSelectedItem(null);
    setSelectedDoorId(null);
  }, []);

  // Cmd/Ctrl+Z undo · Shift+Cmd/Ctrl+Z redo · Esc clears the current selection.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { clearSelection(); setSelectedZoneId(null); return; }
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, clearSelection]);

  const selectedZone = useMemo(
    () => scene?.zones.find((z) => z.id === selectedZoneId) ?? null,
    [scene, selectedZoneId],
  );
  const selectedDoor = useMemo(
    () => scene?.doors.find((d) => d.id === selectedDoorId) ?? null,
    [scene, selectedDoorId],
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

  // Apply one command server-side; on success push the new snapshot (truncating any redo tail) and
  // return it, on rejection surface the reason, keep the current snapshot, and return null.
  const apply = useCallback(
    async (command: SceneCommand): Promise<SceneState | null> => {
      if (!scene) return null;
      setBusy(true);
      setErr(null);
      try {
        const next = await applySceneCommand(scene, command);
        setHistory((h) => [...h.slice(0, index + 1), next]);
        setIndex((i) => i + 1);
        return next;
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
        return null;
      } finally {
        setBusy(false);
      }
    },
    [scene, index],
  );

  const changeType = (type: string) => {
    if (selectedZoneId) apply({ type: "change_room_type", zone_id: selectedZoneId, new_type: type });
  };
  const setEnclosed = (enclosed: boolean) => {
    if (selectedZoneId) apply({ type: "set_open_enclosed", zone_id: selectedZoneId, enclosed });
  };
  const swapPlate = (settingId: string) => {
    const placement = scene?.placements.find((p) => p.zone_id === selectedZoneId);
    if (placement) apply({ type: "swap_plate", placement_id: placement.id, plate_id: settingId });
  };

  const selectZone = (id: string) => {
    clearSelection();
    setSelectedZoneId(id);
  };
  const selectItem = (sel: ItemSelection) => {
    setSelectedZoneId(null);
    setSelectedDoorId(null);
    setSelectedItem(sel);
  };
  const selectDoor = (id: string) => {
    setSelectedZoneId(null);
    setSelectedItem(null);
    setSelectedDoorId(id);
  };
  const moveItem = (sel: ItemSelection, dx: number, dy: number) =>
    apply({ type: "move_item", ...sel, dx, dy });
  const rotateItem = (sel: ItemSelection, delta: number) =>
    apply({ type: "rotate_item", ...sel, delta });
  const deleteItem = (sel: ItemSelection) => {
    setSelectedItem(null);
    apply({ type: "delete_item", ...sel });
  };
  const flipDoor = (id: string) => apply({ type: "edit_door", door_id: id, flip_swing: true });
  const slideDoor = (id: string, offset: number) => apply({ type: "edit_door", door_id: id, offset });

  const toggleMergeMode = () => {
    clearSelection();
    setSelectedZoneId(null);
    setMergeSelection([]);
    setMergeMode((on) => !on);
  };
  const toggleMergeZone = (id: string) => {
    setMergeSelection((sel) =>
      sel.includes(id)
        ? sel.filter((z) => z !== id)
        : sel.length < 2
          ? [...sel, id]
          : [sel[1], id],
    );
  };
  const applyMerge = async () => {
    if (mergeSelection.length !== 2) return;
    const [a, b] = mergeSelection;
    const next = await apply({ type: "merge_zones", a_id: a, b_id: b });
    if (next) {
      setMergeMode(false);
      setMergeSelection([]);
      setSelectedZoneId(a); // keep the merged zone selected so a plate can seat the bigger footprint
    }
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

  const exportTakeoff = async () => {
    if (!scene) return;
    setBusy(true);
    setErr(null);
    try {
      await downloadSceneTakeoff(scene);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const exportPng = async () => {
    const svg = document.querySelector<SVGSVGElement>(".plan-viewport svg");
    if (!svg) return;
    setBusy(true);
    setErr(null);
    try {
      await downloadRenderImage(await captureSvgJpeg(svg));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Persist the CURRENT scene as this project's edited design (never the undo stack). Stable id per
  // editor session so repeated saves update one record; new when opened fresh from a version.
  const designKey = useMemo(() => designId ?? `d-${Date.now().toString(36)}`, [designId]);
  const save = (): { ok: boolean } => {
    if (!scene) return { ok: false };
    if (!projectId) {
      setSaveMsg("Open this from a project to save it.");
      return { ok: false };
    }
    const res = saveEditedDesign(projectId, {
      id: designKey,
      name: designName ?? "Edited design",
      forkedFrom: forkedFrom ?? null,
      scene,
      updatedAt: Date.now(),
    });
    setSaveMsg(res.ok ? "Saved." : res.error);
    return { ok: res.ok };
  };

  // Fork-on-first-edit: a design record is created only once a command has been committed (the
  // history grew past the seed scene). Opening a version and pressing Done with no edits leaves no
  // trace. Done saves any real edits (so work is never lost), but stays open if the save fails.
  const dirty = history.length > 1;
  const done = () => {
    if (dirty && !save().ok) return;
    onExit();
  };

  return (
    <main className="studio">
      <section className="stage">
        {scene ? (
          <SceneCanvas
            scene={scene}
            selectedZoneId={selectedZoneId}
            onSelectZone={selectZone}
            mergeMode={mergeMode}
            mergeSelection={mergeSelection}
            onToggleMergeZone={toggleMergeZone}
            selectedItem={selectedItem}
            onSelectItem={selectItem}
            onMoveItem={moveItem}
            onRotateItem={rotateItem}
            onDeleteItem={deleteItem}
            selectedDoorId={selectedDoorId}
            onSelectDoor={selectDoor}
            onSlideDoor={slideDoor}
            onFlipDoor={flipDoor}
          />
        ) : (
          <div className="empty">
            <div className="glyph">◳</div>
            <p>{busy ? "Building the editable scene…" : "No scene."}</p>
          </div>
        )}
      </section>

      <aside className="panel">
        <div className="scene-toolbar">
          <button type="button" className="link-btn" onClick={done}>← Done</button>
          <div className="scene-toolbar-actions">
            <button type="button" className={`link-btn${mergeMode ? " is-on" : ""}`} aria-pressed={mergeMode} onClick={toggleMergeMode}>⇔ Merge</button>
            <button type="button" className="link-btn" onClick={undo} disabled={!canUndo} aria-label="Undo">↶ Undo</button>
            <button type="button" className="link-btn" onClick={redo} disabled={!canRedo} aria-label="Redo">↷ Redo</button>
            <button type="button" className="link-btn" onClick={save} disabled={!scene}>Save</button>
          </div>
        </div>

        {saveMsg && <div className="save-msg" role="status">{saveMsg}</div>}
        {err && <div className="err" role="alert">{err}</div>}

        {metrics && <SceneScoreboard metrics={metrics} />}

        {scene && (
          <>
            <hr className="ds-rule" />
            {mergeMode ? (
              <div className="merge-rooms">
                <div className="swap-head">
                  <Eyebrow>Merge zones</Eyebrow>
                  <button type="button" className="link-btn is-on" aria-pressed onClick={toggleMergeMode}>Cancel</button>
                </div>
                <p className="disclaim" style={{ marginBottom: 10 }}>
                  Pick two adjacent zones on the plan, then merge them into one larger space.
                </p>
                <button
                  type="button"
                  className="export-btn export-btn--primary"
                  disabled={mergeSelection.length !== 2 || busy}
                  onClick={applyMerge}
                >
                  <span className="export-btn-label">{busy ? "Merging…" : "Merge these two"}</span>
                  <span className="export-btn-meta">{mergeSelection.length} of 2 picked</span>
                </button>
              </div>
            ) : selectedItem ? (
              <Callout quiet>Drag to move, use the grip to rotate, and Delete (or the ✕) to remove this piece. Esc deselects.</Callout>
            ) : selectedDoor ? (
              <DoorPanel door={selectedDoor} />
            ) : metrics && selectedZone ? (
              <ZonePanel
                zone={selectedZone}
                scene={scene}
                metrics={metrics}
                settings={settings}
                busy={settingsBusy}
                onChangeType={changeType}
                onSetEnclosed={setEnclosed}
                onSwapPlate={swapPlate}
              />
            ) : (
              <Callout quiet>Select a zone, a piece, or a door on the plan to edit it — or use Merge to combine two zones.</Callout>
            )}
          </>
        )}

        <hr className="ds-rule" />
        <div className="exports">
          <Eyebrow style={{ display: "block", marginBottom: 12 }}>Export</Eyebrow>
          <div className="export-actions">
            <button type="button" className="export-btn" onClick={exportDxf} disabled={!scene || busy}>
              <span className="export-btn-label">CAD drawing</span>
              <span className="export-btn-meta">{busy ? "Preparing…" : "DXF"}</span>
            </button>
            <button type="button" className="export-btn" onClick={exportTakeoff} disabled={!scene || busy}>
              <span className="export-btn-label">Quantity takeoff</span>
              <span className="export-btn-meta">{busy ? "Preparing…" : "Excel · post-edit BOM"}</span>
            </button>
            <button type="button" className="export-btn" onClick={exportPng} disabled={!scene || busy}>
              <span className="export-btn-label">Plan image</span>
              <span className="export-btn-meta">{busy ? "Preparing…" : "PNG"}</span>
            </button>
          </div>
        </div>
      </aside>
    </main>
  );
}
