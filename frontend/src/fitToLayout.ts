// Adopt a generated test-fit as a read-layout: synthesize the ExtractedLayout (walls, rooms,
// furniture, inventory) the same shape ingestCad produces, so a generated design flows into the
// full read-layout view (2D LayoutPlan, 3D LayoutScene, inventory) with no re-ingest.
//
// The generation models each enclosed program element as ONE instance footprint (a
// private_office instance IS the office room, not a desk), so those become ROOMS with synthesized
// partitions; open-plan workstations become workstation furniture.

import type {
  ExtractedDoor,
  ExtractedFurniture,
  ExtractedLayout,
  ExtractedRoom,
  ExtractedWall,
  FurnitureCategory,
  Instance,
  Plan,
  WallType,
} from "./types";

// instance type -> how it reads once adopted (room label/type + the partition material)
const ROOM_META: Record<string, { label: string; type: string; wall: WallType }> = {
  private_office: { label: "Office", type: "office", wall: "drywall" },
  meeting_room: { label: "Meeting", type: "meeting", wall: "glass" },
  collaboration: { label: "Collaboration", type: "collab", wall: "glass" },
  phone_booth: { label: "Phone Booth", type: "phone", wall: "glass" },
  reception: { label: "Reception", type: "amenity", wall: "drywall" },
  kitchen: { label: "Kitchen", type: "amenity", wall: "drywall" },
  wellness: { label: "Wellness", type: "amenity", wall: "drywall" },
  copy_print: { label: "Copy / Print", type: "amenity", wall: "drywall" },
  storage: { label: "Storage", type: "amenity", wall: "drywall" },
};

const closeRing = (pts: [number, number][]): [number, number][] => {
  const [a, b] = [pts[0], pts[pts.length - 1]];
  return pts.length > 1 && (a[0] !== b[0] || a[1] !== b[1]) ? [...pts, pts[0]] : pts;
};

// rotate a point about a centre by `deg` degrees (engine convention — shared by corners,
// in-room furniture, and door placement so the trig lives in one place)
const rotatePoint = (
  x: number,
  y: number,
  cx: number,
  cy: number,
  deg: number,
): [number, number] => {
  const rad = (deg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  const dx = x - cx;
  const dy = y - cy;
  return [cx + dx * cos - dy * sin, cy + dx * sin + dy * cos];
};

// the 4 footprint corners rotated about the centre (degrees — matches the engine's convention)
const corners = (it: Instance): [number, number][] => {
  const cx = it.x + it.w / 2;
  const cy = it.y + it.h / 2;
  const raw: [number, number][] = [
    [it.x, it.y],
    [it.x + it.w, it.y],
    [it.x + it.w, it.y + it.h],
    [it.x, it.y + it.h],
  ];
  return raw.map(([x, y]) => rotatePoint(x, y, cx, cy, it.rotation));
};

// one or two representative items per enclosed instance type — sized as fractions of the room
// footprint (a sensible default, NOT read from a real drawing). Each spec is a centred sub-box:
// fractional size + fractional offset from the room centre, BEFORE the instance rotation.
type ItemSpec = {
  category: FurnitureCategory;
  // absolute size in ft when fixed; or fractional (× room w/h) when null
  w?: number;
  h?: number;
  fw?: number;
  fh?: number;
  // offset of the sub-box centre from the room centre, as a fraction of room w/h
  ox?: number;
  oy?: number;
};

const FURNITURE_BY_TYPE: Record<string, ItemSpec[]> = {
  private_office: [
    { category: "desk", w: 5, h: 2.5, oy: -0.12 },
    { category: "chair", w: 1.8, h: 1.8, oy: 0.18 },
  ],
  meeting_room: [{ category: "table", fw: 0.55, fh: 0.45 }],
  collaboration: [{ category: "sofa", fw: 0.6, fh: 0.35 }],
  phone_booth: [{ category: "stool", w: 1.4, h: 1.4 }],
  reception: [{ category: "desk", w: 5, h: 2.5 }],
  kitchen: [{ category: "storage", fw: 0.7, fh: 0.3, oy: -0.3 }],
  wellness: [{ category: "sofa", fw: 0.6, fh: 0.35 }],
  copy_print: [{ category: "storage", fw: 0.6, fh: 0.3, oy: -0.3 }],
  storage: [{ category: "storage", fw: 0.6, fh: 0.3, oy: -0.3 }],
};

// place a centred sub-box inside the room, rotate it about the room centre by the instance
// rotation, and return ExtractedFurniture whose (x,y) is the rotated bounding-box MIN corner —
// the form PlanCanvas consumes (translate to min corner, rotate about centre).
const itemInRoom = (it: Instance, spec: ItemSpec): ExtractedFurniture => {
  const cx = it.x + it.w / 2;
  const cy = it.y + it.h / 2;
  const margin = Math.min(it.w, it.h) * 0.16; // keep furniture clear of the partitions
  const maxW = Math.max(0.5, it.w - 2 * margin);
  const maxH = Math.max(0.5, it.h - 2 * margin);
  const w = Math.min(spec.w ?? it.w * (spec.fw ?? 0.5), maxW);
  const h = Math.min(spec.h ?? it.h * (spec.fh ?? 0.5), maxH);
  // clamp the centre offset so the sub-box stays within the margin-inset interior
  const slackX = (maxW - w) / 2;
  const slackY = (maxH - h) / 2;
  const offX = Math.max(-slackX, Math.min(slackX, it.w * (spec.ox ?? 0)));
  const offY = Math.max(-slackY, Math.min(slackY, it.h * (spec.oy ?? 0)));
  const scx = cx + offX;
  const scy = cy + offY;
  // axis-aligned corners about the sub-box centre, then rotate each about the room centre
  const rotated = [
    [scx - w / 2, scy - h / 2],
    [scx + w / 2, scy - h / 2],
    [scx + w / 2, scy + h / 2],
    [scx - w / 2, scy + h / 2],
  ].map(([x, y]) => rotatePoint(x, y, cx, cy, it.rotation));
  const minX = Math.min(...rotated.map((p) => p[0]));
  const minY = Math.min(...rotated.map((p) => p[1]));
  return {
    category: spec.category,
    block_name: "",
    brand: "",
    model: "",
    x: minX,
    y: minY,
    w,
    h,
    rotation: it.rotation,
  };
};

// a 3-ft door on the room edge whose midpoint is nearest the plate centroid (perimeter rooms
// open inward), hinged at one edge end with the leaf along the wall and the arc swinging into the
// room. Matches PlanCanvas/cad_reader: leaf (0,0)->(width,0) along edge dir, arc end at world
// (x - width·sinθ, y + width·cosθ) — chosen to land inside the room.
const doorForRoom = (it: Instance, centroid: [number, number]): ExtractedDoor => {
  const cx = it.x + it.w / 2;
  const cy = it.y + it.h / 2;
  const c = corners(it); // ordered TL,TR,BR,BL (rotated)
  let best = 0;
  let bestDist = Infinity;
  for (let i = 0; i < 4; i++) {
    const a = c[i];
    const b = c[(i + 1) % 4];
    const mx = (a[0] + b[0]) / 2;
    const my = (a[1] + b[1]) / 2;
    const d = (mx - centroid[0]) ** 2 + (my - centroid[1]) ** 2;
    if (d < bestDist) {
      bestDist = d;
      best = i;
    }
  }
  const a = c[best];
  const b = c[(best + 1) % 4];
  const edgeLen = Math.hypot(b[0] - a[0], b[1] - a[1]);
  const width = Math.min(3, edgeLen);
  // unit vector along the edge from a toward b
  const ux = (b[0] - a[0]) / edgeLen;
  const uy = (b[1] - a[1]) / edgeLen;
  // rotation θ such that (cosθ,sinθ) = edge direction
  const rotation = (Math.atan2(uy, ux) * 180) / Math.PI;
  // PlanCanvas swings the arc to world (x - width·sinθ, y + width·cosθ) = +90° from the leaf.
  // Hinge at edge end `a` if that swing points toward the room centre, else hinge at `b`
  // (with the edge direction reversed) so the arc always opens inward.
  const swing: [number, number] = [-uy, ux]; // (-sinθ, cosθ) for the a→b leaf
  const towardCentreFromA = (cx - a[0]) * swing[0] + (cy - a[1]) * swing[1];
  if (towardCentreFromA >= 0) {
    return { x: a[0], y: a[1], width, rotation };
  }
  // hinge at b, leaf points b→a; its swing (-(-uy), -ux) = (uy, -ux) opens the other way inward
  const revRotation = (Math.atan2(-uy, -ux) * 180) / Math.PI;
  return { x: b[0], y: b[1], width, rotation: revRotation };
};

export function layoutFromFit(plan: Plan, instances: Instance[]): ExtractedLayout {
  const xs = plan.boundary.map((p) => p[0]);
  const ys = plan.boundary.map((p) => p[1]);
  const bounds: [number, number, number, number] = [
    Math.min(...xs),
    Math.min(...ys),
    Math.max(...xs),
    Math.max(...ys),
  ];

  const walls: ExtractedWall[] = [{ type: "perimeter", points: closeRing(plan.boundary) }];
  for (const core of plan.cores) walls.push({ type: "core", points: closeRing(core) });

  const centroid: [number, number] = [
    xs.reduce((s, v) => s + v, 0) / xs.length,
    ys.reduce((s, v) => s + v, 0) / ys.length,
  ];

  const rooms: ExtractedRoom[] = [];
  const furniture: ExtractedFurniture[] = [];
  const doors: ExtractedDoor[] = [];
  const inventory: Record<string, number> = {};

  // When the Steelcase library slotted real furniture into the rooms, those pieces ARE the
  // furniture — adopt them as-is and skip the synthetic representative items.
  const hasSlotted = instances.some((it) => it.slotted);

  let roomN = 0;
  for (const it of instances) {
    if (it.slotted) {
      const category = it.type as FurnitureCategory; // slotted type is the furniture category
      furniture.push({
        category, block_name: "", brand: it.brand ?? "", model: it.model ?? "",
        list_price: it.list_price ?? null,
        x: it.x, y: it.y, w: it.w, h: it.h, rotation: it.rotation,
      });
      inventory[category] = (inventory[category] ?? 0) + 1;
      continue;
    }
    if (it.type === "workstation") {
      furniture.push({
        category: "workstation", block_name: "", brand: "", model: "",
        x: it.x, y: it.y, w: it.w, h: it.h, rotation: it.rotation,
      });
      inventory.workstation = (inventory.workstation ?? 0) + 1;
      continue;
    }
    const meta = ROOM_META[it.type] ?? { label: it.type, type: "room", wall: "drywall" as WallType };
    const poly = corners(it);
    walls.push({ type: meta.wall, points: closeRing(poly) });
    rooms.push({
      id: `r${roomN++}`,
      label: meta.label,
      area_sf: Math.round(it.w * it.h),
      polygon: poly,
      center: [it.x + it.w / 2, it.y + it.h / 2],
      type: meta.type,
    });

    if (!hasSlotted) {
      for (const spec of FURNITURE_BY_TYPE[it.type] ?? []) {
        furniture.push(itemInRoom(it, spec));
        inventory[spec.category] = (inventory[spec.category] ?? 0) + 1;
      }
    }
    doors.push(doorForRoom(it, centroid));
  }

  return {
    source: "generated",
    units: plan.units || "ft",
    bounds,
    walls,
    doors,
    rooms,
    furniture,
    inventory,
    needs_confirmation: false,
    notes: [
      "Adopted from a generated test-fit. Rooms and partitions are synthesized from the placed " +
        "program; open-plan desks read as workstation furniture. Each enclosed room is given a " +
        "door swinging inward, and 1–2 representative furniture items — a sensible default, not " +
        "read from a real drawing.",
    ],
  };
}
