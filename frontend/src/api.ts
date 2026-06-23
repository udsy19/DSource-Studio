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

type ProcLine = { sku: string; qty: number; unit_list: number; manufacturer_code: string; name: string };

export async function requestRfq(lines: ProcLine[]): Promise<import("./types").RfqResponse> {
  const res = await fetch("/api/procurement/rfq", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function createPo(lines: ProcLine[], vendor_id: number): Promise<import("./types").Po> {
  const res = await fetch("/api/procurement/po", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lines, vendor_id }),
  });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function cadSvg(file: File): Promise<{ svg: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/cad/svg", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export async function cadGeometry(file: File): Promise<import("./types").CadGeometry> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch("/api/cad/geometry", { method: "POST", body: fd });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail ?? res.statusText);
  return res.json();
}

export const usd = (n: number, frac = 0) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: frac });

export const num = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 0 });
