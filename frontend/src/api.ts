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

export async function renderView(image: string, prompt?: string): Promise<{ image: string | null }> {
  const res = await fetch("/api/render", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(prompt ? { image, prompt } : { image }),
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

export async function cadSvg(file: File): Promise<{ svg: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/cad/svg", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function sourceIndia(
  counts: Record<string, number>,
): Promise<import("./types").IndiaSource> {
  const res = await fetch("/api/source/india", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ counts }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function matchProduct(
  text: string,
  k = 3,
): Promise<import("./types").MatchResult[]> {
  const res = await fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, k }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return (await res.json()).results ?? [];
}

export async function cadGeometry(file: File): Promise<import("./types").CadGeometry> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/cad/geometry", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
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

export async function downloadTakeoff(file: File, opts?: AltOpts): Promise<void> {
  await downloadBlob(
    await fetch("/api/testfit/takeoff", { method: "POST", body: planForm(file, opts) }),
    "quantity-takeoff.xlsx",
  );
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

export async function downloadIfc(file: File, opts?: AltOpts): Promise<void> {
  await downloadBlob(
    await fetch("/api/testfit/ifc", { method: "POST", body: planForm(file, opts) }),
    "model.ifc",
  );
}

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

export const inr = (n: number, frac = 0) =>
  n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: frac });

export const num = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
