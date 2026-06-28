import { useMemo } from "react";
import type {
  ExtractedLayout,
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
};
type Props = FitProps | { layout: ExtractedLayout };

// Generated-fit instance presentation: which furniture SYMBOL stands in for each program
// type, whether the type reads as an ENCLOSED room (drawn with a room outline + small label),
// and the category tint. Unknown types fall back to an open low box.
// Program family → the quiet floor tint that distinguishes office / meeting / collaboration /
// amenity rooms within the warm-paper palette. Shared by both renderers (FitPlan carries the
// family explicitly; LayoutPlan infers it from the room label via roomFamilyFill).
type RoomFamily = "office" | "meeting" | "collab" | "amenity";
const FAMILY_FILL: Record<RoomFamily, string> = {
  office: "--room-office",
  meeting: "--room-meeting",
  collab: "--room-collab",
  amenity: "--room-amenity",
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

// Stable identity for a placed instance — used to pin/unpin rooms across regenerations.
export const instanceKey = (it: Instance): string =>
  `${it.type}:${it.x.toFixed(2)}:${it.y.toFixed(2)}`;

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

export default function PlanCanvas(props: Props) {
  if ("layout" in props) return <LayoutPlan layout={props.layout} />;
  return <FitPlan {...props} />;
}

/* ── generated-fit plan ──
   Drawn to read like LayoutPlan: the building edge and each enclosed room are SOLID poché
   walls (reusing pocheBands), open furniture is hairline ink contained in its footprint, and
   every enclosed room is inset + clipped so no chair mark ever crosses a wall. Enclosed rooms
   stay pinnable for the iterate loop. */
function FitPlan({ plan, instances, pinnedKeys, onTogglePin }: FitProps) {
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
    <svg viewBox={`0 0 ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet">
      <PlanDefs />
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
        const kind = FIT[it.type] ?? FIT_FALLBACK;
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
            className="fit-room--pinnable"
            role={pinnable ? "button" : undefined}
            tabIndex={pinnable ? 0 : undefined}
            aria-pressed={pinnable ? pinned : undefined}
            aria-label={pinnable ? `${pinned ? "Unpin" : "Pin"} ${kind.room}` : undefined}
            onClick={pin}
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
            {/* floor fill — subtle program-family tint, accent-soft when pinned */}
            <rect
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

      <SheetFurniture view={view} span={maxX - minX} title="TEST-FIT" kind="SPACE PLAN" />
    </svg>
  );
}

/* ── real extracted-layout plan ── */
function LayoutPlan({ layout }: { layout: ExtractedLayout }) {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const view = useView(minx, miny, maxx, maxy);
  const usedTypes = useMemo(
    () => new Set(layout.walls.map((w) => w.type)),
    [layout.walls],
  );

  const polyline = (pts: [number, number][]) =>
    pts.map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ");

  return (
    <div className="layout-plan">
      <svg viewBox={`0 0 ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet">
        <PlanDefs />
        {/* rooms — faint filled polygons (where the walls close) with the label + area placed at
            the room's anchor, so every read room shows on the plan even without a closed boundary */}
        {layout.rooms.map((r) => {
          const cx = r.center ? view.fx(r.center[0]) : null;
          const cy = r.center ? view.fy(r.center[1]) : null;
          return (
            <g key={`room-${r.id}`}>
              {r.polygon.length >= 3 && (
                <>
                  {/* soft lift — opaque paper caster (invisible against the sheet) carries the shadow */}
                  <polygon points={polyline(r.polygon)} fill="var(--paper)" filter="url(#plan-lift)" />
                  <polygon
                    points={polyline(r.polygon)}
                    fill={`var(${r.label ? roomFamilyFill(r.label) : "--room-fill"})`}
                    stroke="var(--room-line)"
                    strokeWidth={1}
                    vectorEffect="non-scaling-stroke"
                  />
                </>
              )}
              {r.label && cx != null && cy != null && (
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

        {/* furniture — recognizable top-down plan symbols, line-drawing first with a soft
            category tint. Each symbol is drawn in local 0..w / 0..h coords inside a <g> that
            translates to the footprint's top-left corner (world min-x / max-y) and rotates about
            the centre. Mullions are drawn by the glass panels, not as separate footprints. */}
        {layout.furniture.filter((f) => f.category !== "mullion").map((f, i) => {
          const ox = view.fx(f.x);
          const oy = view.fy(f.y + f.h);
          const cx = view.fx(f.x + f.w / 2);
          const cy = view.fy(f.y + f.h / 2);
          const tint = `var(${FURN[f.category] ?? "--furn-other"})`;
          return (
            <g
              key={`f-${i}`}
              transform={`translate(${ox} ${oy}) rotate(${-f.rotation} ${cx - ox} ${cy - oy})`}
              fill={tint}
              fillOpacity={0.14}
            >
              <title>{`${f.category}${f.brand ? ` · ${f.brand}` : ""}${f.model ? ` ${f.model}` : ""}`}</title>
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

        <SheetFurniture view={view} span={maxx - minx} title={sheetName(layout.source)} kind="EXTRACTED LAYOUT" />
      </svg>

      {/* wall-type legend — only the types actually present */}
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
    </div>
  );
}
