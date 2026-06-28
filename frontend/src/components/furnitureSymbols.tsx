import type { ReactNode } from "react";
import type { FurnitureCategory } from "../types";

// Top-down plan SYMBOLS for furniture. Each builder draws in LOCAL coordinates
// (0..w by 0..h, SVG top-left origin — matches the translated <g> the caller places)
// and returns an SVG fragment of clean ink linework. Strokes are non-scaling so the
// drawing stays hairline-crisp at any zoom; fills are a light category tint applied by
// the caller around this fragment (line-drawing first, tint second).
//
// Convention inside each symbol: x grows right, y grows DOWN. For furniture the "back"
// edge (where a seat-back or monitor sits) is the +y/bottom edge after the caller's
// flip, but symbols are drawn self-consistently so they read correctly once rotated.

const STROKE = "var(--furn-line)";
const STROKE_FAINT = "var(--furn-line-faint)";

// shared hairline props for every drawn primitive
const line = { stroke: STROKE, vectorEffect: "non-scaling-stroke" as const, fill: "none" };

function chair(w: number, h: number): ReactNode {
  // seat square inset from the footprint + a back bar along the rear (top) edge
  const inset = Math.min(w, h) * 0.16;
  const backH = h * 0.18;
  return (
    <>
      <rect
        x={inset}
        y={inset + backH}
        width={w - inset * 2}
        height={h - inset * 2 - backH}
        rx={Math.min(w, h) * 0.12}
        {...line}
      />
      <rect x={inset} y={inset} width={w - inset * 2} height={backH} rx={backH * 0.4} {...line} />
    </>
  );
}

function desk(w: number, h: number): ReactNode {
  // desk slab + a small monitor on the back (top) edge + a chair tucked at the front
  const monW = w * 0.34;
  const monH = h * 0.12;
  const chairW = w * 0.34;
  const chairH = h * 0.28;
  return (
    <>
      <rect x={0} y={0} width={w} height={h * 0.62} {...line} />
      <rect x={(w - monW) / 2} y={0} width={monW} height={monH} {...line} />
      <rect
        x={(w - chairW) / 2}
        y={h - chairH}
        width={chairW}
        height={chairH}
        rx={Math.min(w, h) * 0.1}
        {...line}
      />
    </>
  );
}

function table(w: number, h: number): ReactNode {
  // rounded table outline + chair marks (short bars) along each long edge
  const r = Math.min(w, h) * 0.14;
  const seats = Math.max(1, Math.round(w / 2.6));
  const seatW = w / (seats + 1);
  const markH = h * 0.12;
  const markW = seatW * 0.5;
  const marks: ReactNode[] = [];
  for (let i = 1; i <= seats; i++) {
    const cx = seatW * i;
    marks.push(
      <rect key={`t-${i}`} x={cx - markW / 2} y={-markH * 1.3} width={markW} height={markH} rx={markH * 0.4} {...line} />,
      <rect key={`b-${i}`} x={cx - markW / 2} y={h + markH * 0.3} width={markW} height={markH} rx={markH * 0.4} {...line} />,
    );
  }
  return (
    <>
      <rect x={0} y={0} width={w} height={h} rx={r} {...line} />
      {marks}
    </>
  );
}

function sofa(w: number, h: number): ReactNode {
  // sofa outline + a thick back (top) + arms (sides) + seat-cushion divisions
  const back = h * 0.26;
  const arm = w * 0.12;
  const cushions = Math.max(1, Math.round((w - arm * 2) / 2.4));
  const seatW = (w - arm * 2) / cushions;
  const divs: ReactNode[] = [];
  for (let i = 1; i < cushions; i++) {
    const x = arm + seatW * i;
    divs.push(<line key={`c-${i}`} x1={x} y1={back} x2={x} y2={h} {...line} />);
  }
  return (
    <>
      <rect x={0} y={0} width={w} height={h} rx={Math.min(w, h) * 0.12} {...line} />
      <line x1={0} y1={back} x2={w} y2={back} {...line} />
      <line x1={arm} y1={back} x2={arm} y2={h} {...line} />
      <line x1={w - arm} y1={back} x2={w - arm} y2={h} {...line} />
      {divs}
    </>
  );
}

function stool(w: number, h: number): ReactNode {
  return <circle cx={w / 2} cy={h / 2} r={Math.min(w, h) / 2} {...line} />;
}

function tv(w: number, h: number): ReactNode {
  // thin screen rectangle on a short stand line (stand drops toward the wall behind)
  const screenH = Math.max(h * 0.4, Math.min(w, h) * 0.5);
  return (
    <>
      <rect x={0} y={0} width={w} height={screenH} {...line} />
      <line x1={w / 2} y1={screenH} x2={w / 2} y2={h} {...line} />
    </>
  );
}

function storage(w: number, h: number): ReactNode {
  // cabinet rectangle + a door swing arc from one front corner
  const reach = Math.min(w, h * 1.6);
  return (
    <>
      <rect x={0} y={0} width={w} height={h} {...line} />
      <path d={`M 0 ${h} L ${reach} ${h}`} {...line} />
      <path d={`M ${reach} ${h} A ${reach} ${reach} 0 0 0 0 ${h - reach}`} stroke={STROKE_FAINT} vectorEffect="non-scaling-stroke" fill="none" />
    </>
  );
}

function planter(w: number, h: number): ReactNode {
  const cx = w / 2;
  const cy = h / 2;
  const r = Math.min(w, h) / 2;
  return (
    <>
      <circle cx={cx} cy={cy} r={r} {...line} />
      <circle cx={cx} cy={cy} r={r * 0.45} stroke={STROKE_FAINT} vectorEffect="non-scaling-stroke" fill="none" />
    </>
  );
}

function panel(w: number, h: number): ReactNode {
  // glass partition: a faint thin line spanning the long axis with end ticks
  const horizontal = w >= h;
  const tick = Math.min(w, h) * 1.4;
  const faint = { stroke: STROKE_FAINT, vectorEffect: "non-scaling-stroke" as const, fill: "none" };
  if (horizontal) {
    const y = h / 2;
    return (
      <>
        <line x1={0} y1={y} x2={w} y2={y} {...faint} />
        <line x1={0} y1={y - tick / 2} x2={0} y2={y + tick / 2} {...faint} />
        <line x1={w} y1={y - tick / 2} x2={w} y2={y + tick / 2} {...faint} />
      </>
    );
  }
  const x = w / 2;
  return (
    <>
      <line x1={x} y1={0} x2={x} y2={h} {...faint} />
      <line x1={x - tick / 2} y1={0} x2={x + tick / 2} y2={0} {...faint} />
      <line x1={x - tick / 2} y1={h} x2={x + tick / 2} y2={h} {...faint} />
    </>
  );
}

function other(w: number, h: number): ReactNode {
  return <rect x={0} y={0} width={w} height={h} rx={Math.min(w, h) * 0.08} {...line} />;
}

const BUILDERS: Record<FurnitureCategory, (w: number, h: number) => ReactNode> = {
  chair,
  desk,
  workstation: desk,
  table,
  sofa,
  stool,
  tv,
  storage,
  planter,
  panel,
  mullion: panel,
  other,
};

// Build the plan symbol for a category at the given footprint (feet). Returns an SVG
// fragment in local 0..w / 0..h coordinates — the caller wraps it in a positioned,
// rotated, tinted <g>.
export function furnitureSymbol(category: FurnitureCategory, w: number, h: number): ReactNode {
  return (BUILDERS[category] ?? other)(w, h);
}
