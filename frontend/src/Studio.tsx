import { useState } from "react";
import {
  downloadIfc,
  downloadLayoutTakeoff,
  downloadReport,
  generateAlternatives,
  generateFromConcept,
  ingestCad,
  num,
} from "./api";
import Dropzone from "./components/Dropzone";
import PlanCanvas from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented } from "./design/ui";
import type { Alternative, ConceptProgram, ExtractedLayout, Metrics } from "./types";

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

// Concept brief option sets — labels for the user, values for the backend.
const PLANNING_STYLES: { value: ConceptProgram["planning_style"]; label: string }[] = [
  { value: "traditional", label: "Traditional" },
  { value: "modern", label: "Modern" },
  { value: "cowork", label: "Co-work" },
];
const DESK_TYPES: { value: ConceptProgram["desk_type"]; label: string }[] = [
  { value: "workstations", label: "Workstations" },
  { value: "benchings", label: "Benchings" },
];
const DESK_SIZES: { value: string; label: string; w: number; d: number }[] = [
  { value: "120x60", label: "120×60", w: 120, d: 60 },
  { value: "140x70", label: "140×70", w: 140, d: 70 },
  { value: "160x70", label: "160×70", w: 160, d: 70 },
  { value: "180x70", label: "180×70", w: 180, d: 70 },
];
const CLOSED_RATIOS = [0, 0.1, 0.2, 0.3, 0.4]; // share of seats in closed offices

const DEFAULT_CONCEPT: ConceptProgram = {
  planning_style: "modern",
  desk_type: "workstations",
  desk_width_cm: 140,
  desk_depth_cm: 70,
  closed_ratio: 0.2,
};

export default function Studio() {
  const [studioMode, setStudioMode] = useState<"read" | "generate">("read");

  // Read-layout state (the existing flow).
  const [layout, setLayout] = useState<ExtractedLayout | null>(null);
  const [file, setFile] = useState<File | null>(null);

  // Generate state (the Concept flow) — kept separate from the read-layout state.
  const [concept, setConcept] = useState<ConceptProgram>(DEFAULT_CONCEPT);
  const [versions, setVersions] = useState<{ plan: import("./types").Plan; alternatives: Alternative[] } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<"plan" | "space">("plan");
  const [exporting, setExporting] = useState<string | null>(null);

  async function readLayout(f: File) {
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

  async function generate(f: File) {
    setBusy(true);
    setErr(null);
    setVersions(null);
    setSelectedId(null);
    setFile(f);
    try {
      // Generate scored test-fit versions from the plate + the simple brief, then let the user
      // compare them side by side and open one in 2D / 3D.
      const res = await generateFromConcept(f, concept);
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
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
  const selected = versions?.alternatives.find((a) => a.id === selectedId) ?? null;

  return (
    <main className="studio">
      <section className="stage">
        {studioMode === "read" ? (
          layout ? (
            <>
              <div className="stage-tools">
                <Segmented
                  value={view}
                  onChange={setView}
                  options={[
                    { value: "plan", label: "Plan" },
                    { value: "space", label: "3D Space" },
                  ]}
                />
              </div>
              {view === "space" ? <SpaceView layout={layout} /> : <PlanCanvas layout={layout} />}
            </>
          ) : (
            <div className="empty">
              <div className="glyph">⌟</div>
              <p>
                Drop a floor plate. DSource Studio reads the real layout — walls by type, rooms, and a
                furniture inventory — straight from your CAD, in 2D and 3D.
              </p>
            </div>
          )
        ) : versions && selected ? (
          <>
            <div className="stage-tools">
              <Segmented
                value={view}
                onChange={setView}
                options={[
                  { value: "plan", label: "Plan" },
                  { value: "space", label: "3D Space" },
                ]}
              />
            </div>
            {view === "space" ? (
              <SpaceView plan={versions.plan} instances={selected.testfit.instances} />
            ) : (
              <PlanCanvas plan={versions.plan} instances={selected.testfit.instances} />
            )}
          </>
        ) : (
          <div className="empty">
            <div className="glyph">◳</div>
            <p>
              Pick a program and generate. DSource Studio lays out multiple test-fit versions on your
              plate, scores each, and lets you compare them — then open one in 2D and 3D.
            </p>
          </div>
        )}
      </section>

      <aside className="panel">
        <div className="mode-toggle">
          <Segmented
            value={studioMode}
            onChange={(m) => {
              setStudioMode(m);
              setErr(null);
            }}
            options={[
              { value: "read", label: "Read layout" },
              { value: "generate", label: "Generate" },
            ]}
          />
        </div>

        {err && <div className="err">{err}</div>}

        {studioMode === "read" ? (
          <>
            <Dropzone busy={busy} onFile={readLayout} />

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
          </>
        ) : (
          <ConceptForm
            concept={concept}
            onChange={setConcept}
            busy={busy}
            file={file}
            onGenerate={generate}
            versions={versions}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
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

function ConceptForm({
  concept,
  onChange,
  busy,
  file,
  onGenerate,
  versions,
  selectedId,
  onSelect,
}: {
  concept: ConceptProgram;
  onChange: (c: ConceptProgram) => void;
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  versions: { plan: import("./types").Plan; alternatives: Alternative[] } | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const sizeValue = `${concept.desk_width_cm}x${concept.desk_depth_cm}`;
  const ratioPct = Math.round(concept.closed_ratio * 100);

  return (
    <>
      {/* the plate to plan on — same Dropzone; once a file is chosen the brief drives re-generation */}
      <Dropzone busy={busy} onFile={onGenerate} />
      {file && <p className="disclaim">{file.name}</p>}

      <div className="brief">
        <Eyebrow style={{ display: "block", marginBottom: 12 }}>Program · brief</Eyebrow>

        <div className="brief-field">
          <span className="brief-label">Planning style</span>
          <Segmented
            value={concept.planning_style}
            onChange={(v) => onChange({ ...concept, planning_style: v })}
            options={PLANNING_STYLES}
          />
        </div>

        <div className="brief-field">
          <span className="brief-label">Desk type</span>
          <Segmented
            value={concept.desk_type}
            onChange={(v) => onChange({ ...concept, desk_type: v })}
            options={DESK_TYPES}
          />
        </div>

        <div className="brief-field">
          <span className="brief-label">Desk size · cm</span>
          <Segmented
            value={sizeValue}
            onChange={(v) => {
              const s = DESK_SIZES.find((d) => d.value === v);
              if (s) onChange({ ...concept, desk_width_cm: s.w, desk_depth_cm: s.d });
            }}
            options={DESK_SIZES.map((s) => ({ value: s.value, label: s.label }))}
          />
        </div>

        <div className="brief-field">
          <label className="brief-label" htmlFor="closed-ratio">
            Closed offices vs open · <span className="brief-val">{ratioPct}%</span>
          </label>
          <input
            id="closed-ratio"
            className="brief-slider"
            type="range"
            min={0}
            max={CLOSED_RATIOS.length - 1}
            step={1}
            value={CLOSED_RATIOS.indexOf(concept.closed_ratio)}
            onChange={(e) =>
              onChange({ ...concept, closed_ratio: CLOSED_RATIOS[Number(e.target.value)] })
            }
            aria-valuetext={`${ratioPct}% closed offices`}
          />
          <div className="brief-ticks" aria-hidden="true">
            {CLOSED_RATIOS.map((r) => (
              <span key={r}>{Math.round(r * 100)}</span>
            ))}
          </div>
        </div>

        <button
          className="ds-btn ds-btn--primary brief-go"
          onClick={() => file && onGenerate(file)}
          disabled={!file || busy}
        >
          {busy ? "Generating…" : versions ? "Regenerate versions" : "Generate versions"}
        </button>
      </div>

      {versions && versions.alternatives.length > 0 && (
        <>
          <hr className="ds-rule" />
          <div>
            <Eyebrow style={{ display: "block", marginBottom: 12 }}>
              Versions · {versions.alternatives.length}
            </Eyebrow>
            <div className="versions" role="list">
              {versions.alternatives.map((alt) => (
                <VersionCard
                  key={alt.id}
                  alt={alt}
                  plan={versions.plan}
                  selected={alt.id === selectedId}
                  onSelect={() => onSelect(alt.id)}
                />
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}

function VersionCard({
  alt,
  plan,
  selected,
  onSelect,
}: {
  alt: Alternative;
  plan: import("./types").Plan;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="listitem"
      className={`version-card ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="version-thumb">
        <PlanCanvas plan={plan} instances={alt.testfit.instances} />
      </span>
      <span className="version-meta">
        <span className="version-seats">
          <span className="version-seats-n">{num(alt.metrics.seats)}</span>
          <span className="version-seats-k">seats</span>
        </span>
        <MetricRow label="Density" value={`${num(alt.metrics.density_sf_per_person)} sf/p`} />
        <MetricRow label="Daylight" value={pct(alt.metrics.daylight_pct)} />
        <MetricRow label="Privacy" value={pct(alt.metrics.privacy_pct)} />
        <MetricRow label="Efficiency" value={pct(alt.metrics.efficiency_pct)} />
      </span>
    </button>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <span className="version-row">
      <span className="version-row-k">{label}</span>
      <span className="version-row-v">{value}</span>
    </span>
  );
}

const pct = (n: Metrics["daylight_pct"]) => `${Math.round(n * 100)}%`;
