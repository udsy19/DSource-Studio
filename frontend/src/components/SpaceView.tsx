import { ContactShadows, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Component, type ReactNode, useMemo, useState } from "react";
import * as THREE from "three";
import { renderView } from "../api";
import type { Instance, Plan } from "../types";

/* Guards the WebGL canvas: if the browser/GPU can't start WebGL, show a calm fallback instead of
   crashing the whole Studio (the 2D Plan and every export keep working). */
class WebGLBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return (
        <div className="space3d-fallback">
          3D view unavailable — this browser or GPU could not start WebGL. The 2D Plan and all
          exports still work.
        </div>
      );
    }
    return this.props.children;
  }
}

/* ── finishes (the "materials" the customer can swap) ── */
const FLOORS = [
  { name: "Slate Carpet", color: "#6f6e69", roughness: 0.96 },
  { name: "Warm Oak", color: "#b58a52", roughness: 0.55 },
  { name: "Concrete", color: "#b6b2a9", roughness: 0.5 },
  { name: "Ash", color: "#cdc8bd", roughness: 0.82 },
];
const FINISHES = [
  { name: "Graphite", color: "#37352f" },
  { name: "Oak", color: "#c0a16b" },
  { name: "Ember", color: "#b8552f" },
  { name: "Bone", color: "#e6e0d3" },
];

const WALL_H = 3.2;
const ROOM_H = 7;
const MAX_RENDER = 2500; // safety cap so a pathological plan never freezes the browser

function centroid(boundary: [number, number][]) {
  const xs = boundary.map((p) => p[0]);
  const ys = boundary.map((p) => p[1]);
  return [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2] as const;
}

/* map plan (x,y) feet → world (x, z); y is up. */
function useWorld(plan: Plan) {
  return useMemo(() => {
    const [cx, cy] = centroid(plan.boundary);
    const xs = plan.boundary.map((p) => p[0]);
    const ys = plan.boundary.map((p) => p[1]);
    const size = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const wx = (x: number) => x - cx;
    const wz = (y: number) => -(y - cy);
    return { cx, cy, size, wx, wz };
  }, [plan]);
}

function Floor({ plan, w, finish }: { plan: Plan; w: ReturnType<typeof useWorld>; finish: typeof FLOORS[number] }) {
  const geo = useMemo(() => {
    const shape = new THREE.Shape(plan.boundary.map(([x, y]) => new THREE.Vector2(w.wx(x), -w.wz(y))));
    for (const core of plan.cores) {
      const path = new THREE.Path(core.map(([x, y]) => new THREE.Vector2(w.wx(x), -w.wz(y))));
      shape.holes.push(path);
    }
    return new THREE.ShapeGeometry(shape);
  }, [plan, w]);
  return (
    <mesh geometry={geo} rotation-x={-Math.PI / 2} receiveShadow>
      <meshStandardMaterial color={finish.color} roughness={finish.roughness} side={THREE.DoubleSide} />
    </mesh>
  );
}

function Walls({ plan, w }: { plan: Plan; w: ReturnType<typeof useWorld> }) {
  const edges = useMemo(() => {
    const out: { x: number; z: number; len: number; angle: number }[] = [];
    const b = plan.boundary;
    for (let i = 0; i < b.length; i++) {
      const a = b[i];
      const c = b[(i + 1) % b.length];
      const ax = w.wx(a[0]), az = w.wz(a[1]), cxw = w.wx(c[0]), czw = w.wz(c[1]);
      const dx = cxw - ax, dz = czw - az;
      const len = Math.hypot(dx, dz);
      if (len < 0.1) continue;
      out.push({ x: (ax + cxw) / 2, z: (az + czw) / 2, len, angle: -Math.atan2(dz, dx) });
    }
    return out;
  }, [plan, w]);
  return (
    <>
      {edges.map((e, i) => (
        <mesh key={i} position={[e.x, WALL_H / 2, e.z]} rotation-y={e.angle} castShadow>
          <boxGeometry args={[e.len + 0.5, WALL_H, 0.5]} />
          <meshStandardMaterial color="#efeae0" roughness={0.9} />
        </mesh>
      ))}
    </>
  );
}

function RoomShell({ w, h, color }: { w: number; h: number; color: string }) {
  const t = 0.25;
  const mat = <meshStandardMaterial color={color} transparent opacity={0.12} roughness={0.1} />;
  return (
    <group>
      <mesh position={[0, ROOM_H / 2, -h / 2]}>{<boxGeometry args={[w, ROOM_H, t]} />}{mat}</mesh>
      <mesh position={[0, ROOM_H / 2, h / 2]}>{<boxGeometry args={[w, ROOM_H, t]} />}{mat}</mesh>
      <mesh position={[-w / 2, ROOM_H / 2, 0]}>{<boxGeometry args={[t, ROOM_H, h]} />}{mat}</mesh>
      <mesh position={[w / 2, ROOM_H / 2, 0]}>{<boxGeometry args={[t, ROOM_H, h]} />}{mat}</mesh>
    </group>
  );
}

/* Optional REAL models: map a furniture type → a .glb URL to render real geometry instead of
   the procedural furniture below. Empty by default = procedural (always works). Manufacturer
   BIM files (.rfa/.skp/.dwg) must be converted to .glb first (Blender/assimp) — they cannot be
   loaded on the web directly — then dropped in here, e.g. { workstation: "/models/leap.glb" }. */
const MODELS: Partial<Record<Instance["type"], string>> = {};

function GltfPiece({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const obj = useMemo(() => scene.clone(), [scene]);
  return <primitive object={obj} />;
}

const PEDESTAL = "#2b2a27";
/* a real-office material palette — desks/tables read as wood, legs as metal; the "Finish" swatch
   drives only the soft goods (chair + sofa upholstery), so swapping it doesn't paint the room. */
const DESK_TOP = "#c7a679"; // warm oak laminate
const LEG = "#54524b"; // soft dark metal
const WOOD = "#a97d4a"; // conference/table wood

/* A real .glb chair can be dropped in here (e.g. "/models/chair.glb") to render real geometry.
   Empty by default = procedural chair: a single high-poly model cloned across hundreds of seats
   would freeze the browser (and 404s when absent), so procedural is the safe, scalable default. */
const CHAIR_MODEL = "";

/* loads a real .glb chair, auto-scaled to ~3.4 ft tall with its base on the floor */
function RealChair({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  const { obj, scale, py } = useMemo(() => {
    const o = scene.clone();
    const box = new THREE.Box3().setFromObject(o);
    const size = new THREE.Vector3();
    box.getSize(size);
    const s = 3.4 / (size.y || 1);
    return { obj: o, scale: s, py: -box.min.y * s };
  }, [scene]);
  return (
    <group scale={scale} position={[0, py, 0]}>
      <primitive object={obj} />
    </group>
  );
}

/* realistic task chair: real .glb model when configured, else procedural geometry (feet) */
function Chair({ uph }: { uph: string }) {
  if (CHAIR_MODEL) return <RealChair url={CHAIR_MODEL} />;
  return (
    <group>
      <mesh position={[0, 1.45, 0]} castShadow>
        <boxGeometry args={[1.5, 0.18, 1.5]} />
        <meshStandardMaterial color={uph} roughness={0.78} />
      </mesh>
      <mesh position={[0, 2.2, -0.62]} castShadow>
        <boxGeometry args={[1.5, 1.5, 0.16]} />
        <meshStandardMaterial color={uph} roughness={0.78} />
      </mesh>
      <mesh position={[0, 0.9, 0]} castShadow>
        <cylinderGeometry args={[0.1, 0.1, 1.1, 10]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.4} metalness={0.45} />
      </mesh>
      <mesh position={[0, 0.16, 0]} castShadow>
        <cylinderGeometry args={[0.75, 0.85, 0.16, 18]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.4} metalness={0.45} />
      </mesh>
    </group>
  );
}

/* desk: warm laminate top on two dark metal leg panels + a small monitor */
function Desk({ w, h }: { w: number; h: number }) {
  const depth = Math.min(h * 0.55, 2.6);
  const topW = Math.min(w * 0.95, 5.6);
  const lx = topW / 2 - 0.2;
  return (
    <group>
      <mesh position={[0, 2.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[topW, 0.12, depth]} />
        <meshStandardMaterial color={DESK_TOP} roughness={0.5} />
      </mesh>
      {[-lx, lx].map((x, i) => (
        <mesh key={i} position={[x, 1.2, 0]} castShadow>
          <boxGeometry args={[0.12, 2.4, depth * 0.82]} />
          <meshStandardMaterial color={LEG} roughness={0.45} metalness={0.3} />
        </mesh>
      ))}
      <mesh position={[0, 3.35, -depth * 0.28]} castShadow>
        <boxGeometry args={[1.7, 1.0, 0.08]} />
        <meshStandardMaterial color="#23211d" roughness={0.3} />
      </mesh>
    </group>
  );
}

/* conference table: wood top on a central metal plinth */
function Table({ w, h }: { w: number; h: number }) {
  return (
    <group>
      <mesh position={[0, 2.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.5, 0.16, h * 0.42]} />
        <meshStandardMaterial color={WOOD} roughness={0.35} />
      </mesh>
      <mesh position={[0, 1.2, 0]} castShadow>
        <boxGeometry args={[w * 0.18, 2.3, h * 0.12]} />
        <meshStandardMaterial color={LEG} roughness={0.5} metalness={0.3} />
      </mesh>
    </group>
  );
}

/* lounge sofa: seat base + back + two arms */
function Sofa({ color, w }: { color: string; w: number }) {
  const sw = Math.min(w * 0.5, 7);
  return (
    <group>
      <mesh position={[0, 0.55, 0]} castShadow><boxGeometry args={[sw, 0.8, 1.8]} /><meshStandardMaterial color={color} roughness={0.88} /></mesh>
      <mesh position={[0, 1.25, -0.75]} castShadow><boxGeometry args={[sw, 1.1, 0.35]} /><meshStandardMaterial color={color} roughness={0.88} /></mesh>
      {[-sw / 2 + 0.15, sw / 2 - 0.15].map((x, i) => (
        <mesh key={i} position={[x, 1.0, 0]} castShadow><boxGeometry args={[0.3, 0.9, 1.8]} /><meshStandardMaterial color={color} roughness={0.88} /></mesh>
      ))}
    </group>
  );
}

function Piece({ it, finish }: { it: Instance; finish: string }) {
  const { type, w, h } = it;
  const model = MODELS[type];
  if (model) return <GltfPiece url={model} />;
  switch (type) {
    case "workstation":
      return (
        <group>
          <Desk w={w} h={h} />
          <group position={[0, 0, h * 0.3]}>
            <Chair uph={finish} />
          </group>
        </group>
      );
    case "private_office":
      return (
        <group>
          <RoomShell w={w} h={h} color="#7d8a86" />
          <group position={[0, 0, -h * 0.12]}>
            <Desk w={w * 0.62} h={h * 0.5} />
          </group>
          <group position={[0, 0, h * 0.12]}>
            <Chair uph={finish} />
          </group>
        </group>
      );
    case "meeting_room":
      return (
        <group>
          <RoomShell w={w} h={h} color="#7d8a86" />
          <Table w={w} h={h} />
          {[-1, 1].map((sx) =>
            [-1, 1].map((sz) => (
              <group key={`${sx}${sz}`} position={[(sx * w) / 4.5, 0, (sz * h) / 4.5]}>
                <Chair uph={finish} />
              </group>
            )),
          )}
        </group>
      );
    case "collaboration":
      return (
        <group>
          <mesh position={[0, 0.04, 0]} receiveShadow rotation-x={-Math.PI / 2}>
            <planeGeometry args={[w * 0.85, h * 0.85]} />
            <meshStandardMaterial color="#b8552f" transparent opacity={0.14} roughness={1} />
          </mesh>
          <group position={[0, 0, h * 0.12]}>
            <Sofa color={finish} w={w} />
          </group>
        </group>
      );
    default:
      return null;
  }
}

function Scene({ plan, instances, floor, finish }: {
  plan: Plan; instances: Instance[]; floor: typeof FLOORS[number]; finish: typeof FINISHES[number];
}) {
  const w = useWorld(plan);
  return (
    <>
      <color attach="background" args={["#f4f1ea"]} />
      <ambientLight intensity={0.85} />
      <hemisphereLight args={["#fff7ec", "#d8d2c4", 0.55]} />
      <directionalLight
        position={[w.size, w.size * 1.4, w.size * 0.6]}
        intensity={1.25}
        color="#fff4e6"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
      />
      <Floor plan={plan} w={w} finish={floor} />
      <Walls plan={plan} w={w} />
      {plan.columns.map(([x, y], i) => (
        <mesh key={`c${i}`} position={[w.wx(x), WALL_H / 2, w.wz(y)]} castShadow>
          <cylinderGeometry args={[0.8, 0.8, WALL_H, 16]} />
          <meshStandardMaterial color="#d6d0c0" roughness={0.7} />
        </mesh>
      ))}
      {instances.slice(0, MAX_RENDER).map((it, i) => (
        <group key={i} position={[w.wx(it.x + it.w / 2), 0, w.wz(it.y + it.h / 2)]}>
          <Piece it={it} finish={finish.color} />
        </group>
      ))}
      <ContactShadows position={[0, 0.02, 0]} scale={w.size * 2.4} blur={2.2} opacity={0.3} far={20} />
      <OrbitControls makeDefault enablePan target={[0, 0, 0]} maxPolarAngle={Math.PI / 2.05} minDistance={20} />
    </>
  );
}

export default function SpaceView({ plan, instances }: { plan: Plan; instances: Instance[] }) {
  const [floor, setFloor] = useState(FLOORS[0]);
  const [finish, setFinish] = useState(FINISHES[0]);
  const [render, setRender] = useState<null | { busy: boolean; img: string | null; err: string | null }>(null);
  const { size } = useWorld(plan);

  async function handleRender() {
    const canvas = document.querySelector(".space3d canvas") as HTMLCanvasElement | null;
    if (!canvas) return;
    const shot = canvas.toDataURL("image/jpeg", 0.85);
    setRender({ busy: true, img: shot, err: null });
    try {
      const r = await renderView(shot);
      setRender({ busy: false, img: r.image ?? shot, err: r.image ? null : "Provider returned no image." });
    } catch (e) {
      setRender({ busy: false, img: shot, err: String(e instanceof Error ? e.message : e) });
    }
  }

  return (
    <div className="space3d">
      <WebGLBoundary>
        <Canvas
          shadows
          gl={{ preserveDrawingBuffer: true }}
          camera={{ position: [size * 0.75, size * 0.7, size * 0.85], fov: 34 }}
          dpr={[1, 2]}
        >
          <Scene plan={plan} instances={instances} floor={floor} finish={finish} />
        </Canvas>
      </WebGLBoundary>

      <div className="mat-controls">
        <div className="mat-group">
          <span className="ds-eyebrow">Floor</span>
          <div className="sw-row">
            {FLOORS.map((f) => (
              <button key={f.name} title={f.name} className={`sw ${floor.name === f.name ? "on" : ""}`}
                style={{ background: f.color }} onClick={() => setFloor(f)} />
            ))}
          </div>
        </div>
        <div className="mat-group">
          <span className="ds-eyebrow">Finish</span>
          <div className="sw-row">
            {FINISHES.map((f) => (
              <button key={f.name} title={f.name} className={`sw ${finish.name === f.name ? "on" : ""}`}
                style={{ background: f.color }} onClick={() => setFinish(f)} />
            ))}
          </div>
        </div>
        <button className="ds-btn ds-btn--primary" onClick={handleRender}>Render</button>
        <span className="mat-hint">drag to orbit · scroll to zoom</span>
      </div>

      {render && (
        <div className="render-overlay" onClick={() => setRender(null)}>
          <div className="render-card" onClick={(e) => e.stopPropagation()}>
            <div className="render-head">
              <span className="ds-eyebrow">{render.busy ? "Rendering…" : render.err ? "Render unavailable" : "Photoreal render"}</span>
              <button className="ds-btn ds-btn--quiet" onClick={() => setRender(null)}>Close</button>
            </div>
            {render.img && <img src={render.img} alt="render" className={render.err ? "dim" : ""} />}
            {render.err && (
              <p className="render-note">
                {render.err}
                <br />
                <span className="ds-muted">Set RENDER_API_URL + RENDER_API_KEY in backend/.env (a Decor8/Spacely image-to-image endpoint) to enable real renders. The image above is your captured 3D view.</span>
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
