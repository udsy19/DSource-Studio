import { ContactShadows, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo, useState } from "react";
import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { renderView } from "../api";
import type { CadGeometry } from "../types";

const WALL_H = 9;        // ft — extrude wall layers up
const FURN_H = 2.45;     // ft — extrude closed furniture (desks/tables) up
const MAX_FURN = 7000;

export interface Mat {
  name: string;
  color: string;
  roughness: number;
}
// Real-material palettes (stand-ins for real India catalog products → SKU/vendor/price later).
export const FLOOR_MATS: Mat[] = [
  { name: "Carpet · Welspun", color: "#6f6e69", roughness: 0.96 },
  { name: "Oak LVT", color: "#b58a52", roughness: 0.55 },
  { name: "Concrete", color: "#c2beb6", roughness: 0.5 },
  { name: "Marble", color: "#e8e4dc", roughness: 0.28 },
];
export const WALL_MATS: Mat[] = [
  { name: "White", color: "#e9e3d7", roughness: 0.9 },
  { name: "Sage", color: "#9aa48b", roughness: 0.85 },
  { name: "Fluted Oak", color: "#b58a52", roughness: 0.6 },
  { name: "Charcoal", color: "#3c3a35", roughness: 0.8 },
];
export const FURN_MATS: Mat[] = [
  { name: "Walnut", color: "#6b4f34", roughness: 0.55 },
  { name: "Graphite", color: "#37352f", roughness: 0.5 },
  { name: "Oak", color: "#c0a16b", roughness: 0.55 },
  { name: "Bone", color: "#d9d2c4", roughness: 0.6 },
];

function polyArea(pts: [number, number][]): number {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x1, y1] = pts[i];
    const [x2, y2] = pts[(i + 1) % pts.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

/* ── 2D: the faithful CAD render (ezdxf SVG) ── */
export function CadSvg({ svg }: { svg: string }) {
  return <div className="cad-svg" dangerouslySetInnerHTML={{ __html: svg }} />;
}

/* ── 3D: walls + extruded furniture + the full furniture layout drawn on the floor ──
   lineMode renders a crisp black-on-white architectural line drawing of the EXACT same
   view — used as the ControlNet (Flux-Canny) control image so the photoreal output is
   forced to follow the real walls/desks instead of hallucinating a new room. ── */
function CadScene({ geo, lineMode = false }: { geo: CadGeometry; lineMode?: boolean }) {
  const b = geo.bounds!;
  const cx = (b.minx + b.maxx) / 2;
  const cy = (b.miny + b.maxy) / 2;
  const size = Math.max(b.maxx - b.minx, b.maxy - b.miny);
  const wx = (x: number) => x - cx;
  const wz = (y: number) => -(y - cy);

  // exterior + interior walls, extruded to WALL_H (merged quads -> one geometry)
  const wallGeo = useMemo(() => {
    const pos: number[] = [];
    for (const p of geo.paths) {
      if (!p.wall) continue;
      for (let i = 0; i < p.pts.length - 1; i++) {
        const [x1, y1] = p.pts[i];
        const [x2, y2] = p.pts[i + 1];
        const ax = wx(x1), az = wz(y1), bx = wx(x2), bz = wz(y2);
        pos.push(ax, 0, az, bx, 0, bz, bx, WALL_H, bz, ax, 0, az, bx, WALL_H, bz, ax, WALL_H, az);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    return g;
  }, [geo]);

  // closed furniture (desk/table tops) extruded to furniture height (merged -> one geometry)
  const furnSolid = useMemo(() => {
    const geos: THREE.BufferGeometry[] = [];
    let n = 0;
    for (const p of geo.paths) {
      if (p.wall || !p.closed || p.pts.length < 3) continue;
      const area = polyArea(p.pts);
      if (area < 2 || area > 120) continue;   // keep furniture-sized closed shapes only
      if (n++ > MAX_FURN) break;
      const shape = new THREE.Shape(p.pts.map(([x, y]) => new THREE.Vector2(wx(x), -wz(y))));
      try {
        geos.push(new THREE.ExtrudeGeometry(shape, { depth: FURN_H, bevelEnabled: false }));
      } catch {
        /* degenerate */
      }
    }
    if (!geos.length) return null;
    const merged = mergeGeometries(geos, false);
    merged.rotateX(-Math.PI / 2);   // extrude is +Z; stand it up so depth -> +Y
    merged.computeVertexNormals();
    return merged;
  }, [geo]);

  // ALL furniture outlines (open + closed) drawn flat on the floor (one LineSegments geometry)
  const furnLines = useMemo(() => {
    const pos: number[] = [];
    for (const p of geo.paths) {
      if (p.wall) continue;
      for (let i = 0; i < p.pts.length - 1; i++) {
        const [x1, y1] = p.pts[i];
        const [x2, y2] = p.pts[i + 1];
        pos.push(wx(x1), 0.06, wz(y1), wx(x2), 0.06, wz(y2));
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    return g;
  }, [geo]);

  // hard outlines for line-art control capture (crisp edges => faithful ControlNet)
  const wallEdges = useMemo(() => new THREE.EdgesGeometry(wallGeo, 12), [wallGeo]);
  const furnEdges = useMemo(() => (furnSolid ? new THREE.EdgesGeometry(furnSolid, 18) : null), [furnSolid]);

  const sun = size * 1.2;

  /* ── line-art pass: white world, black edges, no fog/shadow/AO ── */
  if (lineMode) {
    return (
      <>
        <color attach="background" args={["#ffffff"]} />
        <ambientLight intensity={1} />
        {/* white wall fills so Canny reads solid planes, with black outlines on top */}
        <mesh geometry={wallGeo}>
          <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1} />
        </mesh>
        <lineSegments geometry={wallEdges}>
          <lineBasicMaterial color="#000000" />
        </lineSegments>
        {furnSolid && (
          <mesh geometry={furnSolid}>
            <meshBasicMaterial color="#ffffff" />
          </mesh>
        )}
        {furnEdges && (
          <lineSegments geometry={furnEdges}>
            <lineBasicMaterial color="#111111" />
          </lineSegments>
        )}
        <lineSegments geometry={furnLines}>
          <lineBasicMaterial color="#111111" />
        </lineSegments>
        <OrbitControls makeDefault enablePan maxPolarAngle={Math.PI / 2.08} minDistance={size * 0.12} />
      </>
    );
  }

  return (
    <>
      <color attach="background" args={["#f1ece1"]} />
      <fog attach="fog" args={["#f1ece1", size * 1.4, size * 3.2]} />
      <ambientLight intensity={0.5} />
      <hemisphereLight args={["#fbf7ee", "#cfc4ad", 0.5]} />
      <directionalLight
        position={[sun, size * 1.7, sun * 0.7]}
        intensity={1.15}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-size} shadow-camera-right={size}
        shadow-camera-top={size} shadow-camera-bottom={-size}
        shadow-camera-near={1} shadow-camera-far={size * 4}
      />

      {/* floor */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.02, 0]} receiveShadow>
        <planeGeometry args={[size * 1.6, size * 1.6]} />
        <meshStandardMaterial color="#e7dfd0" roughness={0.97} />
      </mesh>

      {/* furniture layout drawn on the floor */}
      <lineSegments geometry={furnLines}>
        <lineBasicMaterial color="#6f6857" transparent opacity={0.7} />
      </lineSegments>

      {/* furniture volumes (desks/tables) */}
      {furnSolid && (
        <mesh geometry={furnSolid} castShadow receiveShadow>
          <meshStandardMaterial color="#9c7c4e" roughness={0.55} />
        </mesh>
      )}

      {/* walls */}
      <mesh geometry={wallGeo} castShadow receiveShadow>
        <meshStandardMaterial color="#d3cab7" roughness={0.85} side={THREE.DoubleSide} />
      </mesh>

      <ContactShadows position={[0, 0.0, 0]} scale={size * 1.7} blur={2.4} opacity={0.28} far={WALL_H} />
      <OrbitControls makeDefault enablePan maxPolarAngle={Math.PI / 2.08} minDistance={size * 0.12} />
    </>
  );
}

const RENDER_PROMPT =
  "Photorealistic architectural visualization of a modern Indian corporate office interior, " +
  "isometric cutaway view. Preserve EXACTLY the wall layout, room partitions, glass-fronted " +
  "cabins and the desk/workstation positions shown in the line drawing — do not add, remove, " +
  "or move any walls, rooms, or desks. Warm oak wood flooring in the open area, white plastered " +
  "walls, ergonomic mesh task chairs at every desk, enclosed meeting rooms with glass partitions, " +
  "potted plants, soft natural daylight, clean professional render, no text, no labels, no signage.";

export function Cad3D({ geometry }: { geometry: CadGeometry }) {
  const [render, setRender] = useState<null | { busy: boolean; img: string | null; err: string | null }>(null);
  const [lineMode, setLineMode] = useState(false);
  if (!geometry.bounds) return <div className="empty"><p>No geometry to extrude.</p></div>;
  const b = geometry.bounds;
  const size = Math.max(b.maxx - b.minx, b.maxy - b.miny);

  async function handleRender() {
    const canvas = document.querySelector(".space3d canvas") as HTMLCanvasElement | null;
    if (!canvas) return;
    // pass 1: flip the scene to crisp black-line mode and let r3f paint it, then capture.
    // that line drawing is the ControlNet condition -> the render is forced to follow it.
    setLineMode(true);
    await new Promise((r) => setTimeout(r, 220));
    const control = canvas.toDataURL("image/jpeg", 0.95);
    setLineMode(false);
    setRender({ busy: true, img: control, err: null });
    try {
      const r = await renderView(control, RENDER_PROMPT);
      setRender({ busy: false, img: r.image ?? control, err: r.image ? null : "Provider returned no image." });
    } catch (e) {
      setRender({ busy: false, img: control, err: String(e instanceof Error ? e.message : e) });
    }
  }

  return (
    <div className="space3d">
      <Canvas
        shadows
        gl={{ preserveDrawingBuffer: true }}
        camera={{ position: [size * 0.65, size * 0.6, size * 0.75], fov: 32 }}
        dpr={[1, 2]}
      >
        <CadScene geo={geometry} lineMode={lineMode} />
      </Canvas>
      <div className="mat-controls">
        <button className="ds-btn ds-btn--primary" onClick={handleRender}>Render (AI)</button>
        <span className="mat-hint">drag to orbit · scroll to zoom</span>
      </div>
      {render && (
        <div className="render-overlay" onClick={() => setRender(null)}>
          <div className="render-card" onClick={(e) => e.stopPropagation()}>
            <div className="render-head">
              <span className="ds-eyebrow">
                {render.busy ? "Rendering from your layout…" : render.err ? "Render unavailable" : "Photoreal render"}
              </span>
              <button className="ds-btn ds-btn--quiet" onClick={() => setRender(null)}>Close</button>
            </div>
            {render.img && <img src={render.img} alt="render" className={render.err ? "dim" : ""} />}
            {render.err && (
              <p className="render-note">
                {render.err}
                <br />
                <span className="ds-muted">
                  Set RENDER_API_URL + RENDER_API_KEY in backend/.env (Nano Banana / Decor8 / Spacely)
                  to enable real photoreal renders. The image above is your captured 3D view.
                </span>
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
