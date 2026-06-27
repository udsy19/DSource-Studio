import { useMemo } from "react";
import type {
  ExtractedLayout,
  FurnitureCategory,
  Instance,
  InstanceType,
  Plan,
  WallType,
} from "../types";

// Two modes: the generated fit (plan + instances) and the user's REAL extracted layout.
type Props = { plan: Plan; instances: Instance[] } | { layout: ExtractedLayout };

// fill / stroke per instance type — restrained, ink + a single terracotta accent
const STYLE: Record<InstanceType, { fill: string; stroke: string; dash?: string }> = {
  workstation: { fill: "rgba(184,85,47,0.11)", stroke: "rgba(184,85,47,0.5)" },
  private_office: { fill: "rgba(26,24,19,0.045)", stroke: "rgba(26,24,19,0.34)" },
  meeting_room: { fill: "rgba(26,24,19,0.07)", stroke: "rgba(26,24,19,0.4)" },
  collaboration: { fill: "rgba(184,85,47,0.05)", stroke: "rgba(184,85,47,0.34)", dash: "3 3" },
};

// wall colour token + human label per type (drives both the plan strokes and the legend)
const WALL: Record<WallType, { token: string; label: string; width: number; dash?: string }> = {
  perimeter: { token: "--wall-perimeter", label: "Perimeter", width: 2 },
  core: { token: "--wall-core", label: "Core", width: 2 },
  drywall: { token: "--wall-drywall", label: "Drywall", width: 1.6 },
  half_drywall: { token: "--wall-half-drywall", label: "Half-drywall", width: 1.4, dash: "4 2" },
  glass: { token: "--wall-glass", label: "Glass", width: 1.4, dash: "1 2" },
  door: { token: "--wall-door", label: "Door", width: 1.6 },
  unknown: { token: "--wall-unknown", label: "Other", width: 1.2, dash: "2 3" },
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
        {/* rooms — faint filled polygons with label + area */}
        {layout.rooms.map((r) => {
          const cx = r.polygon.reduce((s, p) => s + view.fx(p[0]), 0) / r.polygon.length;
          const cy = r.polygon.reduce((s, p) => s + view.fy(p[1]), 0) / r.polygon.length;
          return (
            <g key={`room-${r.id}`}>
              <polygon
                points={polyline(r.polygon)}
                fill="var(--room-fill)"
                stroke="var(--room-line)"
                strokeWidth={1}
                vectorEffect="non-scaling-stroke"
              />
              {r.label && (
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

        {/* furniture footprints — rect at (x,y) by (w,h), rotated about its centre.
            Mullions (glazing framing) are drawn by the glass panels, not as separate footprints. */}
        {layout.furniture.filter((f) => f.category !== "mullion").map((f, i) => {
          const cx = view.fx(f.x + f.w / 2);
          const cy = view.fy(f.y + f.h / 2);
          const color = `var(${FURN[f.category] ?? "--furn-other"})`;
          return (
            <rect
              key={`f-${i}`}
              x={view.fx(f.x)}
              y={view.fy(f.y + f.h)}
              width={f.w}
              height={f.h}
              fill={color}
              fillOpacity={0.16}
              stroke={color}
              strokeOpacity={0.7}
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
              rx={0.3}
              transform={`rotate(${-f.rotation} ${cx} ${cy})`}
            >
              <title>{`${f.category}${f.brand ? ` · ${f.brand}` : ""}${f.model ? ` ${f.model}` : ""}`}</title>
            </rect>
          );
        })}

        {/* doors — accent marker on the threshold */}
        {layout.doors.map((d, i) => (
          <rect
            key={`d-${i}`}
            x={view.fx(d.x) - d.width / 2}
            y={view.fy(d.y) - 0.3}
            width={d.width}
            height={0.6}
            fill="var(--wall-door)"
            transform={`rotate(${-d.rotation} ${view.fx(d.x)} ${view.fy(d.y)})`}
          />
        ))}

        {/* walls — coloured by type, drawn last on top */}
        {layout.walls.map((wall, i) => {
          const s = WALL[wall.type] ?? WALL.unknown;
          return (
            <polyline
              key={`w-${i}`}
              points={polyline(wall.points)}
              fill="none"
              stroke={`var(${s.token})`}
              strokeWidth={s.width}
              strokeDasharray={s.dash}
              strokeLinejoin="round"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          );
        })}
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
