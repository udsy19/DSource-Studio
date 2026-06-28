import { ContactShadows, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Component, type ReactNode, useMemo, useState } from "react";
import * as THREE from "three";
import { renderView } from "../api";
import type { ExtractedFurniture, ExtractedLayout, Instance, Plan } from "../types";

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
const LAYOUT_WALL_H = 8.0; // real extracted walls + generated-fit glass partitions: ceiling-ish, so rooms enclose
const MAX_RENDER = 2500; // safety cap so a pathological plan never freezes the browser

type World = { cx: number; cy: number; size: number; wx: (x: number) => number; wz: (y: number) => number };

/* map plan (x,y) feet → world (x, z); y is up. Shared by both render modes. */
function worldFromBounds(minx: number, miny: number, maxx: number, maxy: number): World {
  const cx = (minx + maxx) / 2;
  const cy = (miny + maxy) / 2;
  const size = Math.max(maxx - minx, maxy - miny);
  return { cx, cy, size, wx: (x) => x - cx, wz: (y) => -(y - cy) };
}

function useWorld(plan: Plan) {
  return useMemo(() => {
    const xs = plan.boundary.map((p) => p[0]);
    const ys = plan.boundary.map((p) => p[1]);
    return worldFromBounds(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys));
  }, [plan]);
}

function Floor({ plan, w, finish }: { plan: Plan; w: World; finish: typeof FLOORS[number] }) {
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

function Walls({ plan, w }: { plan: Plan; w: World }) {
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

/* translucent glass partitions enclosing a room footprint — four walls at the layout's ~8 ft
   partition height so generated offices/meeting rooms read as rooms, not floating desks.
   Same glass material as the extracted-CAD LayoutWalls (cool slate, no depth write). */
function RoomShell({ w, h }: { w: number; h: number }) {
  const t = 0.16;
  const y = LAYOUT_WALL_H / 2;
  const glass = (
    <meshStandardMaterial
      color="#aec4cc" transparent opacity={0.18} roughness={0.1} metalness={0.1}
      depthWrite={false}
    />
  );
  return (
    <group>
      <mesh position={[0, y, -h / 2]}>{<boxGeometry args={[w, LAYOUT_WALL_H, t]} />}{glass}</mesh>
      <mesh position={[0, y, h / 2]}>{<boxGeometry args={[w, LAYOUT_WALL_H, t]} />}{glass}</mesh>
      <mesh position={[-w / 2, y, 0]}>{<boxGeometry args={[t, LAYOUT_WALL_H, h]} />}{glass}</mesh>
      <mesh position={[w / 2, y, 0]}>{<boxGeometry args={[t, LAYOUT_WALL_H, h]} />}{glass}</mesh>
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

/* small stool: round seat on a slim post */
function Stool({ color }: { color: string }) {
  return (
    <group>
      <mesh position={[0, 1.5, 0]} castShadow>
        <cylinderGeometry args={[0.7, 0.7, 0.2, 16]} />
        <meshStandardMaterial color={color} roughness={0.8} />
      </mesh>
      <mesh position={[0, 0.75, 0]} castShadow>
        <cylinderGeometry args={[0.1, 0.1, 1.4, 10]} />
        <meshStandardMaterial color={PEDESTAL} roughness={0.4} metalness={0.45} />
      </mesh>
    </group>
  );
}

/* tv / screen: a thin dark panel on a small floor stand */
function Tv({ w, h }: { w: number; h: number }) {
  const sw = Math.min(Math.max(w, h), 5.5);
  return (
    <group>
      <mesh position={[0, 4, 0]} castShadow>
        <boxGeometry args={[sw, sw * 0.56, 0.12]} />
        <meshStandardMaterial color="#23211d" roughness={0.25} metalness={0.1} />
      </mesh>
      <mesh position={[0, 1.4, 0]} castShadow>
        <boxGeometry args={[0.2, 2.8, 0.2]} />
        <meshStandardMaterial color={LEG} roughness={0.5} metalness={0.3} />
      </mesh>
      <mesh position={[0, 0.1, 0]} castShadow>
        <boxGeometry args={[sw * 0.4, 0.2, 0.8]} />
        <meshStandardMaterial color={LEG} roughness={0.5} metalness={0.3} />
      </mesh>
    </group>
  );
}

/* storage: a simple cabinet box filling its footprint */
function Cabinet({ w, h }: { w: number; h: number }) {
  return (
    <mesh position={[0, 1.6, 0]} castShadow receiveShadow>
      <boxGeometry args={[w * 0.9, 3.2, h * 0.9]} />
      <meshStandardMaterial color={WOOD} roughness={0.6} />
    </mesh>
  );
}

/* panel: a translucent glass partition slab spanning the footprint's long side */
function GlassPanel({ w, h }: { w: number; h: number }) {
  const span = Math.max(w, h);
  return (
    <mesh position={[0, LAYOUT_WALL_H / 2, 0]} castShadow>
      <boxGeometry args={[span, LAYOUT_WALL_H, 0.16]} />
      <meshStandardMaterial
        color="#aec4cc" transparent opacity={0.18} roughness={0.1} metalness={0.1}
        depthWrite={false}
      />
    </mesh>
  );
}

/* planter: a small green box */
function Planter({ w, h }: { w: number; h: number }) {
  const s = Math.min(w, h, 2.4);
  return (
    <group>
      <mesh position={[0, 0.5, 0]} castShadow>
        <boxGeometry args={[s, 1.0, s]} />
        <meshStandardMaterial color="#7d6a4f" roughness={0.85} />
      </mesh>
      <mesh position={[0, 1.6, 0]} castShadow>
        <boxGeometry args={[s * 0.95, 1.4, s * 0.95]} />
        <meshStandardMaterial color="#6f8a5e" roughness={0.95} />
      </mesh>
    </group>
  );
}

/* a low generic box for unrecognised categories */
function LowBox({ w, h }: { w: number; h: number }) {
  return (
    <mesh position={[0, 0.6, 0]} castShadow receiveShadow>
      <boxGeometry args={[w * 0.85, 1.2, h * 0.85]} />
      <meshStandardMaterial color="#b6b2a9" roughness={0.8} />
    </mesh>
  );
}

/* map an extracted-furniture category → existing/new procedural geometry */
function CategoryPiece({ f, finish }: { f: ExtractedFurniture; finish: string }) {
  const { category, w, h } = f;
  switch (category) {
    case "chair":
      return <Chair uph={finish} />;
    case "stool":
      return <Stool color={finish} />;
    case "desk":
    case "workstation":
      return <Desk w={w} h={h} />;
    case "table":
      return <Table w={w} h={h} />;
    case "sofa":
      return <Sofa color={finish} w={w} />;
    case "tv":
      return <Tv w={w} h={h} />;
    case "storage":
      return <Cabinet w={w} h={h} />;
    case "panel":
      return <GlassPanel w={w} h={h} />;
    case "planter":
      return <Planter w={w} h={h} />;
    case "mullion":
      return null; // glazing framing — drawn by the glass panels, not as standalone objects
    default:
      return <LowBox w={w} h={h} />;
  }
}

/* a wall segment extruded from a polyline; height + material vary by type.
   glass = translucent, core = darker solid, everything else = solid drywall. */
function LayoutWalls({ layout, w }: { layout: ExtractedLayout; w: World }) {
  const segs = useMemo(() => {
    const out: { x: number; z: number; len: number; angle: number; type: ExtractedLayout["walls"][number]["type"] }[] = [];
    for (const wall of layout.walls) {
      for (let i = 0; i < wall.points.length - 1; i++) {
        const a = wall.points[i];
        const b = wall.points[i + 1];
        const ax = w.wx(a[0]), az = w.wz(a[1]), bx = w.wx(b[0]), bz = w.wz(b[1]);
        const dx = bx - ax, dz = bz - az;
        const len = Math.hypot(dx, dz);
        if (len < 0.1) continue;
        out.push({ x: (ax + bx) / 2, z: (az + bz) / 2, len, angle: -Math.atan2(dz, dx), type: wall.type });
      }
    }
    return out;
  }, [layout, w]);

  return (
    <>
      {segs.map((s, i) => {
        const glass = s.type === "glass";
        const half = s.type === "half_drywall";
        const core = s.type === "core";
        const h = half ? LAYOUT_WALL_H * 0.45 : LAYOUT_WALL_H;
        const thickness = glass ? 0.16 : core ? 0.7 : 0.45;
        return (
          <mesh key={i} position={[s.x, h / 2, s.z]} rotation-y={s.angle} castShadow>
            <boxGeometry args={[s.len + (glass ? 0 : 0.3), h, thickness]} />
            {glass ? (
              <meshStandardMaterial
                color="#aec4cc" transparent opacity={0.22} roughness={0.1} metalness={0.1}
                depthWrite={false}
              />
            ) : (
              <meshStandardMaterial
                color={core ? "#5a564d" : "#efeae0"} roughness={0.9}
                polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}
              />
            )}
          </mesh>
        );
      })}
    </>
  );
}

function LayoutScene({ layout, floor, finish }: {
  layout: ExtractedLayout; floor: typeof FLOORS[number]; finish: typeof FINISHES[number];
}) {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const w = useMemo(() => worldFromBounds(minx, miny, maxx, maxy), [minx, miny, maxx, maxy]);
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
      <mesh rotation-x={-Math.PI / 2} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[(maxx - minx) * 1.1, (maxy - miny) * 1.1]} />
        <meshStandardMaterial color={floor.color} roughness={floor.roughness} side={THREE.DoubleSide} />
      </mesh>
      <LayoutWalls layout={layout} w={w} />
      {layout.furniture.slice(0, MAX_RENDER).map((f, i) => (
        <group
          key={i}
          position={[w.wx(f.x + f.w / 2), 0, w.wz(f.y + f.h / 2)]}
          rotation-y={(-f.rotation * Math.PI) / 180}
        >
          <CategoryPiece f={f} finish={finish.color} />
        </group>
      ))}
      <ContactShadows position={[0, 0.02, 0]} scale={w.size * 2.4} blur={2.2} opacity={0.3} far={20} />
      <OrbitControls makeDefault enablePan target={[0, 0, 0]} maxPolarAngle={Math.PI / 2.05} minDistance={20} />
    </>
  );
}

function Piece({ it, finish }: { it: Instance; finish: string }) {
  const { type, w, h } = it;
  const model = MODELS[type];
  if (model) return <GltfPiece url={model} />;
  // widen to string: generated programs may emit richer types (e.g. phone_booth) beyond the
  // four in the InstanceType union — handle them here, unknowns fall through to a low box.
  switch (type as string) {
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
          <RoomShell w={w} h={h} />
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
          <RoomShell w={w} h={h} />
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
    case "phone_booth":
      return (
        <group>
          <RoomShell w={w} h={h} />
          <Stool color={finish} />
        </group>
      );
    default:
      return <LowBox w={w} h={h} />;
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

type SpaceViewProps = { plan: Plan; instances: Instance[] } | { layout: ExtractedLayout };

export default function SpaceView(props: SpaceViewProps) {
  const [floor, setFloor] = useState(FLOORS[0]);
  const [finish, setFinish] = useState(FINISHES[0]);
  const [render, setRender] = useState<null | { busy: boolean; img: string | null; err: string | null }>(null);
  const size = "layout" in props
    ? Math.max(props.layout.bounds[2] - props.layout.bounds[0], props.layout.bounds[3] - props.layout.bounds[1])
    : worldFromBounds(
        Math.min(...props.plan.boundary.map((p) => p[0])),
        Math.min(...props.plan.boundary.map((p) => p[1])),
        Math.max(...props.plan.boundary.map((p) => p[0])),
        Math.max(...props.plan.boundary.map((p) => p[1])),
      ).size;

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
          {"layout" in props ? (
            <LayoutScene layout={props.layout} floor={floor} finish={finish} />
          ) : (
            <Scene plan={props.plan} instances={props.instances} floor={floor} finish={finish} />
          )}
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
