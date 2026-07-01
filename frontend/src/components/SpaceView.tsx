import { useEffect, useMemo, useRef, useState } from "react";

import { fetchGeometry, renderView, type SymbolGeometry } from "../api";
import type { ExtractedLayout, ExtractedRoom, Instance, Plan } from "../types";

type Geo = Record<string, SymbolGeometry>;

/* Axonometric "paper model" — a pure-SVG 2.5D view. No WebGL, so it can never lose its context or
   fail to compile; it renders instantly and reads like the ink-on-paper 2D plan. Walls + furniture
   are extruded into an isometric projection with directional shading, contact shadows, glass on
   meeting rooms, faint zone tints, and a near-wall cutaway, painted back-to-front. */

type Pt = [number, number];
type RGB = [number, number, number];

// ── warm paper/ink palette ──
// NOTE: numeric RGB tuples the isometric shader lightens/darkens (can't do that math on a CSS var
// at draw time). PAPER/INK mirror tokens.css --paper/--ink; the tints are derived from --paper-3 /
// --line / --furn-*. Keep in sync with tokens.css (unifies with the 2D render path in Phase D).
const PAPER = "#f4f1ea";
const FLOOR: RGB = [232, 225, 211];
const WALL: RGB = [225, 217, 201];
const FURN_SEAT: RGB = [201, 169, 139]; // seating leans ~12% toward the terracotta accent
const FURN_SURF: RGB = [217, 204, 180]; // tables / desks / casework
const INK = "#1a1813";
const EDGE = "rgba(26,24,19,0.32)";
const GLASS = "rgba(150,171,186,0.34)"; // meeting-room glazing
const GLASS_EDGE = "rgba(120,140,158,0.7)";

const WALL_H = 8.5; // ft — perimeter
const PARTITION_H = 4.5; // ft — interior room walls, low (dollhouse) so furniture stays visible
const GLASS_H = 6.5; // ft — meeting-room glazing, a bit taller
const DESK_H = 2.5; // ft — a generated workstation desk
const DOOR_W = 3.3; // ft — clear doorway opening
const HEIGHTS: Record<string, number> = {
  chair: 2.9, stool: 2.7, desk: 2.5, table: 2.5, workstation: 3.4, sofa: 2.7,
  storage: 4.2, panel: 5.2, mullion: 8.5, tv: 4.4, planter: 2.6, other: 2.5,
};
const SEATING = new Set(["chair", "stool", "sofa"]);
const furnTone = (cat?: string): RGB => (cat && SEATING.has(cat) ? FURN_SEAT : FURN_SURF);

// faint floor tint per zone, keyed by a loose type match (null = no tint)
function zoneTint(type: string): RGB | null {
  const t = type.toLowerCase();
  if (/meet|conf|board|huddle/.test(t)) return [226, 223, 216];
  if (/office|cabin|exec|focus/.test(t)) return [235, 229, 217];
  if (/collab|lounge|cafe|break/.test(t)) return [237, 228, 212];
  return null;
}

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
  return placeShape([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], x, y, w, h, rotDeg);
}

// a per-category footprint (chairs/stools rounded, sofas softly chamfered, surfaces rectangular)
function shapeFoot(cat: string, x: number, y: number, w: number, h: number, rotDeg: number): Pt[] {
  const r = cat === "chair" || cat === "stool" ? 0.34 : cat === "sofa" || cat === "planter" ? 0.18 : 0;
  if (r === 0) return rectCorners(x, y, w, h, rotDeg);
  const c = r; // chamfer as a fraction of the half-extent
  const local: Pt[] = [
    [-0.5 + c, -0.5], [0.5 - c, -0.5], [0.5, -0.5 + c], [0.5, 0.5 - c],
    [0.5 - c, 0.5], [-0.5 + c, 0.5], [-0.5, 0.5 - c], [-0.5, -0.5 + c],
  ];
  return placeShape(local, x, y, w, h, rotDeg);
}

// map unit-square-centred local points to world, scaled to w×h, rotated, anchored at (x,y) min-corner
function placeShape(local: Pt[], x: number, y: number, w: number, h: number, rotDeg: number): Pt[] {
  const cx = x + w / 2;
  const cy = y + h / 2;
  const a = (rotDeg * Math.PI) / 180;
  const ca = Math.cos(a);
  const sa = Math.sin(a);
  return local.map(([lx, ly]) => {
    const dx = lx * w;
    const dy = ly * h;
    return [cx + dx * ca - dy * sa, cy + dx * sa + dy * ca] as Pt;
  });
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
  if (area(best) < 0.2) return null;
  return { foot: best, detail: rings.filter((r) => r !== best) };
}

// place a product's real geometry (rings re-based to a [0..w]×[0..h] box) at a slotted piece:
// centre on the piece, rotate to its orientation.
function placedOutline(g: SymbolGeometry, cx: number, cy: number, rotDeg: number): Pt[][] {
  const a = (rotDeg * Math.PI) / 180;
  const ca = Math.cos(a);
  const sa = Math.sin(a);
  return g.outline.map((ring) =>
    ring.map(([x, y]) => {
      const lx = x - g.w / 2;
      const ly = y - g.h / 2;
      return [cx + lx * ca - ly * sa, cy + lx * sa + ly * ca] as Pt;
    }),
  );
}

// a door symbol on the floor: quarter-circle swing (closed tip → open tip) hinged at `hinge`,
// radius `g`, swept from the in-edge direction `d` toward the into-room normal `n`, then the
// leaf line back to the hinge. One ink polyline at z=0; the caller spins + projects it.
function swingPath(hinge: Pt, d: Pt, n: Pt, g: number): Pt[] {
  const STEPS = 10;
  const path: Pt[] = [];
  for (let s = 0; s <= STEPS; s++) {
    const phi = (Math.PI / 2) * (s / STEPS);
    const c = Math.cos(phi);
    const si = Math.sin(phi);
    path.push([hinge[0] + g * (d[0] * c + n[0] * si), hinge[1] + g * (d[1] * c + n[1] * si)]);
  }
  path.push(hinge); // leaf: open tip → hinge
  return path;
}

// ── scene assembly ──
type Item = { foot: Pt[]; z1: number; base: RGB; detail?: Pt[][] };
type Wall = { a: Pt; b: Pt; h: number; glass?: boolean; cut?: boolean };
type Zone = { poly: Pt[]; tint: RGB };
type Scene = { floor: Pt[]; zones: Zone[]; walls: Wall[]; items: Item[]; doors: Pt[][]; center: Pt };

function sceneFromLayout(layout: ExtractedLayout): Scene {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const center: Pt = [(minx + maxx) / 2, (miny + maxy) / 2];
  const floor: Pt[] = [[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy]];

  const walls = layout.walls.flatMap((w) => {
    const peri = w.type === "perimeter" || w.type === "core";
    const glass = w.type === "glass";
    const h = peri ? WALL_H : glass ? GLASS_H : PARTITION_H;
    const segs: Wall[] = [];
    for (let i = 0; i + 1 < w.points.length; i++)
      segs.push({ a: w.points[i], b: w.points[i + 1], h, glass, cut: peri });
    return segs;
  });

  const zones: Zone[] = (layout.rooms ?? [])
    .map((r: ExtractedRoom) => ({ poly: r.polygon as Pt[], tint: zoneTint(r.type) }))
    .filter((z): z is Zone => z.tint !== null && z.poly.length >= 3);

  const items: Item[] = layout.furniture
    .filter((f) => f.category !== "mullion" && f.category !== "panel")
    .map((f) => {
      const sil = f.outline?.length ? silhouette(f.outline as Pt[][]) : null;
      return {
        foot: sil ? sil.foot : shapeFoot(f.category, f.x, f.y, f.w, f.h, f.rotation),
        z1: HEIGHTS[f.category] ?? HEIGHTS.other,
        base: furnTone(f.category),
        detail: sil?.detail.length ? sil.detail : undefined,
      };
    });

  // CAD walls already carry the opening; add a swing arc + leaf so each door reads as enterable
  const doors: Pt[][] = (layout.doors ?? []).map((dr) => {
    const a = (dr.rotation * Math.PI) / 180;
    const d: Pt = [Math.cos(a), Math.sin(a)];
    const n: Pt = [-d[1], d[0]];
    return swingPath([dr.x, dr.y], d, n, dr.width);
  });

  return { floor, zones, walls, items, doors, center };
}

const ENCLOSED = new Set(["private_office", "meeting_room", "collaboration"]);

function sceneFromPlan(plan: Plan, instances: Instance[], geo: Geo): Scene {
  const xs = plan.boundary.map((p) => p[0]);
  const ys = plan.boundary.map((p) => p[1]);
  const center: Pt = [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2];

  const walls: Wall[] = [];
  for (let i = 0; i < plan.boundary.length; i++)
    walls.push({ a: plan.boundary[i] as Pt, b: plan.boundary[(i + 1) % plan.boundary.length] as Pt, h: WALL_H, cut: true });

  const zones: Zone[] = [];
  const items: Item[] = [];
  const doors: Pt[][] = [];
  for (const i of instances) {
    if (i.slotted) {
      // use the SKU's real plan silhouette once fetched, else a per-category footprint
      const g = i.model ? geo[i.model] : undefined;
      const sil = g?.outline?.length
        ? silhouette(placedOutline(g, i.x + i.w / 2, i.y + i.h / 2, i.rotation))
        : null;
      items.push({
        foot: sil ? sil.foot : shapeFoot(i.type, i.x, i.y, i.w, i.h, i.rotation),
        z1: HEIGHTS[i.type] ?? HEIGHTS.other,
        base: furnTone(i.type),
        detail: sil?.detail.length ? sil.detail : undefined,
      });
      continue;
    }
    const corners = rectCorners(i.x, i.y, i.w, i.h, i.rotation);
    if (ENCLOSED.has(i.type)) {
      const glass = i.type === "meeting_room" || i.type === "private_office"; // modern glass fronts
      const wallH = glass ? GLASS_H : PARTITION_H;
      const roomCenter: Pt = [i.x + i.w / 2, i.y + i.h / 2];
      // the doorway is the edge whose midpoint sits nearest the plan centre — the most-visible,
      // interior-facing side
      let door = 0;
      let bestD = Infinity;
      for (let k = 0; k < corners.length; k++) {
        const a = corners[k];
        const b = corners[(k + 1) % corners.length];
        const dd = ((a[0] + b[0]) / 2 - center[0]) ** 2 + ((a[1] + b[1]) / 2 - center[1]) ** 2;
        if (dd < bestD) {
          bestD = dd;
          door = k;
        }
      }
      for (let k = 0; k < corners.length; k++) {
        const a = corners[k];
        const b = corners[(k + 1) % corners.length];
        if (k !== door) {
          walls.push({ a, b, h: wallH, glass });
          continue;
        }
        // leave a centred gap; emit the two flanking wall segments and a swing into the room
        const ex = b[0] - a[0];
        const ey = b[1] - a[1];
        const len = Math.hypot(ex, ey) || 1;
        const d: Pt = [ex / len, ey / len];
        let n: Pt = [-d[1], d[0]];
        if ((roomCenter[0] - (a[0] + b[0]) / 2) * n[0] + (roomCenter[1] - (a[1] + b[1]) / 2) * n[1] < 0)
          n = [-n[0], -n[1]];
        const g = Math.min(DOOR_W, len * 0.8);
        const mx = (a[0] + b[0]) / 2;
        const my = (a[1] + b[1]) / 2;
        const h1: Pt = [mx - d[0] * (g / 2), my - d[1] * (g / 2)];
        const h2: Pt = [mx + d[0] * (g / 2), my + d[1] * (g / 2)];
        walls.push({ a, b: h1, h: wallH, glass });
        walls.push({ a: h2, b, h: wallH, glass });
        doors.push(swingPath(h1, d, n, g));
      }
      const tint = zoneTint(i.type);
      if (tint) zones.push({ poly: corners, tint });
    } else {
      items.push({ foot: corners, z1: DESK_H, base: FURN_SURF }); // a workstation desk
    }
  }

  return { floor: plan.boundary as Pt[], zones, walls, items, doors, center };
}

// ── projection + shading into paint-ready faces ──
type Face = { pts: Pt[]; fill: string; stroke?: string; depth: number; order: number; lines?: Pt[][]; glass?: boolean };

function buildFaces(scene: Scene, q: number) {
  const { center } = scene;
  const faces: Face[] = [];
  const shadows: Pt[][] = [];
  const centerDepth = center[0] + center[1];

  const sideShade = (a: Pt, b: Pt) => {
    let n: Pt = [b[1] - a[1], -(b[0] - a[0])];
    const m = Math.hypot(n[0], n[1]) || 1;
    n = [n[0] / m, n[1] / m];
    return 0.82 + 0.16 * Math.max(0, n[0] * LIGHT[0] + n[1] * LIGHT[1]);
  };

  for (const w of scene.walls) {
    const sa = spin(w.a, center, q);
    const sb = spin(w.b, center, q);
    // cutaway: drop the tall perimeter walls on the near (viewer-facing) side so you see the floor
    if (w.cut && (sa[0] + sa[1] + sb[0] + sb[1]) / 2 > centerDepth + 0.5) continue;
    faces.push({
      pts: [iso(sa[0], sa[1], 0), iso(sb[0], sb[1], 0), iso(sb[0], sb[1], w.h), iso(sa[0], sa[1], w.h)],
      fill: w.glass ? GLASS : shade(WALL, sideShade(sa, sb)),
      stroke: w.glass ? GLASS_EDGE : undefined,
      depth: depthOf([sa, sb]),
      order: 0,
      glass: w.glass,
    });
  }

  for (const it of scene.items) {
    const spun = it.foot.map((p) => spin(p, center, q));
    const d = depthOf(spun);
    shadows.push(spun.map((p) => iso(p[0] + 0.5, p[1] + 0.5, 0)));
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
  const zones = scene.zones.map((z) => ({ pts: z.poly.map((p) => iso(...(spin(p, center, q) as Pt), 0)), fill: shade(z.tint, 1) }));
  const floorLines = scene.doors.map((poly) => poly.map((p) => iso(...(spin(p, center, q) as Pt), 0)));
  return { faces, floor, zones, shadows, floorLines };
}

const ptsStr = (pts: Pt[]) => pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");

export default function SpaceView(props: { layout: ExtractedLayout } | { plan: Plan; instances: Instance[] }) {
  const [q, setQ] = useState(0);
  const [render, setRender] = useState<null | { busy: boolean; img: string | null; err: string | null }>(null);
  const [geo, setGeo] = useState<Geo>({});
  const svgRef = useRef<SVGSVGElement | null>(null);

  // generate path: fetch each slotted SKU's real geometry once so its true shape replaces the
  // procedural footprint (the read path already carries outlines).
  const slottedSkus = "instances" in props
    ? [...new Set(props.instances.filter((i) => i.slotted && i.model).map((i) => i.model as string))].sort().join(",")
    : "";
  useEffect(() => {
    if (!slottedSkus) return;
    let live = true;
    Promise.all(
      slottedSkus.split(",").map(async (sku): Promise<[string, SymbolGeometry] | null> => {
        try {
          const g = await fetchGeometry(sku);
          return g.outline?.length ? [sku, g] : null;
        } catch {
          return null;
        }
      }),
    ).then((rs) => {
      if (live) setGeo(Object.fromEntries(rs.filter((r): r is [string, SymbolGeometry] => r !== null)));
    });
    return () => {
      live = false;
    };
  }, [slottedSkus]);

  const scene = useMemo(
    () => ("layout" in props ? sceneFromLayout(props.layout) : sceneFromPlan(props.plan, props.instances, geo)),
    [props, geo],
  );
  const { faces, floor, zones, shadows, floorLines } = useMemo(() => buildFaces(scene, q), [scene, q]);

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
        <defs>
          <linearGradient id="axon-floor" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={shade(FLOOR, 0.9)} />
            <stop offset="1" stopColor={shade(FLOOR, 1.05)} />
          </linearGradient>
        </defs>
        <polygon points={ptsStr(floor)} fill="url(#axon-floor)" stroke="rgba(26,24,19,0.18)" strokeWidth={0.4} />
        {zones.map((z, i) => (
          <polygon key={`z${i}`} points={ptsStr(z.pts)} fill={z.fill} />
        ))}
        {shadows.map((s, i) => (
          <polygon key={`sh${i}`} points={ptsStr(s)} fill="rgba(26,24,19,0.10)" />
        ))}
        {floorLines.map((line, i) => (
          <polyline key={`d${i}`} points={ptsStr(line)} fill="none" stroke={INK} strokeWidth={0.3}
            strokeLinejoin="round" strokeLinecap="round" opacity={0.5} />
        ))}
        {faces.map((f, i) => (
          <g key={i}>
            <polygon points={ptsStr(f.pts)} fill={f.fill} stroke={f.stroke ?? "none"}
              strokeWidth={f.glass ? 0.5 : 0.35} strokeLinejoin="round" />
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
              <span style={{ color: "var(--accent)" }} className="ds-eyebrow">
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
