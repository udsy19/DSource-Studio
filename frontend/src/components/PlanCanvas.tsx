import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type {
  ExtractedFurniture,
  ExtractedLayout,
  ExtractedRoom,
  FurnitureCategory,
  Instance,
  Plan,
  WallType,
} from "../types";
import { furnitureSymbol } from "./furnitureSymbols";

// Two modes: the generated fit (plan + instances) and the user's REAL extracted layout.
// In fit mode, enclosed rooms can be pinned (the iterate loop) when onTogglePin is supplied.
type FitProps = {
  plan: Plan;
  instances: Instance[];
  pinnedKeys?: Set<string>;
  onTogglePin?: (it: Instance) => void;
  compact?: boolean; // a contained, non-interactive mini-plan (version thumbnails) — no pan/zoom chrome
};
// Extracted-layout mode also drives swap: a furniture item (real SKU) or a room can be selected
// for a piece / room swap when the matching select handler is supplied.
type LayoutProps = {
  layout: ExtractedLayout;
  compact?: boolean;
  selectedFurnitureKey?: string | null;
  onSelectFurniture?: (f: ExtractedFurniture) => void;
  selectedRoomId?: string | null;
  onSelectRoom?: (r: ExtractedRoom) => void;
  // Editable canvas: drag a piece to a new position (x, y = its new bbox min-corner, feet), or
  // remove it. When omitted the plan is read-only (viewer / thumbnail).
  onMoveFurniture?: (key: string, x: number, y: number) => void;
  onDeleteFurniture?: (key: string) => void;
  // Room markers the user has dropped (feet) + place mode: a click on the plan drops one.
  markers?: { type: string; label: string; x: number; y: number }[];
  placing?: boolean;
  onPlacePoint?: (x: number, y: number) => void;
};
type Props = FitProps | LayoutProps;

// Generated-fit instance presentation: which furniture SYMBOL stands in for each program
// type, whether the type reads as an ENCLOSED room (drawn with a room outline + small label),
// and the category tint. Unknown types fall back to an open low box.
// Program family → the quiet floor tint that distinguishes office / meeting / collaboration /
// amenity rooms within the warm-paper palette. Shared by both renderers (FitPlan carries the
// family explicitly; LayoutPlan resolves it from the room's type via roomFill).
type RoomFamily = "open" | "office" | "meeting" | "collab" | "amenity";
const FAMILY_FILL: Record<RoomFamily, string> = {
  open: "--room-open",       // open workstation field + circulation — a quiet neutral it recedes to
  office: "--room-office",
  meeting: "--room-meeting",
  collab: "--room-collab",
  amenity: "--room-amenity",
};
const FAMILY_LABEL: Record<RoomFamily, string> = {
  open: "Open plan",
  office: "Office",
  meeting: "Meeting",
  collab: "Collab",
  amenity: "Amenity",
};

type FitKind = { symbol: FurnitureCategory; tint: string; room?: string; family?: RoomFamily };
const FIT: Record<string, FitKind> = {
  workstation: { symbol: "desk", tint: "--furn-work" },
  private_office: { symbol: "desk", tint: "--furn-work", room: "OFFICE", family: "office" },
  meeting_room: { symbol: "table", tint: "--furn-work", room: "MEETING", family: "meeting" },
  collaboration: { symbol: "sofa", tint: "--furn-seat" },
  phone_booth: { symbol: "stool", tint: "--furn-storage", room: "BOOTH", family: "collab" },
  reception: { symbol: "other", tint: "--furn-storage", room: "RECEPTION", family: "collab" },
  kitchen: { symbol: "other", tint: "--furn-storage", room: "KITCHEN", family: "amenity" },
  wellness: { symbol: "sofa", tint: "--furn-seat", room: "WELLNESS", family: "amenity" },
  copy_print: { symbol: "other", tint: "--furn-storage", room: "COPY", family: "amenity" },
  storage: { symbol: "other", tint: "--furn-storage", room: "STORAGE", family: "amenity" },
};
const FIT_FALLBACK: FitKind = { symbol: "other", tint: "--furn-other" };

// Infer a program family from a free-text room label (extracted layouts have no typed program).
function roomFamilyFill(label: string): string {
  const s = label.toLowerCase();
  if (/(office|cabin|director|manager|md\b|work)/.test(s)) return FAMILY_FILL.office;
  if (/(meet|conf|board|huddle|discuss|interview)/.test(s)) return FAMILY_FILL.meeting;
  if (/(collab|lounge|breakout|break|cafe|caf|waiting|reception|open)/.test(s)) return FAMILY_FILL.collab;
  return FAMILY_FILL.amenity;
}

// Backend Room.type → floor tint. The reader now types every room (from its label or, for a
// label-less plan, its furniture mix), so colour by type first; fall back to label inference,
// then a neutral fill for circulation/core/genuinely-unknown space.
const ROOM_TYPE_FAMILY: Record<string, RoomFamily> = {
  open: "open",         // the workstation field / circulation — quiet, so enclosed rooms carry colour
  office: "office",
  meeting: "meeting",
  huddle: "meeting",
  collab: "collab",
  reception: "collab",
  kitchen: "amenity",
  wellness: "amenity",
  storage: "amenity",
  copy_print: "amenity",
};
function roomFill(r: ExtractedRoom): string {
  const fam = ROOM_TYPE_FAMILY[r.type];
  if (fam) return FAMILY_FILL[fam];
  if (r.label) return roomFamilyFill(r.label);
  return "--room-fill";
}

// Stable identity for a placed instance — used to pin/unpin rooms across regenerations.
export const instanceKey = (it: Instance): string =>
  `${it.type}:${it.x.toFixed(2)}:${it.y.toFixed(2)}`;

// Stable identity for a placed furniture item — used to select/replace the right one on swap.
export const furnitureKey = (f: ExtractedFurniture): string =>
  `${f.category}:${f.x.toFixed(2)}:${f.y.toFixed(2)}`;

// wall poché per type — fill token (the solid cut band), legend-swatch token, label, and
// the assumed cut THICKNESS in feet (weight hierarchy: perimeter/core heaviest, glass thinnest).
// `door` is an opening, not a poché band — it draws as a swing, so it carries no fill.
const WALL: Record<WallType, { fill: string; token: string; label: string; thickness: number }> = {
  perimeter: { fill: "--poche-perimeter", token: "--wall-perimeter", label: "Perimeter", thickness: 0.8 },
  core: { fill: "--poche-core", token: "--wall-core", label: "Core", thickness: 0.7 },
  drywall: { fill: "--poche-drywall", token: "--wall-drywall", label: "Drywall", thickness: 0.4 },
  half_drywall: { fill: "--poche-half-drywall", token: "--wall-half-drywall", label: "Half-drywall", thickness: 0.3 },
  glass: { fill: "--poche-glass", token: "--wall-glass", label: "Glass", thickness: 0.18 },
  door: { fill: "--wall-door", token: "--wall-door", label: "Door", thickness: 0.4 },
  unknown: { fill: "--poche-unknown", token: "--wall-unknown", label: "Other", thickness: 0.3 },
};

// furniture footprint colour token by category
const FURN: Record<FurnitureCategory, string> = {
  chair: "--furn-seat",
  sofa: "--furn-seat",
  stool: "--furn-seat",
  desk: "--furn-work",
  workstation: "--furn-work",
  table: "--furn-work",
  storage: "--furn-storage",
  panel: "--furn-storage",
  tv: "--furn-storage",
  planter: "--furn-green",
  mullion: "--furn-other",
  other: "--furn-other",
};

const PAD = 8; // feet of margin around the plate
const SHEET_INSET = PAD * 0.45; // drawing-frame inset from the viewBox edge (feet)

// A wall is a polyline; render each segment as a filled band `thickness` ft wide centred on
// the segment so it reads as a solid cut element (poché). Returns one screen-space polygon
// point string per segment, already y-flipped via the view mappers.
function pocheBands(
  points: [number, number][],
  thickness: number,
  fx: (x: number) => number,
  fy: (y: number) => number,
): string[] {
  const half = thickness / 2;
  const bands: string[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const [ax, ay] = points[i];
    const [bx, by] = points[i + 1];
    const dx = bx - ax;
    const dy = by - ay;
    const len = Math.hypot(dx, dy);
    if (len === 0) continue;
    // unit normal in feet, then mapped to screen (fx/fy are translations/flips, so offsets map cleanly)
    const nx = (-dy / len) * half;
    const ny = (dx / len) * half;
    const corners: [number, number][] = [
      [ax + nx, ay + ny],
      [bx + nx, by + ny],
      [bx - nx, by - ny],
      [ax - nx, ay - ny],
    ];
    bands.push(corners.map(([x, y]) => `${fx(x).toFixed(2)},${fy(y).toFixed(2)}`).join(" "));
  }
  return bands;
}

// Pick a round scale-bar length (ft) that's ~1/6 of the plate width: 1,2,5,10,20,50…
function niceScaleFeet(span: number): number {
  const target = span / 6;
  const pow = Math.pow(10, Math.floor(Math.log10(target)));
  for (const m of [1, 2, 5]) if (m * pow >= target) return m * pow;
  return 10 * pow;
}

function useView(minX: number, minY: number, maxX: number, maxY: number) {
  return useMemo(() => {
    const x0 = minX - PAD;
    const x1 = maxX + PAD;
    const y0 = minY - PAD;
    const y1 = maxY + PAD;
    // flip Y so north is up; return mappers
    const fx = (x: number) => x - x0;
    const fy = (y: number) => y1 - y;
    return { w: x1 - x0, h: y1 - y0, fx, fy };
  }, [minX, minY, maxX, maxY]);
}

type View = ReturnType<typeof useView>;

// Soft warm drop-shadow that lifts enclosed rooms off the paper. One shared filter, referenced
// sparingly (rooms/containers only — never per-desk) so ~300-desk plans stay fast.
function PlanDefs() {
  return (
    <defs>
      <filter id="plan-lift" x="-25%" y="-25%" width="150%" height="150%">
        <feDropShadow dx="0" dy="0.5" stdDeviation="0.7" floodColor="var(--plan-shadow)" floodOpacity="1" />
      </filter>
    </defs>
  );
}

// Thin inner border framing the sheet — the first cue that this is a real CAD plate.
function SheetFrame({ view }: { view: View }) {
  return (
    <rect
      className="sheet-frame"
      x={SHEET_INSET}
      y={SHEET_INSET}
      width={view.w - SHEET_INSET * 2}
      height={view.h - SHEET_INSET * 2}
      fill="none"
      vectorEffect="non-scaling-stroke"
    />
  );
}

// Refined architectural scale bar (alternating filled/open halves + ticks), bottom-right.
function ScaleBar({ view, span }: { view: View; span: number }) {
  const ft = niceScaleFeet(span);
  const y = view.h - SHEET_INSET - 1.8;
  const x2 = view.w - SHEET_INSET - 1.6;
  const x1 = x2 - ft;
  const mid = (x1 + x2) / 2;
  const barH = 0.7;
  return (
    <g className="scale-bar-mark">
      <rect className="scale-fill" x={x1} y={y - barH / 2} width={ft / 2} height={barH} />
      <rect
        className="scale-frame"
        x={x1}
        y={y - barH / 2}
        width={ft}
        height={barH}
        fill="none"
        vectorEffect="non-scaling-stroke"
      />
      <line className="scale-frame" x1={mid} y1={y - barH / 2} x2={mid} y2={y + barH / 2} vectorEffect="non-scaling-stroke" />
      <text className="scale-label" x={x1} y={y + 2.2} textAnchor="middle">0</text>
      <text className="scale-label" x={x2} y={y + 2.2} textAnchor="middle">{ft} ft</text>
    </g>
  );
}

// Slim north arrow, stacked just above the scale bar.
function NorthArrow({ view }: { view: View }) {
  const cx = view.w - SHEET_INSET - 2;
  const base = view.h - SHEET_INSET - 5.2;
  const top = base - 3.2;
  return (
    <g className="north-arrow">
      <path
        className="north-mark"
        d={`M ${cx} ${top} L ${cx - 1.1} ${base} L ${cx} ${base - 0.9} L ${cx + 1.1} ${base} Z`}
        vectorEffect="non-scaling-stroke"
      />
      <text className="north-label" x={cx} y={top - 0.8} textAnchor="middle">N</text>
    </g>
  );
}

// Corner title block — the touch that reads as a drafted sheet. Date is a placeholder (no real
// time: keeps the render deterministic).
function TitleBlock({ view, title, kind }: { view: View; title: string; kind: string }) {
  const w = 25;
  const h = 9;
  const x = view.w - SHEET_INSET - w;
  const y = SHEET_INSET;
  const px = 1.4;
  const ruleY = y + h * 0.6;
  return (
    <g className="title-block">
      {/* opaque paper fill so the block reads as a clean overlay, not transparent over the plan */}
      <rect x={x} y={y} width={w} height={h} fill="var(--paper)" />
      <rect className="title-box" x={x} y={y} width={w} height={h} fill="none" vectorEffect="non-scaling-stroke" />
      <line className="title-rule" x1={x} y1={ruleY} x2={x + w} y2={ruleY} vectorEffect="non-scaling-stroke" />
      <text className="title-eyebrow" x={x + px} y={y + 2.4}>DSOURCE STUDIO</text>
      <text className="title-name" x={x + px} y={y + 5}>{title}</text>
      <text className="title-meta" x={x + px} y={ruleY + 2.1}>{kind}</text>
      <text className="title-meta" x={x + w - px} y={ruleY + 2.1} textAnchor="end">DATE — — —</text>
    </g>
  );
}

// Frame + scale bar + north arrow + title block, shared by both renderers.
function SheetFurniture({ view, span, title, kind }: { view: View; span: number; title: string; kind: string }) {
  return (
    <>
      <SheetFrame view={view} />
      <NorthArrow view={view} />
      <ScaleBar view={view} span={span} />
      <TitleBlock view={view} title={title} kind={kind} />
    </>
  );
}

// Derive a sheet name from an extracted-layout source path/filename.
function sheetName(source: string): string {
  const base = source.split(/[\\/]/).pop() ?? source;
  const clean = base.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim().toUpperCase();
  return clean || "EXTRACTED LAYOUT";
}

// ── pan + zoom ──
// One shared interaction for both plans: wheel zooms toward the cursor, pointer-drag pans, and
// double-click resets. Transform lives in viewBox units and drives a single <g> wrapping the whole
// sheet — strokes carry vectorEffect="non-scaling-stroke" so they stay crisp at any zoom.
const MIN_K = 1;
const MAX_K = 10;
const DRAG_THRESHOLD = 4; // px of pointer travel before a press counts as a pan (not a click)

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

type Transform = { k: number; tx: number; ty: number };

function usePanZoom(w: number, h: number) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [t, setT] = useState<Transform>({ k: 1, tx: 0, ty: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const drag = useRef<{ x: number; y: number; tx: number; ty: number } | null>(null);
  const moved = useRef(false); // true once the active gesture passed the drag threshold

  // keep the sheet filling the viewport: at k=1 pan is pinned to 0, so the plan can never be lost.
  const settle = (k: number, tx: number, ty: number): Transform => {
    const kk = clamp(k, MIN_K, MAX_K);
    return { k: kk, tx: clamp(tx, w * (1 - kk), 0), ty: clamp(ty, h * (1 - kk), 0) };
  };

  // client px → viewBox units (honours preserveAspectRatio letterboxing)
  const toViewBox = (clientX: number, clientY: number) => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    return pt.matrixTransform(ctm.inverse());
  };

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); // zoom the plan instead of scrolling the page
      const p = toViewBox(e.clientX, e.clientY);
      if (!p) return;
      setT((prev) => {
        const k = clamp(prev.k * Math.exp(-e.deltaY * 0.0015), MIN_K, MAX_K);
        const cx = (p.x - prev.tx) / prev.k;
        const cy = (p.y - prev.ty) / prev.k;
        return settle(k, p.x - cx * k, p.y - cy * k);
      });
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w, h]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    svgRef.current?.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, tx: t.tx, ty: t.ty };
    moved.current = false;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!moved.current && Math.hypot(dx, dy) < DRAG_THRESHOLD) return;
    moved.current = true;
    if (!isPanning) setIsPanning(true);
    const ctm = svgRef.current?.getScreenCTM();
    if (!ctm) return;
    setT((prev) => settle(prev.k, d.tx + dx / ctm.a, d.ty + dy / ctm.d));
  };

  const endDrag = (e: React.PointerEvent) => {
    if (svgRef.current?.hasPointerCapture(e.pointerId)) svgRef.current.releasePointerCapture(e.pointerId);
    drag.current = null;
    if (isPanning) setIsPanning(false);
    // moved.current is left set until the next press so the trailing click can be ignored
  };

  const reset = () => setT({ k: 1, tx: 0, ty: 0 });
  const zoomed = t.k > 1.001 || t.tx !== 0 || t.ty !== 0;

  return {
    svgRef,
    transform: `translate(${t.tx} ${t.ty}) scale(${t.k})`,
    isPanning,
    zoomed,
    reset,
    didDrag: () => moved.current,
    handlers: {
      onPointerDown,
      onPointerMove,
      onPointerUp: endDrag,
      onPointerCancel: endDrag,
      onDoubleClick: reset,
    },
  };
}

type RoomTag = { name: string; area: number; left: number; top: number };

// What a plan's `draw` closure receives: a click guard (so a pan never fires a room's onClick) and a
// binder that wires hover/focus highlight + the floating room tag onto a room <g>.
type PlanApi = {
  didDrag: () => boolean;
  // Convert a client-pixel drag (from → to) into a world-feet delta, accounting for the current
  // pan/zoom. Used by the editable canvas to translate a dragged piece. {0,0} before first paint.
  worldDelta: (
    from: { x: number; y: number },
    to: { x: number; y: number },
  ) => { dx: number; dy: number };
  bindRoom: (name: string, area: number) => {
    onPointerEnter: (e: React.PointerEvent) => void;
    onPointerMove: (e: React.PointerEvent) => void;
    onPointerLeave: () => void;
    onFocus: (e: React.FocusEvent<SVGGElement>) => void;
    onBlur: () => void;
  };
};

// Shared sheet shell for both plans: the pan/zoom <svg>, the drafted sheet furniture, the hover
// room tag, and the pan/zoom hint + reset control. `draw` paints the plan body inside the transform.
const NOOP_ROOM = {
  onPointerEnter: () => {},
  onPointerMove: () => {},
  onPointerLeave: () => {},
  onFocus: () => {},
  onBlur: () => {},
};
const STATIC_API: PlanApi = {
  didDrag: () => false,
  worldDelta: () => ({ dx: 0, dy: 0 }),
  bindRoom: () => NOOP_ROOM,
};

function PlanStage({
  view,
  span,
  title,
  kind,
  draw,
  overlay,
  compact,
  placing,
  onPlacePoint,
}: {
  view: View;
  span: number;
  title: string;
  kind: string;
  draw: (api: PlanApi) => ReactNode;
  overlay?: ReactNode;
  compact?: boolean;
  placing?: boolean;
  onPlacePoint?: (x: number, y: number) => void;
}) {
  // Version thumbnails: a plain, contained, non-interactive mini-plan — no absolute viewport, no
  // pan/zoom, no sheet chrome — so many of them can sit in the side panel without stacking.
  if (compact) {
    return (
      <svg
        className="plan-static"
        viewBox={`0 0 ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        aria-hidden="true"
      >
        <PlanDefs />
        <g>{draw(STATIC_API)}</g>
      </svg>
    );
  }

  const pz = usePanZoom(view.w, view.h);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<SVGGElement | null>(null);
  const [tag, setTag] = useState<RoomTag | null>(null);

  const showTag = (name: string, area: number, clientX: number, clientY: number) => {
    if (pz.isPanning) return;
    const host = hostRef.current;
    if (!host) return;
    const r = host.getBoundingClientRect();
    setTag({ name, area, left: clientX - r.left, top: clientY - r.top });
  };

  const api: PlanApi = {
    didDrag: pz.didDrag,
    worldDelta: (from, to) => {
      const ctm = contentRef.current?.getScreenCTM();
      if (!ctm) return { dx: 0, dy: 0 };
      const inv = ctm.inverse();
      // contentRef's local space is view-space (children are drawn via view.fx/fy); invert the
      // full screen CTM to map client px there. fx has slope +1 and fy slope -1, so world dx = view
      // dx and world dy = -view dy.
      const a = new DOMPoint(from.x, from.y).matrixTransform(inv);
      const b = new DOMPoint(to.x, to.y).matrixTransform(inv);
      return { dx: b.x - a.x, dy: -(b.y - a.y) };
    },
    bindRoom: (name, area) => ({
      onPointerEnter: (e) => showTag(name, area, e.clientX, e.clientY),
      onPointerMove: (e) => showTag(name, area, e.clientX, e.clientY),
      onPointerLeave: () => setTag(null),
      onFocus: (e) => {
        const r = e.currentTarget.getBoundingClientRect();
        showTag(name, area, r.left + r.width / 2, r.top);
      },
      onBlur: () => setTag(null),
    }),
  };

  // Click → world-feet, for dropping a room marker. Recovers the view origin from view.fx(0)/fy(0)
  // (fx(x)=x-x0, fy(y)=y1-y), so world = (local.x - fx(0), fy(0) - local.y).
  const placeAt = (clientX: number, clientY: number) => {
    if (!onPlacePoint || !placing || pz.didDrag()) return;
    const ctm = contentRef.current?.getScreenCTM();
    if (!ctm) return;
    const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
    const r = (n: number) => Math.round(n * 100) / 100;
    onPlacePoint(r(p.x - view.fx(0)), r(view.fy(0) - p.y));
  };

  return (
    <div className="plan-viewport" ref={hostRef}>
      <svg
        ref={pz.svgRef}
        viewBox={`0 0 ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        className={`${pz.isPanning ? "is-panning" : ""}${placing ? " is-placing" : ""}`.trim() || undefined}
        role="application"
        aria-label={`${title} floor plan — drag to pan, scroll to zoom`}
        {...pz.handlers}
        onClick={placing ? (e) => placeAt(e.clientX, e.clientY) : undefined}
      >
        <PlanDefs />
        <g ref={contentRef} transform={pz.transform}>
          {draw(api)}
          <SheetFurniture view={view} span={span} title={title} kind={kind} />
        </g>
      </svg>
      {tag && (
        <div className="room-tag" style={{ left: tag.left, top: tag.top }} aria-hidden="true">
          <span className="room-tag-name">{tag.name}</span>
          {tag.area > 0 && <span className="room-tag-area">{Math.round(tag.area)} sf</span>}
        </div>
      )}
      <div className="plan-controls">
        <span className="plan-hint">drag to pan · scroll to zoom</span>
        {pz.zoomed && (
          <button type="button" className="plan-reset" onClick={pz.reset}>
            Reset view
          </button>
        )}
      </div>
      {overlay}
    </div>
  );
}

export default function PlanCanvas(props: Props) {
  if ("layout" in props) return <LayoutPlan {...props} />;
  return <FitPlan {...props} />;
}

/* ── generated-fit plan ──
   Drawn to read like LayoutPlan: the building edge and each enclosed room are SOLID poché
   walls (reusing pocheBands), open furniture is hairline ink contained in its footprint, and
   every enclosed room is inset + clipped so no chair mark ever crosses a wall. Enclosed rooms
   stay pinnable for the iterate loop. */
function FitPlan({ plan, instances, pinnedKeys, onTogglePin, compact }: FitProps) {
  const xs = plan.boundary.map((p) => p[0]);
  const ys = plan.boundary.map((p) => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);
  const view = useView(minX, minY, maxX, maxY);

  // a closed ring (boundary/core polygons may omit the closing point) — pocheBands draws per
  // segment, so append the first point to seal the loop into one continuous wall.
  const closed = (pts: [number, number][]): [number, number][] =>
    pts.length > 1 && (pts[0][0] !== pts[pts.length - 1][0] || pts[0][1] !== pts[pts.length - 1][1])
      ? [...pts, pts[0]]
      : pts;

  return (
    <PlanStage view={view} span={maxX - minX} title="TEST-FIT" kind="SPACE PLAN" compact={compact} draw={(api) => (
    <>
      {/* cores — faint structural fill ringed by a heavy core-poché wall */}
      {plan.cores.map((c, i) => (
        <g key={`core-${i}`}>
          <polygon
            points={c.map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ")}
            fill="var(--poche-core)"
            fillOpacity={0.12}
          />
          {pocheBands(closed(c), WALL.core.thickness, view.fx, view.fy).map((pts, j) => (
            <polygon key={j} className="poche-band" points={pts} fill="var(--poche-core)" vectorEffect="non-scaling-stroke" />
          ))}
        </g>
      ))}

      {instances.map((it, i) => {
        // a slotted piece is real furniture INSIDE a room — render its category symbol, never a
        // walled room (FIT["storage"] etc. carry a `room`, which would draw a phantom STORAGE room).
        const kind: FitKind = it.slotted
          ? { symbol: it.type as FurnitureCategory, tint: "--furn-seat" }
          : (FIT[it.type] ?? FIT_FALLBACK);
        // local 0..w/0..h origin at the footprint's top-left (world min-x / max-y), rotated
        // about the centre — same convention as LayoutPlan's furniture so symbols read upright.
        const ox = view.fx(it.x);
        const oy = view.fy(it.y + it.h);
        const cx = view.fx(it.x + it.w / 2);
        const cy = view.fy(it.y + it.h / 2);
        const pinnable = !!kind.room && !!onTogglePin;
        const pinned = pinnable && (pinnedKeys?.has(instanceKey(it)) ?? false);
        const pin = pinnable ? () => onTogglePin!(it) : undefined;

        // open furniture (workstations, collab) — hairline symbol inside its own footprint
        if (!kind.room) {
          return (
            <g
              key={`i-${i}`}
              transform={`translate(${ox} ${oy}) rotate(${-it.rotation} ${cx - ox} ${cy - oy})`}
              fill={`var(${kind.tint})`}
              fillOpacity={0.14}
            >
              {furnitureSymbol(kind.symbol, it.w, it.h)}
            </g>
          );
        }

        // enclosed room — poché-wall perimeter + faint fill + an INSET, CLIPPED furniture glyph
        // so chair marks can never cross the wall, regardless of the symbol's own math.
        const m = Math.min(it.w, it.h) * 0.16; // wall→furniture margin (feet)
        const iw = Math.max(it.w - m * 2, 0.1);
        const ih = Math.max(it.h - m * 2, 0.1);
        const clipId = `fit-room-clip-${i}`;
        return (
          <g
            key={`i-${i}`}
            transform={`translate(${ox} ${oy}) rotate(${-it.rotation} ${cx - ox} ${cy - oy})`}
            className={pinnable ? "fit-room fit-room--pinnable" : "fit-room"}
            role={pinnable ? "button" : "img"}
            tabIndex={pinnable ? 0 : undefined}
            aria-pressed={pinnable ? pinned : undefined}
            aria-label={
              pinnable
                ? `${pinned ? "Unpin" : "Pin"} ${kind.room}, ${Math.round(it.w * it.h)} square feet`
                : `${kind.room}, ${Math.round(it.w * it.h)} square feet`
            }
            {...api.bindRoom(kind.room!, it.w * it.h)}
            onClick={pin ? () => { if (!api.didDrag()) pin(); } : undefined}
            onKeyDown={
              pin
                ? (e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      pin();
                    }
                  }
                : undefined
            }
          >
            <clipPath id={clipId}>
              <rect x={m} y={m} width={iw} height={ih} />
            </clipPath>
            {/* soft lift — an opaque paper caster (invisible against the sheet) casts the shadow */}
            <rect x={0} y={0} width={it.w} height={it.h} fill="var(--paper)" filter="url(#plan-lift)" />
            {/* floor fill — subtle program-family tint, accent-soft when pinned or hovered */}
            <rect
              className="fit-room-floor"
              x={0}
              y={0}
              width={it.w}
              height={it.h}
              fill={pinned ? "var(--accent-soft)" : `var(${kind.family ? FAMILY_FILL[kind.family] : "--room-fill"})`}
            />
            {/* inset, clipped furniture glyph — nothing escapes the interior */}
            <g clipPath={`url(#${clipId})`}>
              <g
                transform={`translate(${m} ${m})`}
                fill={`var(${kind.tint})`}
                fillOpacity={0.14}
              >
                {furnitureSymbol(kind.symbol, iw, ih)}
              </g>
            </g>
            {/* room wall — solid poché perimeter, accent stroke when pinned */}
            {pocheBands(
              [[0, 0], [it.w, 0], [it.w, it.h], [0, it.h], [0, 0]],
              WALL.drywall.thickness,
              (x) => x,
              (y) => y,
            ).map((pts, j) => (
              <polygon key={j} className="poche-band" points={pts} fill={pinned ? "var(--accent)" : "var(--poche-drywall)"} vectorEffect="non-scaling-stroke" />
            ))}
            <text className="fit-room-label" x={it.w / 2} y={it.h / 2} textAnchor="middle">
              {kind.room}
            </text>
            {pinned && <circle cx={it.w - 1.3} cy={1.3} r={0.9} fill="var(--accent)" />}
          </g>
        );
      })}

      {plan.columns.map(([x, y], i) => (
        <circle key={`col-${i}`} cx={view.fx(x)} cy={view.fy(y)} r={0.9} fill="var(--ink)" opacity={0.55} />
      ))}

      {/* building edge — one closed perimeter poché wall, drawn last on top */}
      {pocheBands(closed(plan.boundary), WALL.perimeter.thickness, view.fx, view.fy).map((pts, j) => (
        <polygon key={`b-${j}`} className="poche-band" points={pts} fill="var(--poche-perimeter)" vectorEffect="non-scaling-stroke" />
      ))}
    </>
    )} />
  );
}

/* ── real extracted-layout plan ── */
function LayoutPlan({
  layout,
  compact,
  selectedFurnitureKey,
  onSelectFurniture,
  selectedRoomId,
  onSelectRoom,
  onMoveFurniture,
  onDeleteFurniture,
  markers,
  placing,
  onPlacePoint,
}: LayoutProps) {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const view = useView(minx, miny, maxx, maxy);
  // Active drag of a furniture piece: its key + the live world-feet offset (for the preview
  // transform). A move commits on pointer-up; a drag beyond MOVE_MIN_FT suppresses the select click.
  const [drag, setDrag] = useState<{ key: string; dx: number; dy: number } | null>(null);
  const dragStart = useRef<{ x: number; y: number; key: string; moved: boolean } | null>(null);
  const MOVE_MIN_FT = 0.25;
  const usedTypes = useMemo(
    () => new Set(layout.walls.map((w) => w.type)),
    [layout.walls],
  );
  // Room families actually present, for the colour legend — resolved from each room's type (the
  // same mapping roomFill uses), so the legend matches the fills on the plan.
  const roomFamilies = useMemo(() => {
    const fams = new Set<RoomFamily>();
    for (const r of layout.rooms) {
      const fam = ROOM_TYPE_FAMILY[r.type];
      if (fam) fams.add(fam);
    }
    return fams;
  }, [layout.rooms]);

  // De-conflict room labels: place the largest rooms first and drop any whose (padded) label box
  // would collide with one already placed, so dense office/conference clusters never smear. Rooms
  // too small to hold a legible label are dropped outright — every room still lists in the side
  // panel and reveals its name + area on hover. (Box half-extents are in feet — the SVG units.)
  const MIN_LABEL_AREA = 60; // sf — below this a two-line label can't fit inside the room
  const labelled = useMemo(() => {
    const placed: { x: number; y: number; hw: number; hh: number }[] = [];
    const show = new Set<string>();
    for (const r of [...layout.rooms].filter((r) => r.label && r.center).sort((a, b) => b.area_sf - a.area_sf)) {
      if (r.area_sf > 0 && r.area_sf < MIN_LABEL_AREA) continue;
      const x = view.fx(r.center![0]);
      const y = view.fy(r.center![1]);
      // padded label box: ~0.75 ft per char wide (+1.5 ft breathing room), two lines tall
      const hw = Math.max(r.label.length * 0.75, 6.5) + 1.5;
      const hh = r.area_sf > 0 ? 4.4 : 2.8;
      if (!placed.some((p) => Math.abs(p.x - x) < p.hw + hw && Math.abs(p.y - y) < p.hh + hh)) {
        placed.push({ x, y, hw, hh });
        show.add(r.id);
      }
    }
    return show;
  }, [layout.rooms, view]);

  const polyline = (pts: [number, number][]) =>
    pts.map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ");

  return (
    <PlanStage
      view={view}
      span={maxx - minx}
      title={sheetName(layout.source)}
      kind="EXTRACTED LAYOUT"
      compact={compact}
      placing={placing}
      onPlacePoint={onPlacePoint}
      overlay={
        // legends — the room-family colour key and the wall-type key, each showing only what's present
        <>
          {roomFamilies.size > 0 && (
            <ul className="wall-legend room-legend" aria-label="Room types">
              {(Object.keys(FAMILY_FILL) as RoomFamily[])
                .filter((f) => roomFamilies.has(f))
                .map((f) => (
                  <li key={f}>
                    <span className="swatch" style={{ background: `var(${FAMILY_FILL[f]})` }} aria-hidden="true" />
                    {FAMILY_LABEL[f]}
                  </li>
                ))}
            </ul>
          )}
          <ul className="wall-legend" aria-label="Wall types">
            {(Object.keys(WALL) as WallType[])
              .filter((t) => usedTypes.has(t))
              .map((t) => (
                <li key={t}>
                  <span className="swatch" style={{ background: `var(${WALL[t].token})` }} aria-hidden="true" />
                  {WALL[t].label}
                </li>
              ))}
          </ul>
        </>
      }
      draw={(api) => (
      <>
        {/* rooms — faint filled polygons (where the walls close) with the label + area placed at
            the room's anchor, so every read room shows on the plan even without a closed boundary.
            Closed rooms are hover/focus targets: the shape shifts to the accent and a name + area
            tag follows the cursor (so even de-conflicted, label-suppressed rooms stay identifiable). */}
        {layout.rooms.map((r) => {
          const cx = r.center ? view.fx(r.center[0]) : null;
          const cy = r.center ? view.fy(r.center[1]) : null;
          const interactive = r.polygon.length >= 3;
          const selectable = interactive && !!onSelectRoom;
          const selected = selectable && selectedRoomId === r.id;
          const name = r.label || "Room";
          const sf = Math.round(r.area_sf);
          return (
            <g
              key={`room-${r.id}`}
              className={
                [interactive ? "layout-room" : "", selected ? "is-selected" : ""]
                  .filter(Boolean)
                  .join(" ") || undefined
              }
              role={selectable ? "button" : interactive ? "img" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-pressed={selectable ? selected : undefined}
              aria-label={
                interactive
                  ? `${selectable ? "Swap " : ""}${name}, ${sf} square feet`
                  : undefined
              }
              {...(interactive ? api.bindRoom(name, r.area_sf) : {})}
              onClick={selectable ? () => { if (!api.didDrag()) onSelectRoom!(r); } : undefined}
              onKeyDown={
                selectable
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onSelectRoom!(r);
                      }
                    }
                  : undefined
              }
            >
              {interactive && (
                <>
                  {/* soft lift — opaque paper caster (invisible against the sheet) carries the shadow */}
                  <polygon points={polyline(r.polygon)} fill="var(--paper)" filter="url(#plan-lift)" />
                  <polygon
                    className="room-shape"
                    points={polyline(r.polygon)}
                    fill={`var(${roomFill(r)})`}
                    fillOpacity={r.confidence != null && r.confidence < 0.9 ? 0.45 + 0.5 * r.confidence : 1}
                    stroke="var(--room-line)"
                    strokeWidth={1}
                    strokeDasharray={r.boundary_basis === "furniture_hull" ? "4 3" : undefined}
                    vectorEffect="non-scaling-stroke"
                  />
                </>
              )}
              {r.label && cx != null && cy != null && labelled.has(r.id) && (
                <text className="room-label" x={cx} y={cy} textAnchor="middle">
                  <tspan x={cx}>{r.label}</tspan>
                  {r.area_sf > 0 && (
                    <tspan className="room-area" x={cx} dy="1.2em">
                      {Math.round(r.area_sf)} sf
                    </tspan>
                  )}
                </text>
              )}
            </g>
          );
        })}

        {/* furniture — the item's REAL shape where the CAD carries one (outline polylines, already
            world coords → mapped straight to screen, no per-item transform), else a recognizable
            top-down plan symbol drawn in local 0..w / 0..h inside a translated/rotated <g>. Closed
            outline rings take the soft category tint; open runs are hairline ink only.
            Mullions are drawn by the glass panels, not as separate footprints. */}
        {layout.furniture.filter((f) => f.category !== "mullion").map((f, i) => {
          const tint = `var(${FURN[f.category] ?? "--furn-other"})`;
          const label = `${f.category}${f.brand ? ` · ${f.brand}` : ""}${f.model ? ` ${f.model}` : ""}`;

          // only real-SKU items (f.model) can be selected; wire interaction when a handler is supplied
          const k = furnitureKey(f);
          const selectable = !!f.model && !!onSelectFurniture;
          const selected = selectable && selectedFurnitureKey === k;
          const dragging = drag?.key === k;
          // live preview: shift by the world delta, expressed in view units (world dy is up → view -dy)
          const previewT = dragging ? `translate(${drag!.dx} ${-drag!.dy}) ` : "";
          const swap: Record<string, unknown> = selectable
            ? {
                className:
                  `layout-furn${selected ? " is-selected" : ""}` +
                  `${onMoveFurniture ? " is-movable" : ""}`,
                role: "button",
                tabIndex: 0,
                "aria-pressed": selected,
                "aria-label": `${onMoveFurniture ? "Move or swap" : "Swap"} ${label}`,
                onClick: () => {
                  if (api.didDrag()) return; // a canvas pan
                  if (dragStart.current?.moved) return; // finished a piece drag — don't also select
                  onSelectFurniture!(f);
                },
                onKeyDown: (e: React.KeyboardEvent) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectFurniture!(f);
                  } else if (onDeleteFurniture && (e.key === "Delete" || e.key === "Backspace")) {
                    e.preventDefault();
                    onDeleteFurniture(k);
                  }
                },
                ...(onMoveFurniture && {
                  onPointerDown: (e: React.PointerEvent) => {
                    e.stopPropagation(); // begin a piece drag, not a canvas pan
                    (e.currentTarget as Element).setPointerCapture(e.pointerId);
                    dragStart.current = { x: e.clientX, y: e.clientY, key: k, moved: false };
                  },
                  onPointerMove: (e: React.PointerEvent) => {
                    const s = dragStart.current;
                    if (!s || s.key !== k) return;
                    const d = api.worldDelta({ x: s.x, y: s.y }, { x: e.clientX, y: e.clientY });
                    if (Math.abs(d.dx) > MOVE_MIN_FT || Math.abs(d.dy) > MOVE_MIN_FT) s.moved = true;
                    setDrag({ key: k, dx: d.dx, dy: d.dy });
                  },
                  onPointerUp: () => {
                    const s = dragStart.current;
                    if (s && s.key === k && s.moved && drag && drag.key === k) {
                      onMoveFurniture(k, f.x + drag.dx, f.y + drag.dy);
                    }
                    setDrag(null); // dragStart kept so the trailing onClick sees `moved` and skips select
                  },
                }),
              }
            : {};

          if (f.outline?.length) {
            return (
              <g key={`f-${i}`} transform={previewT || undefined} stroke="var(--furn-line)" vectorEffect="non-scaling-stroke" {...swap}>
                <title>{label}</title>
                {f.outline.map((ring, j) => {
                  const closed =
                    ring.length > 2 &&
                    ring[0][0] === ring[ring.length - 1][0] &&
                    ring[0][1] === ring[ring.length - 1][1];
                  return closed ? (
                    <polygon key={j} points={polyline(ring)} fill={tint} fillOpacity={0.14} vectorEffect="non-scaling-stroke" />
                  ) : (
                    <polyline key={j} points={polyline(ring)} fill="none" vectorEffect="non-scaling-stroke" />
                  );
                })}
              </g>
            );
          }

          const ox = view.fx(f.x);
          const oy = view.fy(f.y + f.h);
          const cx = view.fx(f.x + f.w / 2);
          const cy = view.fy(f.y + f.h / 2);
          return (
            <g
              key={`f-${i}`}
              transform={`${previewT}translate(${ox} ${oy}) rotate(${-f.rotation} ${cx - ox} ${cy - oy})`}
              fill={tint}
              fillOpacity={0.14}
              {...swap}
            >
              <title>{label}</title>
              {furnitureSymbol(f.category, f.w, f.h)}
            </g>
          );
        })}

        {/* doors — a proper architectural swing: the leaf line + a quarter-circle arc.
            (x,y) is the hinge/threshold; rotation orients the opening. */}
        {layout.doors.map((d, i) => {
          const hx = view.fx(d.x);
          const hy = view.fy(d.y);
          return (
            <g
              key={`d-${i}`}
              transform={`translate(${hx} ${hy}) rotate(${-d.rotation})`}
              stroke="var(--wall-door)"
              vectorEffect="non-scaling-stroke"
              fill="none"
            >
              <line x1={0} y1={0} x2={d.width} y2={0} vectorEffect="non-scaling-stroke" />
              <path
                d={`M ${d.width} 0 A ${d.width} ${d.width} 0 0 1 0 ${d.width}`}
                strokeOpacity={0.5}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}

        {/* walls — filled poché bands, drawn last on top. Door segments are openings (no fill);
            their swing is drawn above. Weight hierarchy comes from the per-type fill + thickness. */}
        {layout.walls.filter((w) => w.type !== "door").map((wall, i) => {
          const s = WALL[wall.type] ?? WALL.unknown;
          return (
            <g key={`w-${i}`}>
              {pocheBands(wall.points, s.thickness, view.fx, view.fy).map((pts, j) => (
                <polygon key={j} className="poche-band" points={pts} fill={`var(${s.fill})`} vectorEffect="non-scaling-stroke" />
              ))}
            </g>
          );
        })}

        {/* user-dropped room markers (seeds) — pinned on top */}
        {markers?.map((m, i) => (
          <g key={`mk-${i}`} transform={`translate(${view.fx(m.x)} ${view.fy(m.y)})`}>
            <circle r={2.6} fill="var(--accent-soft)" stroke="var(--accent)" strokeWidth={0.6} vectorEffect="non-scaling-stroke" />
            <circle r={0.7} fill="var(--accent)" />
            <text className="marker-label" textAnchor="middle" y={-3.4}>{m.label}</text>
          </g>
        ))}
      </>
      )}
    />
  );
}
