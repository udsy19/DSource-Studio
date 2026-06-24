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

export interface VendorBid {
  vendor_id: number;
  vendor_name: string;
  city: string;
  state: string;
  lead_time_days: number;
  coverage_pct: number;
  net_total: number;
  rank: number;
  can_fulfill_all: boolean;
  uncovered_skus: string[];
}

export interface RfqResponse {
  currency: string;
  vendor_count: number;
  vendors: VendorBid[];
  is_synthetic: boolean;
  note: string;
}

export interface Po {
  po_number: string;
  currency: string;
  issued_date: string;
  vendor: { id: number; name: string; city: string; state: string };
  subtotal: number;
  tax: number;
  total: number;
  lead_time_days: number;
  delivery_window: { from: string; to: string };
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

export interface TestFitResponse {
  plan: Plan;
  testfit: TestFit;
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
