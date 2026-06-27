export type InstanceType =
  | "workstation"
  | "private_office"
  | "meeting_room"
  | "collaboration";

export interface Instance {
  type: InstanceType;
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
}

export interface Plan {
  boundary: [number, number][];
  cores: [number, number][][];
  columns: [number, number][];
  gross_area_sf: number;
  usable_area_sf: number;
  units: string;
}

export interface TestFit {
  instances: Instance[];
  workstation_count: number;
  office_count?: number;
  meeting_count?: number;
  collab_count?: number;
  placeable_area_sf: number;
  notes?: string[];
}

export interface BomLine {
  type?: string;
  sku: string;
  name: string;
  manufacturer_code?: string;
  qty: number;
  unit_list: number;
  real?: boolean;
  source?: string;
}

export interface Quote {
  subtotal_list: number;
  net_merchandise: number;
  install: number;
  freight: number;
  tax: number;
  total: number;
  is_budgetary: boolean;
}

export interface WellbeingDimension {
  key: string;
  label: string;
  score: number;
  basis: string;
  measured: boolean;
}

export interface Wellbeing {
  overall: number;
  dimensions: WellbeingDimension[];
  notes: string[];
}

export interface CadPath {
  pts: [number, number][];
  layer: string;
  closed: boolean;
  wall: boolean;
}

export interface CadGeometry {
  units: string;
  path_count: number;
  truncated: boolean;
  bounds: { minx: number; miny: number; maxx: number; maxy: number } | null;
  layers: Record<string, number>;
  paths: CadPath[];
}

export interface Elements {
  furniture: { chairs: number; desks: number; tables: number; sofas: number; ottomans: number };
  spaces: {
    workstations: number;
    private_offices: number;
    meeting_rooms: number;
    huddle_spaces: number;
  };
  construction: { perimeter_walls: number; room_partitions: number; walls: number };
}

export interface TestFitResponse {
  plan: Plan;
  testfit: TestFit;
  elements?: Elements;
  wellbeing?: Wellbeing;
  bom?: BomLine[];
  quote?: Quote;
}

export type MatchLabel = "exact" | "close" | "no_match";

export interface MaintenanceAxis {
  score: number;
  basis: "measured_standard" | "derived_proxy" | "estimated";
  standard_ref: string;
  rationale: string;
}

export interface SourceLine {
  need: string;
  for_type: string;
  qty: number;
  sku: string;
  name: string;
  vendor: string;
  unit_inr: number;
  gst_rate: number;
  line_inr: number;
  label: MatchLabel;
  material: string | null;
}

export interface IndiaSource {
  currency: string;
  lines: SourceLine[];
  unmatched: { need: string; for_type: string; qty: number }[];
  subtotal: number;
  gst: number;
  total: number;
}

export interface MatchResult {
  product_id: number;
  sku: string;
  name: string;
  category: string;
  vendor: string;
  price_inr: number | null;
  gst_rate: number | null;
  image_url: string | null;
  url: string | null;
  score: number;
  label: MatchLabel;
  flagged_fields: string[];
  material: string | null;
  enrichment: Record<string, { value: string | null; confidence: number; source: string }> | null;
  maintenance: Record<string, MaintenanceAxis> | null;
}

// Space-planning deliverables (Qbiq-style: 3 scored test-fit alternatives per plate).
export interface Metrics {
  usf: number;
  seats: number;
  open_space_seats: number;
  offices: number;
  conf_rooms: number;
  density_sf_per_person: number;
  daylight_pct: number; // 0..1
  privacy_pct: number; // 0..1
  efficiency_pct: number; // 0..1
}

export interface Alternative {
  id: string;
  testfit: { instances: Instance[] };
  metrics: Metrics;
}

export interface AlternativesResponse {
  plan: Plan;
  alternatives: Alternative[];
}

export interface ReportProject {
  client: string;
  building: string;
  style: string;
  floor: string;
}

// ── Extracted layout (the user's REAL CAD layout) — from POST /api/ingest/cad ──
export type WallType =
  | "drywall"
  | "half_drywall"
  | "glass"
  | "core"
  | "perimeter"
  | "door"
  | "unknown";

export type FurnitureCategory =
  | "chair"
  | "desk"
  | "workstation"
  | "table"
  | "sofa"
  | "stool"
  | "tv"
  | "storage"
  | "planter"
  | "panel"
  | "mullion"
  | "other";

export interface ExtractedWall {
  points: [number, number][];
  type: WallType;
}

export interface ExtractedDoor {
  x: number;
  y: number;
  width: number;
  rotation: number;
}

export interface ExtractedRoom {
  id: string;
  label: string;
  area_sf: number;
  polygon: [number, number][];
  type: string;
}

export interface ExtractedFurniture {
  category: FurnitureCategory;
  block_name: string;
  brand: string;
  model: string;
  x: number; // bounding-box MIN corner
  y: number;
  w: number;
  h: number;
  rotation: number; // degrees, about the item's center
}

export interface ExtractedLayout {
  source: string;
  units: string;
  bounds: [number, number, number, number]; // [minx, miny, maxx, maxy]
  walls: ExtractedWall[];
  doors: ExtractedDoor[];
  rooms: ExtractedRoom[];
  furniture: ExtractedFurniture[];
  inventory: Record<string, number>;
  needs_confirmation: boolean;
  notes: string[];
}
