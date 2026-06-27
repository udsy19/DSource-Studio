import { useState } from "react";

import { downloadIfc, downloadReport, downloadTakeoff, generateAlternatives } from "../api";
import { Button, Callout, Card, Eyebrow, Field, Stat } from "../design/ui";
import type { AlternativesResponse, Metrics, ReportProject } from "../types";
import Dropzone from "./Dropzone";
import PlanCanvas from "./PlanCanvas";

const pct = (x: number) => `${Math.round(x * 100)}%`;

function MetricsRow({ m }: { m: Metrics }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 12 }}>
      <Stat value={m.seats} label="Seats" accent />
      <Stat value={m.density_sf_per_person.toFixed(0)} label="Density sf/person" />
      <Stat value={m.offices} label="Offices" />
      <Stat value={m.conf_rooms} label="Conf rooms" />
      <Stat value={pct(m.daylight_pct)} label="Daylight" />
      <Stat value={pct(m.privacy_pct)} label="Privacy" />
    </div>
  );
}

export default function Deliverables() {
  const [file, setFile] = useState<File | null>(null);
  const [res, setRes] = useState<AlternativesResponse | null>(null);
  const [project, setProject] = useState<ReportProject>({
    client: "",
    building: "",
    style: "Modern",
    floor: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onFile(f: File) {
    setFile(f);
    setErr(null);
    setBusy(true);
    setRes(null);
    try {
      setRes(await generateAlternatives(f));
      setProject((p) => ({ ...p, building: p.building || f.name.replace(/\.(dxf|dwg)$/i, "") }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function download(run: () => Promise<void>) {
    setErr(null);
    try {
      await run();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  const set = (k: keyof ReportProject) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setProject((p) => ({ ...p, [k]: e.target.value }));

  return (
    <section className="stage">
      <Eyebrow>Space-planning deliverables</Eyebrow>
      <h2 style={{ margin: "8px 0 20px" }}>Upload a floor plate, get three fitted options</h2>

      <Dropzone busy={busy} onFile={onFile} />
      {err && <Callout>{err}</Callout>}

      {res && (
        <>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 18,
              marginTop: 22,
            }}
          >
            {res.alternatives.map((alt) => (
              <Card key={alt.id}>
                <Eyebrow>Alternative {alt.id}</Eyebrow>
                <PlanCanvas plan={res.plan} instances={alt.testfit.instances} />
                <MetricsRow m={alt.metrics} />
              </Card>
            ))}
          </div>

          <Card style={{ marginTop: 18 }}>
            <Eyebrow>Export deliverables</Eyebrow>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: 12,
                margin: "12px 0 18px",
              }}
            >
              <Field label="Client / landlord" value={project.client} onChange={set("client")} />
              <Field label="Building" value={project.building} onChange={set("building")} />
              <Field label="Design style" value={project.style} onChange={set("style")} />
              <Field label="Floor" value={project.floor} onChange={set("floor")} />
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
              <Button
                onClick={() =>
                  download(() =>
                    downloadReport({ project, plan: res.plan, alternatives: res.alternatives }),
                  )
                }
              >
                Space-planning report (PDF)
              </Button>
              <Button
                variant="ghost"
                disabled={!file}
                onClick={() => file && download(() => downloadTakeoff(file))}
              >
                Quantity takeoff (Excel)
              </Button>
              <Button
                variant="ghost"
                disabled={!file}
                onClick={() => file && download(() => downloadIfc(file))}
              >
                BIM model (IFC)
              </Button>
            </div>
            <p className="ds-hint" style={{ marginTop: 10 }}>
              Daylight, privacy, and efficiency are derived from the plan geometry. Takeoff prices
              are catalog list prices, flagged real vs. estimated per line.
            </p>
          </Card>
        </>
      )}
    </section>
  );
}
