import { useMemo } from "react";
import type {
  ExtractedLayout,
  FurnitureCategory,
  Instance,
  InstanceType,
  Plan,
  WallType,
} from "../types";
import { furnitureSymbol } from "./furnitureSymbols";

// Two modes: the generated fit (plan + instances) and the user's REAL extracted layout.
type Props = { plan: Plan; instances: Instance[] } | { layout: ExtractedLayout };

// fill / stroke per instance type — restrained, ink + a single terracotta accent
const STYLE: Record<InstanceType, { fill: string; stroke: string; dash?: string }> = {
  workstation: { fill: "rgba(184,85,47,0.11)", stroke: "rgba(184,85,47,0.5)" },
  private_office: { fill: "rgba(26,24,19,0.045)", stroke: "rgba(26,24,19,0.34)" },
  meeting_room: { fill: "rgba(26,24,19,0.07)", stroke: "rgba(26,24,19,0.4)" },
  collaboration: { fill: "rgba(184,85,47,0.05)", stroke: "rgba(184,85,47,0.34)", dash: "3 3" },
};

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

export default function PlanCanvas(props: Props) {
  if ("layout" in props) return <LayoutPlan layout={props.layout} />;
  return <FitPlan plan={props.plan} instances={props.instances} />;
}

/* ── generated-fit plan (existing behaviour) ── */
function FitPlan({ plan, instances }: { plan: Plan; instances: Instance[] }) {
  const xs = plan.boundary.map((p) => p[0]);
  const ys = plan.boundary.map((p) => p[1]);
  const view = useView(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys));

  const poly = (pts: [number, number][]) =>
    pts.map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet">
      {plan.cores.map((c, i) => (
        <polygon
          key={`core-${i}`}
          points={poly(c)}
          fill="rgba(26,24,19,0.06)"
          stroke="rgba(26,24,19,0.22)"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
        />
      ))}

      {instances.map((it, i) => {
        const s = STYLE[it.type] ?? STYLE.workstation;
        return (
          <rect
            key={`i-${i}`}
            x={view.fx(it.x)}
            y={view.fy(it.y + it.h)}
            width={it.w}
            height={it.h}
            fill={s.fill}
            stroke={s.stroke}
            strokeWidth={1}
            strokeDasharray={s.dash}
            vectorEffect="non-scaling-stroke"
            rx={0.4}
          />
        );
      })}

      {plan.columns.map(([x, y], i) => (
        <circle key={`col-${i}`} cx={view.fx(x)} cy={view.fy(y)} r={0.9} fill="var(--ink)" opacity={0.55} />
      ))}

      <polygon
        className="draw"
        points={poly(plan.boundary)}
        fill="none"
        stroke="var(--ink)"
        strokeWidth={1.6}
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
      />
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
        {/* rooms — faint filled polygons (where the walls close) with the label + area placed at
            the room's anchor, so every read room shows on the plan even without a closed boundary */}
        {layout.rooms.map((r) => {
          const cx = r.center ? view.fx(r.center[0]) : null;
          const cy = r.center ? view.fy(r.center[1]) : null;
          return (
            <g key={`room-${r.id}`}>
              {r.polygon.length >= 3 && (
                <polygon
                  points={polyline(r.polygon)}
                  fill="var(--room-fill)"
                  stroke="var(--room-line)"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
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
                <polygon key={j} points={pts} fill={`var(${s.fill})`} />
              ))}
            </g>
          );
        })}

        {/* scale bar — a quiet ruled bar of round length in the bottom-right corner */}
        {(() => {
          const ft = niceScaleFeet(maxx - minx);
          const y = view.h - PAD * 0.55;
          const x1 = view.w - PAD - ft;
          const x2 = view.w - PAD;
          return (
            <g stroke="var(--scale-bar)" vectorEffect="non-scaling-stroke">
              <line x1={x1} y1={y} x2={x2} y2={y} vectorEffect="non-scaling-stroke" />
              <line x1={x1} y1={y - 0.6} x2={x1} y2={y + 0.6} vectorEffect="non-scaling-stroke" />
              <line x1={x2} y1={y - 0.6} x2={x2} y2={y + 0.6} vectorEffect="non-scaling-stroke" />
              <text className="scale-label" x={(x1 + x2) / 2} y={y - 1} textAnchor="middle">
                {ft} ft
              </text>
            </g>
          );
        })()}
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
