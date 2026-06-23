import { useMemo } from "react";
import type { Instance, InstanceType, Plan } from "../types";

interface Props {
  plan: Plan;
  instances: Instance[];
}

// fill / stroke per instance type — restrained, ink + a single terracotta accent
const STYLE: Record<InstanceType, { fill: string; stroke: string; dash?: string }> = {
  workstation: { fill: "rgba(184,85,47,0.11)", stroke: "rgba(184,85,47,0.5)" },
  private_office: { fill: "rgba(26,24,19,0.045)", stroke: "rgba(26,24,19,0.34)" },
  meeting_room: { fill: "rgba(26,24,19,0.07)", stroke: "rgba(26,24,19,0.4)" },
  collaboration: { fill: "rgba(184,85,47,0.05)", stroke: "rgba(184,85,47,0.34)", dash: "3 3" },
};

const PAD = 8; // feet of margin around the plate

export default function PlanCanvas({ plan, instances }: Props) {
  const view = useMemo(() => {
    const xs = plan.boundary.map((p) => p[0]);
    const ys = plan.boundary.map((p) => p[1]);
    const minX = Math.min(...xs) - PAD;
    const maxX = Math.max(...xs) + PAD;
    const minY = Math.min(...ys) - PAD;
    const maxY = Math.max(...ys) + PAD;
    const w = maxX - minX;
    const h = maxY - minY;
    // flip Y so north is up; return mappers
    const fx = (x: number) => x - minX;
    const fy = (y: number) => maxY - y;
    return { w, h, fx, fy };
  }, [plan]);

  const poly = (pts: [number, number][]) =>
    pts.map(([x, y]) => `${view.fx(x).toFixed(2)},${view.fy(y).toFixed(2)}`).join(" ");

  return (
    <svg viewBox={`0 0 ${view.w} ${view.h}`} preserveAspectRatio="xMidYMid meet">
      {/* service core(s) */}
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

      {/* furniture / rooms */}
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

      {/* structural columns */}
      {plan.columns.map(([x, y], i) => (
        <circle
          key={`col-${i}`}
          cx={view.fx(x)}
          cy={view.fy(y)}
          r={0.9}
          fill="var(--ink)"
          opacity={0.55}
        />
      ))}

      {/* exterior boundary — drawn last, on top */}
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
