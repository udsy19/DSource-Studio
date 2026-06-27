import { useState } from "react";
import {
  cadGeometry,
  cadSvg,
  downloadIfc,
  downloadReport,
  downloadTakeoff,
  generateAlternatives,
  generateTestFit,
  inr,
  num,
  sourceIndia,
} from "./api";
import { Cad3D, CadSvg } from "./components/CadViewer";
import Dropzone from "./components/Dropzone";
import PlanCanvas from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented, Stat } from "./design/ui";
import type { CadGeometry, IndiaSource, TestFitResponse } from "./types";

const LEGEND = [
  { k: "Workstation", c: "rgba(184,85,47,0.5)", f: "rgba(184,85,47,0.11)" },
  { k: "Office", c: "rgba(26,24,19,0.34)", f: "rgba(26,24,19,0.045)" },
  { k: "Meeting", c: "rgba(26,24,19,0.4)", f: "rgba(26,24,19,0.07)" },
  { k: "Collab", c: "rgba(184,85,47,0.34)", f: "rgba(184,85,47,0.05)" },
];

export default function Studio() {
  const [res, setRes] = useState<TestFitResponse | null>(null);
  const [cad, setCad] = useState<{ svg: string; geometry: CadGeometry } | null>(null);
  const [source, setSource] = useState<IndiaSource | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"plan" | "space">("plan");
  const [file, setFile] = useState<File | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  async function handle(file: File) {
    setBusy(true);
    setErr(null);
    setCad(null);
    setSource(null);
    setFile(file);
    try {
      // Render the user's ACTUAL drawing (CAD svg + geometry) AND run the analysis (test-fit).
      const [tf, svg, geo] = await Promise.all([
        generateTestFit(file),
        cadSvg(file).catch(() => null),
        cadGeometry(file).catch(() => null),
      ]);
      setRes(tf);
      if (svg && geo) setCad({ svg: svg.svg, geometry: geo });
      // Source the test-fit's furniture to REAL India catalog SKUs (INR). Runs after; the
      // first call warms the embedder so it may take a moment.
      const c = tf.testfit;
      sourceIndia({
        workstation: c.workstation_count,
        private_office: c.office_count ?? 0,
        meeting_room: c.meeting_count ?? 0,
        collaboration: c.collab_count ?? 0,
      }).then(setSource).catch(() => setSource(null));
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
      setRes(null);
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
    // The PDF report compares three fitted options; generate them, then render the report.
    const alts = await generateAlternatives(file);
    await downloadReport({
      project: { client: "", building: file.name.replace(/\.(dxf|dwg)$/i, ""), style: "Modern", floor: "" },
      plan: alts.plan,
      alternatives: alts.alternatives,
    });
  }

  const tf = res?.testfit;

  return (
    <main className="studio">
      <section className="stage">
        {res ? (
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
            {cad ? (
              mode === "plan" ? <CadSvg svg={cad.svg} /> : <Cad3D geometry={cad.geometry} />
            ) : mode === "plan" ? (
              <>
                <PlanCanvas plan={res.plan} instances={res.testfit.instances} />
                <div className="legend">
                  {LEGEND.map((l) => (
                    <span key={l.k}>
                      <i style={{ borderColor: l.c, background: l.f }} />
                      {l.k}
                    </span>
                  ))}
                </div>
              </>
            ) : (
              <SpaceView plan={res.plan} instances={res.testfit.instances} />
            )}
          </>
        ) : (
          <div className="empty">
            <div className="glyph">⌟</div>
            <p>
              Drop a floor plate. DSource Studio designs the test-fit, scores it for wellbeing, and
              sources it to a budgetary number — in one pass.
            </p>
          </div>
        )}
      </section>

      <aside className="panel">
        <Dropzone busy={busy} onFile={handle} />
        {err && <div className="err">{err}</div>}

        {res && tf && (
          <>
            <div>
              <Eyebrow style={{ display: "block", marginBottom: 16 }}>Design · the test-fit</Eyebrow>
              <div className="stats">
                {[
                  { v: num(res.plan.usable_area_sf), k: "usable sf" },
                  { v: tf.workstation_count, k: "workstations" },
                  { v: tf.office_count ?? 0, k: "offices" },
                  { v: tf.meeting_count ?? 0, k: "meeting rooms" },
                  { v: tf.collab_count ?? 0, k: "collab zones" },
                  { v: res.plan.columns.length, k: "columns" },
                ].map((s, i) => (
                  <div key={s.k} style={{ animation: "rise .6s ease both", animationDelay: `${i * 55}ms` }}>
                    <Stat value={s.v} label={s.k} />
                  </div>
                ))}
              </div>
            </div>

            {res.wellbeing && (
              <>
                <hr className="ds-rule" />
                <div className="wellbeing">
                  <div className="wb-head">
                    <div>
                      <Eyebrow>Wellbeing · by design</Eyebrow>
                      <div className="wb-overall">
                        {res.wellbeing.overall}
                        <small>/100</small>
                      </div>
                    </div>
                    <Ring value={res.wellbeing.overall} />
                  </div>
                  <div className="wb-dims">
                    {res.wellbeing.dimensions.map((d) => (
                      <div className="wb-dim" key={d.key} title={d.basis}>
                        <div className="wb-dim-top">
                          <span>
                            {d.label}
                            {!d.measured && <em className="wb-est">≈</em>}
                          </span>
                          <span className="wb-num">{d.score}</span>
                        </div>
                        <div className={`wb-bar ${d.measured ? "" : "proxy"}`}>
                          <span style={{ width: `${d.score}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                  <p className="disclaim" style={{ marginTop: 12 }}>
                    Light, acoustics, movement &amp; social are measured from the plan; ≈ marks
                    proxies (air, ergonomics, biophilia, restoration) pending material certs + IoT sensors.
                  </p>
                </div>
              </>
            )}

            {source && (
              <>
                <hr className="ds-rule" />
                <div className="quote">
                  <div className="total">
                    <small>Source · budgetary total (India)</small>
                    {inr(source.total)}
                  </div>
                  <div className="bom">
                    {source.lines.map((l, i) => (
                      <div className="item" key={i}>
                        <div className="q">{num(l.qty)}</div>
                        <div className="nm">
                          {l.name}
                          <span className="sku">
                            {l.vendor}
                            <em className={`prov ${l.label === "exact" ? "real" : "est"}`}>{l.label}</em>
                          </span>
                        </div>
                        <div className="pr">{inr(l.unit_inr)}</div>
                      </div>
                    ))}
                  </div>
                  <div className="rows">
                    <Row k="Subtotal" n={inr(source.subtotal)} />
                    <Row k="GST" n={inr(source.gst)} />
                    <Row k="Total" n={inr(source.total)} />
                  </div>
                  {source.unmatched.length > 0 && (
                    <Callout>
                      {source.unmatched.length} item type(s) have no real catalog match yet — left
                      unpriced rather than estimated.
                    </Callout>
                  )}
                  <Callout>
                    Priced from real India catalog SKUs (INR + GST). Multi-vendor sourcing &amp;
                    comparison arrive with the vendor layer (Phase 5).
                  </Callout>
                </div>
              </>
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
                  onClick={() => runExport("takeoff", () => downloadTakeoff(file!))}
                  disabled={!!exporting}
                >
                  <span className="export-btn-label">Quantity takeoff</span>
                  <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · BOM"}</span>
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
              <p className="disclaim" style={{ marginTop: 14 }}>
                The report compares three fitted options; the takeoff prices every line against the
                real catalog (real vs. estimated flagged); the IFC opens in any BIM tool.
              </p>
            </div>
          </>
        )}
      </aside>
    </main>
  );
}

function Row({ k, n }: { k: string; n: string }) {
  return (
    <div className="row">
      <span className="k">{k}</span>
      <span className="n">{n}</span>
    </div>
  );
}

function Ring({ value }: { value: number }) {
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <svg width="64" height="64" viewBox="0 0 64 64" className="wb-ring">
      <circle cx="32" cy="32" r={r} fill="none" stroke="var(--line)" strokeWidth="5" />
      <circle
        cx="32" cy="32" r={r} fill="none" stroke="var(--accent)" strokeWidth="5"
        strokeDasharray={c} strokeDashoffset={c * (1 - value / 100)} strokeLinecap="round"
        transform="rotate(-90 32 32)"
      />
    </svg>
  );
}
