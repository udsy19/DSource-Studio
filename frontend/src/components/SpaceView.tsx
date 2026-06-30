import { useMemo, useRef, useState } from "react";

import { renderView } from "../api";
import type { ExtractedLayout, Instance, Plan } from "../types";

/* Axonometric "paper model" — a pure-SVG 2.5D view. No WebGL, so it can never lose its context or
   fail to compile; it renders instantly and reads like the ink-on-paper 2D plan. Walls and furniture
   are extruded into an isometric projection with directional shading + contact shadows, painted
   back-to-front. Each furniture piece is extruded from its REAL plan silhouette, not a box. */

type Pt = [number, number];
type RGB = [number, number, number];

// ── warm paper/ink palette (single terracotta accent kept for the UI, not the model) ──
const PAPER = "#f4f1ea";
const FLOOR: RGB = [232, 225, 211];
const WALL: RGB = [225, 217, 201];
const FURN: RGB = [214, 201, 176];
const ROOM_RGB: Record<string, RGB> = {
  workstation: [223, 214, 195], private_office: [219, 209, 188],
  meeting_room: [222, 211, 188], collaboration: [228, 218, 198],
};
const INK = "#1a1813";
const EDGE = "rgba(26,24,19,0.35)";

const WALL_H = 8.5; // ft
const HEIGHTS: Record<string, number> = {
  chair: 2.9, stool: 2.7, desk: 2.5, table: 2.5, workstation: 3.4, sofa: 2.7,
  storage: 4.2, panel: 5.2, mullion: 8.5, tv: 4.4, planter: 2.6, other: 2.5,
  private_office: 0.5, meeting_room: 0.5, collaboration: 0.5,
};

const ISO = Math.PI / 6;
const COS = Math.cos(ISO);
const SIN = Math.sin(ISO);
const LIGHT = ((): Pt => {
  const v: Pt = [-0.55, -0.8];
  const m = Math.hypot(v[0], v[1]);
  return [v[0] / m, v[1] / m];
})();

const iso = (x: number, y: number, z: number): Pt => [(x - y) * COS, (x + y) * SIN - z];
const depthOf = (poly: Pt[]) => poly.reduce((s, [x, y]) => s + x + y, 0) / poly.length;
const shade = ([r, g, b]: RGB, f: number) =>
  `rgb(${Math.min(255, Math.round(r * f))},${Math.min(255, Math.round(g * f))},${Math.min(255, Math.round(b * f))})`;

function spin(p: Pt, c: Pt, q: number): Pt {
  let [x, y] = [p[0] - c[0], p[1] - c[1]];
  for (let i = 0; i < ((q % 4) + 4) % 4; i++) [x, y] = [-y, x];
  return [x + c[0], y + c[1]];
}

function rectCorners(x: number, y: number, w: number, h: number, rotDeg: number): Pt[] {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const a = (rotDeg * Math.PI) / 180;
  const ca = Math.cos(a);
  const sa = Math.sin(a);
  return ([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]] as Pt[]).map(
    ([dx, dy]) => [cx + dx * ca - dy * sa, cy + dx * sa + dy * ca] as Pt,
  );
}

const area = (ring: Pt[]) => {
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++)
    a += (ring[j][0] + ring[i][0]) * (ring[j][1] - ring[i][1]);
  return Math.abs(a / 2);
};

// the real plan silhouette to extrude (largest-area ring), plus the finer rings to ink on top
function silhouette(outline: Pt[][]): { foot: Pt[]; detail: Pt[][] } | null {
  const rings = outline.filter((r) => r.length >= 3);
  if (!rings.length) return null;
  let best = rings[0];
  for (const r of rings) if (area(r) > area(best)) best = r;
  if (area(best) < 0.2) return null; // too thin to read as a footprint
  return { foot: best, detail: rings.filter((r) => r !== best) };
}

// ── scene assembly ──
type Item = { foot: Pt[]; z1: number; base: RGB; detail?: Pt[][] };
type Scene = { floor: Pt[]; walls: { a: Pt; b: Pt }[]; items: Item[]; center: Pt };

function sceneFromLayout(layout: ExtractedLayout): Scene {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const center: Pt = [(minx + maxx) / 2, (miny + maxy) / 2];
  const floor: Pt[] = [[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy]];

  const walls = layout.walls.flatMap((w) => {
    const segs: { a: Pt; b: Pt }[] = [];
    for (let i = 0; i + 1 < w.points.length; i++) segs.push({ a: w.points[i], b: w.points[i + 1] });
    return segs;
  });

  const items: Item[] = layout.furniture
    .filter((f) => f.category !== "mullion")
    .map((f) => {
      const sil = f.outline?.length ? silhouette(f.outline as Pt[][]) : null;
      return {
        foot: sil ? sil.foot : rectCorners(f.x, f.y, f.w, f.h, f.rotation),
        z1: HEIGHTS[f.category] ?? HEIGHTS.other,
        base: FURN,
        detail: sil?.detail.length ? sil.detail : undefined,
      };
    });

  return { floor, walls, items, center };
}

function sceneFromPlan(plan: Plan, instances: Instance[]): Scene {
  const xs = plan.boundary.map((p) => p[0]);
  const ys = plan.boundary.map((p) => p[1]);
  const center: Pt = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];
  const walls: { a: Pt; b: Pt }[] = [];
  for (let i = 0; i < plan.boundary.length; i++)
    walls.push({ a: plan.boundary[i] as Pt, b: plan.boundary[(i + 1) % plan.boundary.length] as Pt });

  const items: Item[] = instances.map((i) => ({
    foot: rectCorners(i.x, i.y, i.w, i.h, i.rotation),
    z1: HEIGHTS[i.type] ?? HEIGHTS.other,
    base: ROOM_RGB[i.type] ?? FURN,
  }));

  return { floor: plan.boundary as Pt[], walls, items, center };
}

// ── projection + shading into paint-ready faces ──
type Face = { pts: Pt[]; fill: string; stroke?: string; depth: number; order: number; lines?: Pt[][] };

function buildFaces(scene: Scene, q: number) {
  const { center } = scene;
  const faces: Face[] = [];
  const shadows: Pt[][] = [];

  // outward-normal shade factor for a vertical side face spanning world edge a→b
  const sideShade = (a: Pt, b: Pt) => {
    let n: Pt = [b[1] - a[1], -(b[0] - a[0])];
    const m = Math.hypot(n[0], n[1]) || 1;
    n = [n[0] / m, n[1] / m];
    return 0.82 + 0.16 * Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1]);
  };

  for (const { a, b } of scene.walls) {
    const sa = spin(a, center, q);
    const sb = spin(b, center, q);
    faces.push({
      pts: [iso(sa[0], sa[1], 0), iso(sb[0], sb[1], 0), iso(sb[0], sb[1], WALL_H), iso(sa[0], sa[1], WALL_H)],
      fill: shade(WALL, sideShade(sa, sb)),
      depth: depthOf([sa, sb]),
      order: 0,
    });
  }

  for (const it of scene.items) {
    const spun = it.foot.map((p) => spin(p, center, q));
    const d = depthOf(spun);
    // contact shadow: footprint dropped to the floor, nudged toward the light's far side
    shadows.push(spun.map((p) => iso(p[0] + 0.5, p[1] + 0.5, 0)));
    // side faces (only the two facing the viewer read), shaded by direction
    const sides = spun.map((p, i) => {
      const nx = spun[(i + 1) % spun.length];
      return {
        pts: [iso(p[0], p[1], 0), iso(nx[0], nx[1], 0), iso(nx[0], nx[1], it.z1), iso(p[0], p[1], it.z1)] as Pt[],
        depth: (p[0] + p[1] + nx[0] + nx[1]) / 2,
        fill: shade(it.base, sideShade(p, nx) - 0.06),
      };
    });
    sides.sort((x, y) => x.depth - y.depth);
    for (const f of sides.slice(-2)) faces.push({ pts: f.pts, fill: f.fill, depth: d, order: 1 });
    const top = spun.map((p) => iso(p[0], p[1], it.z1));
    const lines = it.detail?.map((ring) => ring.map((p) => iso(...(spin(p, center, q) as Pt), it.z1)));
    faces.push({ pts: top, fill: shade(it.base, 1.08), stroke: EDGE, depth: d, order: 2, lines });
  }

  faces.sort((a, b) => a.depth - b.depth || a.order - b.order);
  const floor = scene.floor.map((p) => iso(...(spin(p, center, q) as Pt), 0));
  return { faces, floor, shadows };
}

const ptsStr = (pts: Pt[]) => pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

export default function SpaceView(props: { layout: ExtractedLayout } | { plan: Plan; instances: Instance[] }) {
  const [q, setQ] = useState(0);
  const [render, setRender] = useState<null | { busy: boolean; img: string | null; err: string | null }>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const scene = useMemo(
    () => ("layout" in props ? sceneFromLayout(props.layout) : sceneFromPlan(props.plan, props.instances)),
    [props],
  );
  const { faces, floor, shadows } = useMemo(() => buildFaces(scene, q), [scene, q]);

  const all = [floor, ...faces.map((f) => f.pts)].flat();
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  const pad = 5;
  const vb = all.length
    ? `${Math.min(...xs) - pad} ${Math.min(...ys) - pad} ${Math.max(...xs) - Math.min(...xs) + pad * 2} ${Math.max(...ys) - Math.min(...ys) + pad * 2}`
    : "0 0 100 100";

  async function handleRender() {
    const svg = svgRef.current;
    if (!svg) return;
    setRender({ busy: true, img: null, err: null });
    try {
      const xml = new XMLSerializer().serializeToString(svg);
      const img = new Image();
      img.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(xml)));
      await img.decode();
      const W = 1100;
      const canvas = document.createElement("canvas");
      canvas.width = W;
      canvas.height = Math.round((W * svg.clientHeight) / Math.max(svg.clientWidth, 1)) || W;
      const ctx = canvas.getContext("2d")!;
      ctx.fillStyle = PAPER;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const shot = canvas.toDataURL("image/jpeg", 0.85);
      const r = await renderView(shot);
      setRender({ busy: false, img: r.image ?? shot, err: r.image ? null : "Provider returned no image." });
    } catch (e) {
      setRender({ busy: false, img: null, err: String(e instanceof Error ? e.message : e) });
    }
  }

  return (
    <div className="axon">
      <svg ref={svgRef} className="axon-svg" viewBox={vb} preserveAspectRatio="xMidYMid meet" role="img"
        aria-label="Axonometric model of the layout">
        <polygon points={ptsStr(floor)} fill={shade(FLOOR, 1)} stroke="rgba(26,24,19,0.18)" strokeWidth={0.4} />
        {shadows.map((s, i) => (
          <polygon key={`sh${i}`} points={ptsStr(s)} fill="rgba(26,24,19,0.10)" />
        ))}
        {faces.map((f, i) => (
          <g key={i}>
            <polygon points={ptsStr(f.pts)} fill={f.fill} stroke={f.stroke ?? "none"}
              strokeWidth={0.35} strokeLinejoin="round" />
            {f.lines?.map((ring, j) => (
              <polyline key={j} points={ptsStr(ring)} fill="none" stroke={INK} strokeWidth={0.3}
                strokeLinejoin="round" opacity={0.45} />
            ))}
          </g>
        ))}
      </svg>

      <div className="axon-tools">
        <button type="button" className="axon-rot" onClick={() => setQ((v) => v - 1)} aria-label="Rotate left">⟲</button>
        <span className="axon-hint">{["NE", "SE", "SW", "NW"][((q % 4) + 4) % 4]}</span>
        <button type="button" className="axon-rot" onClick={() => setQ((v) => v + 1)} aria-label="Rotate right">⟳</button>
        <button type="button" className="axon-render" onClick={handleRender}>Render</button>
      </div>

      {render && (
        <div className="render-overlay" onClick={() => setRender(null)}>
          <div className="render-card" onClick={(e) => e.stopPropagation()}>
            <div className="render-head">
              <span style={{ color: "#b8552f" }} className="ds-eyebrow">
                {render.busy ? "Rendering…" : render.err ? "Render unavailable" : "Photoreal render"}
              </span>
              <button type="button" className="link-btn" onClick={() => setRender(null)}>Close</button>
            </div>
            {render.img && <img src={render.img} alt="Photoreal render" className="render-img" />}
            {render.err && <p className="disclaim">{render.err}</p>}
          </div>
        </div>
      )}
    </div>
  );
}
