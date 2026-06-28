import { ContactShadows, Environment, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Component, type ReactNode, Suspense, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { renderView } from "../api";
import { Segmented } from "../design/ui";
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
/* wall finishes for the "Walls" material control — applied to the opaque partitions/perimeter walls.
   Glass keeps the translucent partition look; the rest are matte meshStandardMaterials. */
const WALLS = [
  { name: "Painted", color: "#efeae0", roughness: 0.92, metalness: 0, glass: false },
  { name: "Glass", color: "#aec4cc", roughness: 0.06, metalness: 0.25, glass: true },
  { name: "Wood", color: "#9b6c3d", roughness: 0.55, metalness: 0.04, glass: false },
  { name: "Concrete", color: "#9a978f", roughness: 0.86, metalness: 0, glass: false },
];
const CEILINGS = ["Open", "Acoustic", "Drywall", "Wood slat"] as const;
type CeilingType = (typeof CEILINGS)[number];
type ViewMode = "cutaway" | "full";

const WALL_H = 3.2;
const LAYOUT_WALL_H = 8.0; // generated-fit glass partitions: ceiling-ish, so clean synthesized rooms enclose
// Extracted-CAD walls are messy FRAGMENTS — full-height opaque slabs read as a chaotic forest that
// blocks the view. Cut them at a dollhouse height so you see OVER them into the furnished space.
const DOLLHOUSE_H = 3.6;
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

/* Shared lighting + atmosphere for both render modes — warm image-based environment for subtle
   glass/surface reflections, one shadow-casting key, a cool fill, low ambient, and a paper-toned
   fog for depth. Shadows are baked once (autoUpdate off) so orbiting ~300 desks stays smooth: the
   light + geometry are static, only the camera moves, so the shadow map never needs to re-render.
   A React commit (material swap) re-bakes once via needsUpdate. */
function SceneLighting({ size }: { size: number }) {
  const gl = useThree((s) => s.gl);
  useEffect(() => {
    gl.shadowMap.autoUpdate = false;
    gl.shadowMap.needsUpdate = true;
  });
  return (
    <>
      <color attach="background" args={["#f4f1ea"]} />
      <fog attach="fog" args={["#ece7da", size * 1.9, size * 4.6]} />
      <Suspense fallback={null}>
        <Environment preset="apartment" environmentIntensity={0.4} />
      </Suspense>
      <ambientLight intensity={0.32} />
      <hemisphereLight args={["#fff5e8", "#cfc7b6", 0.4]} />
      <directionalLight
        position={[size * 0.95, size * 1.55, size * 0.7]}
        intensity={1.55}
        color="#fff0d8"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-normalBias={0.05}
      >
        <orthographicCamera attach="shadow-camera" args={[-size, size, size, -size, 0.5, size * 4.5]} />
      </directionalLight>
      <directionalLight position={[-size * 0.8, size * 0.55, -size * 0.6]} intensity={0.35} color="#cdd8e8" />
    </>
  );
}

/* Shared wall finish for the "Walls" control — opaque partitions/perimeter walls of both scenes.
   Glass picks the translucent partition look; the rest are matte slabs that keep polygonOffset so
   wall-mounted screens still win the depth test. */
function WallMaterial({ wall }: { wall: (typeof WALLS)[number] }) {
  if (wall.glass) {
    return (
      <meshStandardMaterial
        color={wall.color} transparent opacity={0.16} roughness={0.06} metalness={0.25}
        envMapIntensity={1.4} depthWrite={false} side={THREE.DoubleSide}
      />
    );
  }
  return (
    <meshStandardMaterial
      color={wall.color} roughness={wall.roughness} metalness={wall.metalness}
      envMapIntensity={0.3} side={THREE.DoubleSide}
      polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}
    />
  );
}

/* A real acoustic-tile face, baked once into a small repeating CanvasTexture: a light tile centre,
   a soft inner bevel, and a darker recessed seam around each 2 ft tile. One texture + one plane =
   one draw call for the whole ceiling, so it stays cheap over a big floor plate. The texture repeats
   once per 2 ft tile (set via .repeat), so seams land on a true 2 ft grid regardless of room size. */
function useCeilingTexture(width: number, depth: number) {
  const tex = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 128;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#b9b3a4"; // recessed seam / shadow gap
    ctx.fillRect(0, 0, 128, 128);
    ctx.fillStyle = "#e7e3da"; // tile edge
    ctx.fillRect(4, 4, 120, 120);
    ctx.fillStyle = "#f1eee7"; // tile face (faint inner bevel highlight)
    ctx.fillRect(8, 8, 112, 112);
    ctx.fillStyle = "rgba(150,144,132,0.18)"; // light acoustic fissure speckle
    for (let i = 0; i < 70; i++) {
      const x = 8 + Math.random() * 112;
      const y = 8 + Math.random() * 112;
      ctx.fillRect(x, y, 1.4, 1.4);
    }
    const t = new THREE.CanvasTexture(canvas);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(Math.max(1, Math.round(width / 2)), Math.max(1, Math.round(depth / 2)));
    t.anisotropy = 4;
    return t;
  }, [width, depth]);
  useEffect(() => () => tex.dispose(), [tex]);
  return tex;
}

/* Ceiling for Full-height view only — a plane at the top of the walls. Open = exposed (no ceiling);
   Acoustic = a real 2 ft drop-tile grid; Drywall = clean matte with a faint perimeter reveal;
   Wood slat = even warm-timber slats over a dark reveal. Recessed troffer fixtures (emissive panels
   + a small point-light each) make the interior read as a real lit room. The ceiling never casts
   shadow, so it doesn't occlude the baked key light and the interior stays lit. */
function Ceiling({ width, depth, height, type }: {
  width: number; depth: number; height: number; type: CeilingType;
}) {
  const tex = useCeilingTexture(width, depth);
  const slats = useMemo(() => {
    const pitch = 2.2;
    const n = Math.max(2, Math.round(depth / pitch));
    const step = depth / n;
    const positions = Array.from({ length: n }, (_, i) => -depth / 2 + step * (i + 0.5));
    return { positions, slatDepth: step * 0.8 };
  }, [depth]);
  // A few recessed troffers on a coarse grid (≤4 fixtures ⇒ ≤4 extra non-shadow lights, bounded cost).
  const fixtures = useMemo(() => {
    const nx = Math.min(2, Math.max(1, Math.round(width / 14)));
    const nz = Math.min(2, Math.max(1, Math.round(depth / 14)));
    const pts: [number, number][] = [];
    for (let i = 0; i < nx; i++)
      for (let j = 0; j < nz; j++)
        pts.push([-width / 2 + width * ((i + 0.5) / nx), -depth / 2 + depth * ((j + 0.5) / nz)]);
    return pts;
  }, [width, depth]);

  if (type === "Open") return null;
  return (
    <group position={[0, height, 0]}>
      {type === "Acoustic" && (
        <mesh rotation-x={Math.PI / 2} receiveShadow>
          <planeGeometry args={[width, depth]} />
          <meshStandardMaterial
            map={tex} color="#ffffff" roughness={0.96} metalness={0}
            envMapIntensity={0.22} side={THREE.DoubleSide}
          />
        </mesh>
      )}
      {type === "Drywall" && (
        <>
          {/* full-size darker plane reads as a recessed shadow reveal where ceiling meets wall */}
          <mesh rotation-x={Math.PI / 2} position={[0, 0.04, 0]}>
            <planeGeometry args={[width, depth]} />
            <meshStandardMaterial color="#bdb8ab" roughness={1} metalness={0} side={THREE.DoubleSide} />
          </mesh>
          <mesh rotation-x={Math.PI / 2} receiveShadow>
            <planeGeometry args={[width - 0.5, depth - 0.5]} />
            <meshStandardMaterial color="#f1ede6" roughness={0.96} metalness={0} envMapIntensity={0.18} side={THREE.DoubleSide} />
          </mesh>
        </>
      )}
      {type === "Wood slat" && (
        <>
          <mesh rotation-x={Math.PI / 2}>
            <planeGeometry args={[width, depth]} />
            <meshStandardMaterial color="#34291c" roughness={0.9} metalness={0} side={THREE.DoubleSide} />
          </mesh>
          {slats.positions.map((z, i) => (
            <mesh key={i} position={[0, -0.08, z]} castShadow receiveShadow>
              <boxGeometry args={[width, 0.16, slats.slatDepth]} />
              <meshStandardMaterial color="#6b4f30" roughness={0.58} metalness={0.04} envMapIntensity={0.35} />
            </mesh>
          ))}
        </>
      )}
      {fixtures.map(([x, z], i) => (
        <group key={i}>
          <mesh position={[x, -0.04, z]} rotation-x={Math.PI / 2}>
            <planeGeometry args={[3.6, 1.6]} />
            <meshStandardMaterial
              color="#ffffff" emissive="#fff3df" emissiveIntensity={1.3}
              roughness={0.4} side={THREE.DoubleSide} toneMapped={false}
            />
          </mesh>
          <pointLight position={[x, -0.6, z]} intensity={6} distance={28} decay={2} color="#fff2db" />
        </group>
      ))}
    </group>
  );
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
      <meshStandardMaterial
        color={finish.color}
        roughness={finish.roughness}
        metalness={0}
        envMapIntensity={0.4}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

function Walls({ plan, w, wall, wallH }: { plan: Plan; w: World; wall: (typeof WALLS)[number]; wallH: number }) {
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
        <mesh key={i} position={[e.x, wallH / 2, e.z]} rotation-y={e.angle} castShadow receiveShadow>
          <boxGeometry args={[e.len + 0.5, wallH, 0.5]} />
          <WallMaterial wall={wall} />
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
      color="#aec4cc" transparent opacity={0.16} roughness={0.06} metalness={0.25}
      envMapIntensity={1.5} depthWrite={false}
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
const WOOD = "#8a6238"; // conference/table + cabinet — darker walnut

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
        <meshStandardMaterial color={uph} roughness={0.85} envMapIntensity={0.25} />
      </mesh>
      <mesh position={[0, 2.2, -0.62]} castShadow>
        <boxGeometry args={[1.5, 1.5, 0.16]} />
        <meshStandardMaterial color={uph} roughness={0.85} envMapIntensity={0.25} />
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
        <meshPhysicalMaterial
          color={DESK_TOP} roughness={0.38} metalness={0.04}
          clearcoat={0.45} clearcoatRoughness={0.35} envMapIntensity={0.6}
        />
      </mesh>
      {[-lx, lx].map((x, i) => (
        <mesh key={i} position={[x, 1.2, 0]} castShadow>
          <boxGeometry args={[0.12, 2.4, depth * 0.82]} />
          <meshStandardMaterial color={LEG} roughness={0.45} metalness={0.3} />
        </mesh>
      ))}
      {/* monitor on a slim stand, screen gently lit so the workstation reads as "on" */}
      <group position={[0, 0, -depth * 0.28]}>
        <mesh position={[0, 2.66, 0]} castShadow>
          <boxGeometry args={[0.12, 0.42, 0.08]} />
          <meshStandardMaterial color={LEG} roughness={0.4} metalness={0.4} />
        </mesh>
        <mesh position={[0, 3.35, 0]} castShadow>
          <boxGeometry args={[1.7, 1.0, 0.08]} />
          <meshStandardMaterial color="#1c1b18" roughness={0.4} metalness={0.2} />
        </mesh>
        <mesh position={[0, 3.35, 0.05]}>
          <boxGeometry args={[1.55, 0.86, 0.02]} />
          <meshStandardMaterial color="#2a2f36" emissive="#3b4a57" emissiveIntensity={0.32} roughness={0.2} />
        </mesh>
      </group>
    </group>
  );
}

/* conference table: wood top on a central metal plinth */
function Table({ w, h }: { w: number; h: number }) {
  return (
    <group>
      <mesh position={[0, 2.4, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.5, 0.16, h * 0.42]} />
        <meshPhysicalMaterial color={WOOD} roughness={0.32} metalness={0.05} clearcoat={0.35} clearcoatRoughness={0.4} envMapIntensity={0.6} />
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
  const fabric = (
    <meshPhysicalMaterial color={color} roughness={0.92} sheen={0.6} sheenRoughness={0.5} sheenColor={color} />
  );
  return (
    <group>
      <mesh position={[0, 0.55, 0]} castShadow><boxGeometry args={[sw, 0.8, 1.8]} />{fabric}</mesh>
      <mesh position={[0, 1.25, -0.75]} castShadow><boxGeometry args={[sw, 1.1, 0.35]} />{fabric}</mesh>
      {[-sw / 2 + 0.15, sw / 2 - 0.15].map((x, i) => (
        <mesh key={i} position={[x, 1.0, 0]} castShadow><boxGeometry args={[0.3, 0.9, 1.8]} />{fabric}</mesh>
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

/* tv / screen: a clean wall-mounted panel. Sized so its top stays under the 3.6 ft dollhouse cut,
   given real depth + a small standoff off the wall behind it, and polygonOffset so the dark face
   always wins the depth test against that wall (no z-fight flicker, no floating over the wall). */
function Tv({ w, h }: { w: number; h: number }) {
  const sw = Math.min(Math.max(w, h), 4.4);
  const screenH = sw * 0.56;
  const cy = Math.min(2.2, DOLLHOUSE_H - screenH / 2 - 0.1); // keep top under the dollhouse cut
  const depth = 0.3;
  const standoff = depth / 2 + 0.06; // push the panel just off any wall it backs onto
  return (
    <group position={[0, 0, standoff]}>
      <mesh position={[0, cy, 0]} castShadow>
        <boxGeometry args={[sw + 0.12, screenH + 0.12, depth]} />
        <meshStandardMaterial
          color="#1a1916" roughness={0.5} metalness={0.2}
          polygonOffset polygonOffsetFactor={-2} polygonOffsetUnits={-2}
        />
      </mesh>
      <mesh position={[0, cy, depth / 2 + 0.01]} castShadow>
        <boxGeometry args={[sw, screenH, 0.03]} />
        <meshStandardMaterial
          color="#26241f" roughness={0.16} metalness={0.1} envMapIntensity={0.6}
          polygonOffset polygonOffsetFactor={-2} polygonOffsetUnits={-2}
        />
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
    <mesh position={[0, DOLLHOUSE_H / 2, 0]} castShadow>
      <boxGeometry args={[span, DOLLHOUSE_H, 0.16]} />
      <meshStandardMaterial
        color="#aec4cc" transparent opacity={0.16} roughness={0.06} metalness={0.25}
        envMapIntensity={1.2} depthWrite={false} side={THREE.DoubleSide}
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
// Drop the camera to an interior angle in Full-height (so you look INTO the room and up at the
// ceiling, not down at its top); restore the high 3/4 dollhouse angle in Cutaway. Re-runs only when
// the view mode or plate size changes, so it never fights the user's orbit.
function CameraRig({ view, size }: { view: ViewMode; size: number }) {
  const { camera, controls } = useThree();
  useEffect(() => {
    // Full height: sit INSIDE the footprint at eye level (~6.4 ft, below the 8 ft ceiling) with a
    // wider lens so the room feels open and the lit ceiling reads. Cutaway: the high 3/4 dollhouse view.
    const pos: [number, number, number] =
      view === "full"
        ? [size * 0.18, 6.4, size * 0.22]
        : [size * 0.92, size * 0.5, size * 0.96];
    const cam = camera as THREE.PerspectiveCamera;
    cam.fov = view === "full" ? 52 : 32;
    cam.position.set(pos[0], pos[1], pos[2]);
    cam.updateProjectionMatrix();
    const c = controls as unknown as { target: THREE.Vector3; update: () => void } | null;
    if (c) {
      c.target.set(0, view === "full" ? 5.6 : 0, 0);
      c.update();
    }
  }, [view, size, camera, controls]);
  return null;
}

/* Extraction can emit a malformed footprint — zero, NaN, or negative (a negative box/cylinder
   dimension inverts the geometry into an inside-out, mirrored mesh) or an absurd outlier. Clamp to
   a sane positive size so no bad row renders a flipped, sunken, or giant piece. */
function clampDim(v: number): number {
  return Number.isFinite(v) ? Math.min(Math.max(Math.abs(v), 0.5), 30) : 1.5;
}

function CategoryPiece({ f, finish }: { f: ExtractedFurniture; finish: string }) {
  const { category } = f;
  const w = clampDim(f.w);
  const h = clampDim(f.h);
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
function LayoutWalls({ layout, w, wall, wallH }: {
  layout: ExtractedLayout; w: World; wall: (typeof WALLS)[number]; wallH: number;
}) {
  const segs = useMemo(() => {
    const out: { x: number; z: number; len: number; angle: number; type: ExtractedLayout["walls"][number]["type"] }[] = [];
    for (const seg of layout.walls) {
      const pts = seg.points;
      // The perimeter is a closed building envelope, but contour/CAD point lists don't repeat the
      // first point — so also render the closing edge (last → first) or the enclosure shows a gap.
      const edges = seg.type === "perimeter" && pts.length > 2 ? pts.length : pts.length - 1;
      for (let i = 0; i < edges; i++) {
        const a = pts[i];
        const b = pts[(i + 1) % pts.length];
        const ax = w.wx(a[0]), az = w.wz(a[1]), bx = w.wx(b[0]), bz = w.wz(b[1]);
        const dx = bx - ax, dz = bz - az;
        const len = Math.hypot(dx, dz);
        if (len < 0.02) continue; // skip only true zero-length noise, never real short runs
        out.push({ x: (ax + bx) / 2, z: (az + bz) / 2, len, angle: -Math.atan2(dz, dx), type: seg.type });
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
        const perimeter = s.type === "perimeter";
        // height follows the View mode (dollhouse cut vs full); half-walls stay lower, the
        // perimeter envelope always rises to the full wall height so the building reads enclosed
        const h = half ? wallH * 0.6 : wallH;
        // perimeter is a thicker structural slab; it falls through to the finishable WallMaterial
        const thickness = glass ? 0.16 : core ? 0.7 : perimeter ? 0.6 : 0.45;
        return (
          <mesh key={i} position={[s.x, h / 2, s.z]} rotation-y={s.angle} castShadow receiveShadow>
            <boxGeometry args={[s.len + (glass ? 0 : 0.3), h, thickness]} />
            {glass ? (
              <meshStandardMaterial
                color="#aec4cc" transparent opacity={0.16} roughness={0.06} metalness={0.25}
                envMapIntensity={1.2} depthWrite={false} side={THREE.DoubleSide}
              />
            ) : core ? (
              // structural core stays its own dark slab — not a finishable wall surface
              <meshStandardMaterial
                color="#6b665b" roughness={0.94} envMapIntensity={0.2} side={THREE.DoubleSide}
                polygonOffset polygonOffsetFactor={1} polygonOffsetUnits={1}
              />
            ) : (
              <WallMaterial wall={wall} />
            )}
          </mesh>
        );
      })}
    </>
  );
}

/* Extracted CAD often carries stacked duplicates — the same chair/desk drawn twice at virtually
   the same spot — which read as overlapping clutter in 3D. Keep the first of any same-category
   pair whose centres sit within ~0.5 ft of each other. */
function dedupeFurniture(furniture: ExtractedFurniture[]): ExtractedFurniture[] {
  const kept: ExtractedFurniture[] = [];
  for (const f of furniture) {
    const cx = f.x + f.w / 2, cy = f.y + f.h / 2;
    const overlaps = kept.some(
      (k) => k.category === f.category && Math.hypot(k.x + k.w / 2 - cx, k.y + k.h / 2 - cy) < 0.5,
    );
    if (!overlaps) kept.push(f);
  }
  return kept;
}

function LayoutScene({ layout, floor, finish, view, wall, ceiling }: {
  layout: ExtractedLayout; floor: typeof FLOORS[number]; finish: typeof FINISHES[number];
  view: ViewMode; wall: (typeof WALLS)[number]; ceiling: CeilingType;
}) {
  const [minx, miny, maxx, maxy] = layout.bounds;
  const w = useMemo(() => worldFromBounds(minx, miny, maxx, maxy), [minx, miny, maxx, maxy]);
  const furniture = useMemo(
    () => dedupeFurniture(layout.furniture).slice(0, MAX_RENDER),
    [layout.furniture],
  );
  const wallH = view === "full" ? LAYOUT_WALL_H : DOLLHOUSE_H;
  const maxPolar = view === "full" ? Math.PI / 1.85 : Math.PI / 2.05;
  return (
    <>
      <SceneLighting size={w.size} />
      <mesh rotation-x={-Math.PI / 2} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[(maxx - minx) * 1.1, (maxy - miny) * 1.1]} />
        <meshStandardMaterial
          color={floor.color}
          roughness={floor.roughness}
          metalness={0}
          envMapIntensity={0.4}
          side={THREE.DoubleSide}
        />
      </mesh>
      <LayoutWalls layout={layout} w={w} wall={wall} wallH={wallH} />
      {furniture.map((f, i) => (
        <group
          key={i}
          position={[w.wx(f.x + f.w / 2), 0, w.wz(f.y + f.h / 2)]}
          rotation-y={(-f.rotation * Math.PI) / 180}
        >
          <CategoryPiece f={f} finish={finish.color} />
        </group>
      ))}
      {view === "full" && (
        <Ceiling width={(maxx - minx) * 1.1} depth={(maxy - miny) * 1.1} height={LAYOUT_WALL_H} type={ceiling} />
      )}
      <ContactShadows frames={1} resolution={1024} position={[0, 0.02, 0]} scale={w.size * 2.4} blur={2.5} opacity={0.52} far={22} />
      <OrbitControls makeDefault enablePan target={[0, 0, 0]} maxPolarAngle={maxPolar} minDistance={view === "full" ? 4 : 20} />
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

function Scene({ plan, instances, floor, finish, view, wall, ceiling }: {
  plan: Plan; instances: Instance[]; floor: typeof FLOORS[number]; finish: typeof FINISHES[number];
  view: ViewMode; wall: (typeof WALLS)[number]; ceiling: CeilingType;
}) {
  const w = useWorld(plan);
  const wallH = view === "full" ? LAYOUT_WALL_H : WALL_H;
  const maxPolar = view === "full" ? Math.PI / 1.85 : Math.PI / 2.05;
  const ceilDims = useMemo(() => {
    const xs = plan.boundary.map((p) => p[0]);
    const ys = plan.boundary.map((p) => p[1]);
    return { width: (Math.max(...xs) - Math.min(...xs)) * 1.02, depth: (Math.max(...ys) - Math.min(...ys)) * 1.02 };
  }, [plan]);
  return (
    <>
      <SceneLighting size={w.size} />
      <Floor plan={plan} w={w} finish={floor} />
      <Walls plan={plan} w={w} wall={wall} wallH={wallH} />
      {plan.columns.map(([x, y], i) => (
        <mesh key={`c${i}`} position={[w.wx(x), wallH / 2, w.wz(y)]} castShadow>
          <cylinderGeometry args={[0.8, 0.8, wallH, 16]} />
          <meshStandardMaterial color="#d6d0c0" roughness={0.7} />
        </mesh>
      ))}
      {instances.slice(0, MAX_RENDER).map((it, i) => (
        <group key={i} position={[w.wx(it.x + it.w / 2), 0, w.wz(it.y + it.h / 2)]}>
          <Piece it={it} finish={finish.color} />
        </group>
      ))}
      {view === "full" && (
        <Ceiling width={ceilDims.width} depth={ceilDims.depth} height={LAYOUT_WALL_H} type={ceiling} />
      )}
      <ContactShadows frames={1} resolution={1024} position={[0, 0.02, 0]} scale={w.size * 2.4} blur={2.5} opacity={0.52} far={22} />
      <OrbitControls makeDefault enablePan target={[0, 0, 0]} maxPolarAngle={maxPolar} minDistance={view === "full" ? 4 : 20} />
    </>
  );
}

type SpaceViewProps = { plan: Plan; instances: Instance[] } | { layout: ExtractedLayout };

export default function SpaceView(props: SpaceViewProps) {
  const [floor, setFloor] = useState(FLOORS[0]);
  const [finish, setFinish] = useState(FINISHES[0]);
  const [view, setView] = useState<ViewMode>("cutaway");
  const [wall, setWall] = useState(WALLS[0]);
  const [ceiling, setCeiling] = useState<CeilingType>(CEILINGS[0]);
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
          shadows="soft"
          gl={{ preserveDrawingBuffer: true, antialias: true, toneMappingExposure: 1.05 }}
          camera={{ position: [size * 0.92, size * 0.5, size * 0.96], fov: 32 }}
          dpr={[1, 2]}
        >
          <CameraRig view={view} size={size} />
          {"layout" in props ? (
            <LayoutScene layout={props.layout} floor={floor} finish={finish} view={view} wall={wall} ceiling={ceiling} />
          ) : (
            <Scene plan={props.plan} instances={props.instances} floor={floor} finish={finish} view={view} wall={wall} ceiling={ceiling} />
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
        <div className="mat-group">
          <span className="ds-eyebrow">View</span>
          <Segmented<ViewMode>
            options={[{ value: "cutaway", label: "Cutaway" }, { value: "full", label: "Full height" }]}
            value={view}
            onChange={setView}
          />
        </div>
        <div className="mat-group">
          <span className="ds-eyebrow">Walls</span>
          <div className="sw-row">
            {WALLS.map((wm) => (
              <button key={wm.name} title={wm.name} aria-label={`${wm.name} walls`} aria-pressed={wall.name === wm.name}
                className={`sw ${wall.name === wm.name ? "on" : ""}`} style={{ background: wm.color }} onClick={() => setWall(wm)} />
            ))}
          </div>
        </div>
        <div className="mat-group">
          <span className="ds-eyebrow">Ceiling</span>
          <Segmented<CeilingType>
            options={[
              { value: "Open", label: "Open" },
              { value: "Acoustic", label: "Acoustic" },
              { value: "Drywall", label: "Drywall" },
              { value: "Wood slat", label: "Slat" },
            ]}
            value={ceiling}
            onChange={setCeiling}
          />
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
