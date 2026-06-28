import { useState } from "react";
import {
  downloadIfc,
  downloadLayoutTakeoff,
  downloadReport,
  generateAlternatives,
  ingestCad,
  num,
} from "./api";
import Dropzone from "./components/Dropzone";
import PlanCanvas from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented } from "./design/ui";
import type { ExtractedLayout } from "./types";

// The component categories surfaced in the bill, in reading order; only non-zero rows render.
const INVENTORY_ROWS: { key: string; label: string }[] = [
  { key: "chair", label: "chairs" },
  { key: "workstation", label: "workstations" },
  { key: "desk", label: "desks" },
  { key: "table", label: "tables" },
  { key: "sofa", label: "lounge sofas" },
  { key: "stool", label: "stools" },
  { key: "panel", label: "glass panels" },
  { key: "storage", label: "storage" },
  { key: "tv", label: "screens" },
  { key: "planter", label: "planters" },
  { key: "door", label: "doors" },
];

export default function Studio() {
  const [layout, setLayout] = useState<ExtractedLayout | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"plan" | "space">("plan");
  const [file, setFile] = useState<File | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  async function handle(f: File) {
    setBusy(true);
    setErr(null);
    setLayout(null);
    setFile(f);
    try {
      // Read the REAL layout from the CAD — walls, rooms, and a furniture inventory straight from
      // the drawing's blocks. The 2D plan, 3D space, and inventory all read from this one object.
      setLayout(await ingestCad(f));
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  async function runExport(kind: string, fn: () => Promise<void>) {
    if (!file) return;
    setErr(null);
    setExporting(kind);
    try {
      await fn();
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setExporting(null);
    }
  }

  async function exportReport() {
    if (!file) return;
    const alts = await generateAlternatives(file);
    await downloadReport({
      project: { client: "", building: file.name.replace(/\.(dxf|dwg)$/i, ""), style: "Modern", floor: "" },
      plan: alts.plan,
      alternatives: alts.alternatives,
    });
  }

  const inv = layout?.inventory ?? {};
  const rooms = (layout?.rooms ?? []).filter((r) => r.label);

  return (
    <main className="studio">
      <section className="stage">
        {layout ? (
          <>
            <div className="stage-tools">
              <Segmented
                value={mode}
                onChange={setMode}
                options={[
                  { value: "plan", label: "Plan" },
                  { value: "space", label: "3D Space" },
                ]}
              />
            </div>
            {mode === "space" ? <SpaceView layout={layout} /> : <PlanCanvas layout={layout} />}
          </>
        ) : (
          <div className="empty">
            <div className="glyph">⌟</div>
            <p>
              Drop a floor plate. DSource Studio reads the real layout — walls by type, rooms, and a
              furniture inventory — straight from your CAD, in 2D and 3D.
            </p>
          </div>
        )}
      </section>

      <aside className="panel">
        <Dropzone busy={busy} onFile={handle} />
        {err && <div className="err">{err}</div>}

        {layout && (
          <>
            <div>
              <Eyebrow style={{ display: "block", marginBottom: 14 }}>
                Elements · bill of components
              </Eyebrow>
              <div className="el-grid">
                {INVENTORY_ROWS.filter((r) => inv[r.key]).map((r) => (
                  <ElCount key={r.key} n={inv[r.key]} k={r.label} />
                ))}
              </div>
              <p className="disclaim" style={{ marginTop: 12 }}>
                Read straight from the CAD — counted from named blocks, with brand &amp; model where
                the drawing carries it.
              </p>
            </div>

            {rooms.length > 0 && (
              <>
                <hr className="ds-rule" />
                <div>
                  <Eyebrow style={{ display: "block", marginBottom: 12 }}>
                    Rooms · {rooms.length}
                  </Eyebrow>
                  <div className="rooms-list">
                    {rooms.map((r) => (
                      <div className="room-row" key={r.id}>
                        <span className="rm-label">{r.label}</span>
                        <span className="rm-area">{r.area_sf ? `${num(r.area_sf)} sf` : "—"}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {layout.needs_confirmation && (
              <Callout quiet>
                Room boundaries are best-effort where the drawing's walls don't fully close — labels
                and counts are exact; confirm boundaries before fabrication.
              </Callout>
            )}

            <hr className="ds-rule" />
            <div className="exports">
              <Eyebrow style={{ display: "block", marginBottom: 14 }}>Export · deliverables</Eyebrow>
              <div className="export-actions">
                <button
                  className="export-btn export-btn--primary"
                  onClick={() => runExport("report", exportReport)}
                  disabled={!!exporting}
                >
                  <span className="export-btn-label">Space-planning report</span>
                  <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF · 3 options"}</span>
                </button>
                <button
                  className="export-btn"
                  onClick={() => runExport("takeoff", () => downloadLayoutTakeoff(file!))}
                  disabled={!!exporting}
                >
                  <span className="export-btn-label">Quantity takeoff</span>
                  <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · 9 sheets"}</span>
                </button>
                <button
                  className="export-btn"
                  onClick={() => runExport("ifc", () => downloadIfc(file!))}
                  disabled={!!exporting}
                >
                  <span className="export-btn-label">BIM model</span>
                  <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                </button>
              </div>
            </div>
          </>
        )}
      </aside>
    </main>
  );
}

function ElCount({ n, k }: { n: number; k: string }) {
  return (
    <div className="el-count">
      <span className="el-n">{num(n)}</span>
      <span className="el-k">{k}</span>
    </div>
  );
}
