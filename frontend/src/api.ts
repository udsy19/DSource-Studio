import type { TestFitResponse } from "./types";

export async function generateTestFit(file: File): Promise<TestFitResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/testfit/quote", { method: "POST", body: fd });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

// Render status — whether a provider key is configured, so the UI can gate the Visualize action.
export async function renderStatus(): Promise<{ configured: boolean; provider: string; model: string | null }> {
  const res = await fetch("/api/render/status");
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

export async function renderView(
  image: string,
  finishes?: Record<string, string>,
): Promise<{ image: string | null }> {
  const res = await fetch("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(finishes ? { image, finishes } : { image }),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export async function ingestCad(file: File): Promise<import("./types").ExtractedLayout> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/ingest/cad", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

interface AltOpts {
  headcount?: number;
  density_rsf_per_person?: number;
}

function planForm(file: File, opts?: AltOpts): FormData {
  const fd = new FormData();
  fd.append("file", file);
  if (opts?.headcount != null) fd.append("headcount", String(opts.headcount));
  if (opts?.density_rsf_per_person != null)
    fd.append("density_rsf_per_person", String(opts.density_rsf_per_person));
  return fd;
}

async function downloadBlob(res: Response, filename: string): Promise<void> {
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export async function generateAlternatives(
  file: File,
  opts?: AltOpts,
): Promise<import("./types").AlternativesResponse> {
  const res = await fetch("/api/testfit/alternatives", { method: "POST", body: planForm(file, opts) });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Concept mode: generate scored test-fit VERSIONS from a plate + a simple brief.
// Same response shape as generateAlternatives; the brief drives the layout.
export async function generateFromConcept(
  file: File,
  concept: import("./types").ConceptProgram,
): Promise<import("./types").AlternativesResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("planning_style", concept.planning_style);
  fd.append("desk_type", concept.desk_type);
  fd.append("desk_width_cm", String(concept.desk_width_cm));
  fd.append("desk_depth_cm", String(concept.desk_depth_cm));
  fd.append("closed_ratio", String(concept.closed_ratio));
  const res = await fetch("/api/generate", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Detailed mode: explicit room-type counts + placement per type drive the layout.
// Same response shape as generateFromConcept; program is sent as a JSON string.
export async function generateDetailed(
  file: File,
  program: import("./types").DetailedProgram,
): Promise<import("./types").AlternativesResponse> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("program", JSON.stringify(program));
  const res = await fetch("/api/generate/detailed", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Iterate loop: regenerate Detailed versions from the prior version's plan, keeping pinned rooms.
export async function iterateDetailed(body: {
  plan: import("./types").Plan;
  program: import("./types").DetailedProgram;
  locked: import("./types").Instance[];
}): Promise<import("./types").AlternativesResponse> {
  const res = await fetch("/api/generate/detailed/iterate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Qbiq-grade takeoff from the REAL extracted layout (the multi-sheet workbook).
export async function downloadLayoutTakeoff(file: File): Promise<void> {
  const fd = new FormData();
  fd.append("file", file);
  await downloadBlob(
    await fetch("/api/ingest/takeoff", { method: "POST", body: fd }),
    "quantity-takeoff.xlsx",
  );
}

// Takeoff from an already-extracted layout (an adopted generated version) — JSON body, not a file.
export async function downloadTakeoffFromLayout(
  layout: import("./types").ExtractedLayout,
): Promise<void> {
  await downloadBlob(
    await fetch("/api/layout/takeoff", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(layout),
    }),
    "quantity-takeoff.xlsx",
  );
}

export interface BomLine {
  brand: string;
  model: string;
  description: string;
  category: string;
  qty: number;
  unit_price: number;
  line_total: number;
}
export interface Bom {
  lines: BomLine[];
  total: number;
  priced_items: number;
  unpriced_items: number;
  currency: string;
}

// Priced bill of materials from a layout's furniture (real SKUs + list prices where present).
export async function fetchLayoutBom(layout: import("./types").ExtractedLayout): Promise<Bom> {
  const res = await fetch("/api/layout/bom", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(layout),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Live seat/density metrics for an edited layout — re-scored after a move / delete / swap.
export async function fetchLayoutMetrics(
  layout: import("./types").ExtractedLayout,
): Promise<import("./types").LayoutMetrics> {
  const res = await fetch("/api/layout/metrics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(layout),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Piece-swap alternatives for a furniture category (real SKUs to drop in for one item).
export async function fetchProducts(category: string): Promise<import("./types").Product[]> {
  const res = await fetch(`/api/library/products?category=${encodeURIComponent(category)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

// Room-swap alternatives — Steelcase settings that fit within the selected room's footprint.
export async function fetchSettings(
  type: string,
  maxW: number,
  maxH: number,
): Promise<import("./types").CatalogSetting[]> {
  const q = new URLSearchParams({ type, max_w: String(maxW), max_h: String(maxH) });
  const res = await fetch(`/api/library/settings?${q}`);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export interface SymbolGeometry {
  outline: [number, number][][]; // real plan polylines (feet), re-based to the shape's min-corner
  w: number;
  h: number;
}

// Real per-SKU plan geometry from the product-model library (empty outline -> footprint fallback).
export async function fetchGeometry(sku: string): Promise<SymbolGeometry> {
  const res = await fetch(`/api/library/geometry?sku=${encodeURIComponent(sku)}`);
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function downloadIfc(file: File, opts?: AltOpts): Promise<void> {
  await downloadBlob(
    await fetch("/api/testfit/ifc", { method: "POST", body: planForm(file, opts) }),
    "model.ifc",
  );
}

// Export a SELECTED generated version directly from its plan + fit (no regeneration).
type FitExport = { plan: import("./types").Plan; testfit: import("./types").Alternative["testfit"] };

async function postFit(path: string, body: FitExport, filename: string): Promise<void> {
  await downloadBlob(
    await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    filename,
  );
}

export const downloadTakeoffFromFit = (b: FitExport) =>
  postFit("/api/testfit/takeoff-from-fit", b, "quantity-takeoff.xlsx");
export const downloadIfcFromFit = (b: FitExport) =>
  postFit("/api/testfit/ifc-from-fit", b, "model.ifc");
export const downloadDxfFromFit = (b: FitExport) =>
  postFit("/api/testfit/dxf-from-fit", b, "test-fit.dxf");

export async function downloadReport(reportData: {
  project: import("./types").ReportProject;
  plan: import("./types").Plan;
  alternatives: import("./types").Alternative[];
}): Promise<void> {
  await downloadBlob(
    await fetch("/api/testfit/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(reportData),
    }),
    "space-planning-report.pdf",
  );
}

export const num = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });

// Currency-aware money formatter — honours the BOM's `currency` field (Steelcase list prices are
// USD; the India track will emit INR) instead of a hardcoded '$'.
export const money = (n: number, currency = "USD") =>
  new Intl.NumberFormat(currency === "INR" ? "en-IN" : "en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);
