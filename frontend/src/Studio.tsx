import { useState } from "react";
import { cadGeometry, cadSvg, generateTestFit, num, usd } from "./api";
import { Cad3D, CadSvg } from "./components/CadViewer";
import Dropzone from "./components/Dropzone";
import PlanCanvas from "./components/PlanCanvas";
import Procurement from "./components/Procurement";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented, Stat } from "./design/ui";
import type { CadGeometry, TestFitResponse } from "./types";

const LEGEND = [
  { k: "Workstation", c: "rgba(184,85,47,0.5)", f: "rgba(184,85,47,0.11)" },
  { k: "Office", c: "rgba(26,24,19,0.34)", f: "rgba(26,24,19,0.045)" },
  { k: "Meeting", c: "rgba(26,24,19,0.4)", f: "rgba(26,24,19,0.07)" },
  { k: "Collab", c: "rgba(184,85,47,0.34)", f: "rgba(184,85,47,0.05)" },
];

export default function Studio() {
  const [res, setRes] = useState<TestFitResponse | null>(null);
  const [cad, setCad] = useState<{ svg: string; geometry: CadGeometry } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [mode, setMode] = useState<"plan" | "space">("plan");

  async function handle(file: File) {
    setBusy(true);
    setErr(null);
    setCad(null);
    try {
      // Render the user's ACTUAL drawing (CAD svg + geometry) AND run the analysis (test-fit).
      const [tf, svg, geo] = await Promise.all([
        generateTestFit(file),
        cadSvg(file).catch(() => null),
        cadGeometry(file).catch(() => null),
      ]);
      setRes(tf);
      if (svg && geo) setCad({ svg: svg.svg, geometry: geo });
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
      setRes(null);
    } finally {
      setBusy(false);
    }
  }

  const tf = res?.testfit;
  const q = res?.quote;

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

            {q && (
              <>
                <hr className="ds-rule" />
                <div className="quote">
                  <div className="total">
                    <small>Source · budgetary total</small>
                    {usd(q.total)}
                  </div>
                  {res.bom && (() => {
                    const all = res.bom.reduce((s, b) => s + b.qty * b.unit_list, 0);
                    const real = res.bom.filter((b) => b.real).reduce((s, b) => s + b.qty * b.unit_list, 0);
                    const pct = all ? Math.round((real / all) * 100) : 0;
                    return <div className="realbar"><span className="fill" style={{ width: `${pct}%` }} />
                      <em>{pct}% from real published prices</em></div>;
                  })()}
                  <div className="rows">
                    <Row k="List" n={usd(q.subtotal_list)} />
                    <Row k="Net (after discount)" n={usd(q.net_merchandise)} />
                    <Row k="Install" n={usd(q.install)} />
                    <Row k="Freight" n={usd(q.freight)} />
                    <Row k="Tax" n={usd(q.tax)} />
                  </div>
                  <Callout>
                    Budgetary — list minus the dealer’s standard discount, plus install, freight and
                    tax. A dealer confirms the firm number.
                  </Callout>
                </div>
              </>
            )}

            {res.bom && res.bom.length > 0 && (
              <>
                <hr className="ds-rule" />
                <div>
                  <Eyebrow style={{ display: "block", marginBottom: 14 }}>Source · bill of materials</Eyebrow>
                  <div className="bom">
                    {res.bom.map((b, i) => (
                      <div className="item" key={i}>
                        <div className="q">{num(b.qty)}</div>
                        <div className="nm">
                          {b.name}
                          <span className="sku">
                            {b.sku}
                            <em className={`prov ${b.real ? "real" : "est"}`}>
                              {b.real ? "real" : "est."}
                            </em>
                          </span>
                        </div>
                        <div className="pr">{usd(b.unit_list)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}

            {res.bom && res.bom.length > 0 && (
              <>
                <hr className="ds-rule" />
                <Procurement bom={res.bom} />
              </>
            )}
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
