import { useMemo, useState } from "react";
import {
  downloadIfc,
  downloadIfcFromFit,
  downloadLayoutTakeoff,
  downloadReport,
  downloadTakeoffFromFit,
  generateAlternatives,
  generateDetailed,
  generateFromConcept,
  ingestCad,
  iterateDetailed,
  num,
} from "./api";
import Dropzone from "./components/Dropzone";
import PlanCanvas, { instanceKey } from "./components/PlanCanvas";
import SpaceView from "./components/SpaceView";
import { Callout, Eyebrow, Segmented } from "./design/ui";
import type {
  Alternative,
  ConceptProgram,
  DetailedProgram,
  ExtractedLayout,
  Instance,
  Metrics,
  Placement,
  Plan,
  RoomType,
} from "./types";

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

// Detailed mode — the room catalog (mirrors backend app/testfit/catalog.py), grouped by family.
// Each entry carries the placement that suits it; count 0 means "not requested".
const ROOM_CATALOG: {
  family: string;
  rooms: { type: RoomType; label: string; placement: Placement }[];
}[] = [
  {
    family: "Offices",
    rooms: [
      { type: "office_exec", label: "Executive", placement: "window" },
      { type: "office_large", label: "Large", placement: "window" },
      { type: "office_medium", label: "Medium", placement: "window" },
      { type: "office_small", label: "Small", placement: "window" },
      { type: "office_focus", label: "Focus", placement: "flexible" },
    ],
  },
  {
    family: "Team rooms",
    rooms: [
      { type: "team_2", label: "Team · 2", placement: "window" },
      { type: "team_4", label: "Team · 4", placement: "window" },
      { type: "team_6", label: "Team · 6", placement: "flexible" },
      { type: "team_8", label: "Team · 8", placement: "flexible" },
    ],
  },
  {
    family: "Conference",
    rooms: [
      { type: "conf_board", label: "Boardroom", placement: "flexible" },
      { type: "conf_xl", label: "XL conference", placement: "flexible" },
      { type: "conf_large", label: "Large", placement: "flexible" },
      { type: "conf_medium", label: "Medium", placement: "flexible" },
      { type: "conf_small", label: "Small / meeting", placement: "flexible" },
    ],
  },
  {
    family: "Collaboration",
    rooms: [
      { type: "huddle", label: "Huddle", placement: "core" },
      { type: "phone_booth", label: "Phone booth", placement: "core" },
      { type: "focus_room", label: "Focus room", placement: "flexible" },
    ],
  },
  {
    family: "Amenities",
    rooms: [
      { type: "reception", label: "Reception", placement: "window" },
      { type: "kitchen", label: "Kitchen / pantry", placement: "flexible" },
      { type: "wellness", label: "Wellness", placement: "core" },
      { type: "copy_print", label: "Copy / print", placement: "core" },
      { type: "storage", label: "Storage / IT", placement: "core" },
    ],
  },
];
const PLACEMENTS: { value: Placement; label: string }[] = [
  { value: "window", label: "Window" },
  { value: "core", label: "Core" },
  { value: "flexible", label: "Flexible" },
];

const DEFAULT_DETAILED: DetailedProgram = {
  rooms: [
    { type: "office_medium", count: 4, placement: "window" },
    { type: "conf_small", count: 2, placement: "flexible" },
    { type: "huddle", count: 2, placement: "core" },
    { type: "phone_booth", count: 1, placement: "core" },
  ],
  desk_type: "workstations",
  desk_width_cm: 140,
  desk_depth_cm: 70,
};

export default function Studio() {
  const [studioMode, setStudioMode] = useState<"read" | "generate">("read");

  // Read-layout state (the existing flow).
  const [layout, setLayout] = useState<ExtractedLayout | null>(null);
  const [file, setFile] = useState<File | null>(null);

  // Generate state — Concept | Detailed sub-mode, kept separate from the read-layout state.
  const [genMode, setGenMode] = useState<"concept" | "detailed">("concept");
  const [concept, setConcept] = useState<ConceptProgram>(DEFAULT_CONCEPT);
  const [detailed, setDetailed] = useState<DetailedProgram>(DEFAULT_DETAILED);
  const [versions, setVersions] = useState<{ plan: Plan; alternatives: Alternative[] } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pinned, setPinned] = useState<Instance[]>([]); // Detailed iterate: rooms kept across regenerations

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
    setPinned([]);
    setFile(f);
    try {
      // Generate scored test-fit versions from the plate + the program (Concept brief or the
      // explicit Detailed counts), then compare them side by side and open one in 2D / 3D.
      const res =
        genMode === "detailed"
          ? await generateDetailed(f, detailed)
          : await generateFromConcept(f, concept);
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  // Iterate: regenerate Detailed versions keeping the pinned rooms (they persist at exact coords).
  async function regenerate() {
    if (!versions) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await iterateDetailed({ plan: versions.plan, program: detailed, locked: pinned });
      setVersions(res);
      setSelectedId(res.alternatives[0]?.id ?? null);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }

  const togglePin = (it: Instance) => {
    const key = instanceKey(it);
    setPinned((prev) =>
      prev.some((p) => instanceKey(p) === key) ? prev.filter((p) => instanceKey(p) !== key) : [...prev, it],
    );
  };
  const pinnedKeys = useMemo(() => new Set(pinned.map(instanceKey)), [pinned]);
  const canPin = studioMode === "generate" && genMode === "detailed";

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

  const building = file?.name.replace(/\.(dxf|dwg)$/i, "") ?? "Plan";
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
              <PlanCanvas
                plan={versions.plan}
                instances={selected.testfit.instances}
                pinnedKeys={canPin ? pinnedKeys : undefined}
                onTogglePin={canPin ? togglePin : undefined}
              />
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
          <>
            <div className="brief-field">
              <Segmented
                value={genMode}
                onChange={(m) => {
                  setGenMode(m);
                  setErr(null);
                }}
                options={[
                  { value: "concept", label: "Concept" },
                  { value: "detailed", label: "Detailed" },
                ]}
              />
            </div>

            <Dropzone busy={busy} onFile={generate} />
            {file && <p className="disclaim">{file.name}</p>}

            {genMode === "concept" ? (
              <ConceptForm
                concept={concept}
                onChange={setConcept}
                busy={busy}
                file={file}
                onGenerate={generate}
                hasVersions={!!versions}
              />
            ) : (
              <DetailedForm
                program={detailed}
                onChange={setDetailed}
                busy={busy}
                file={file}
                onGenerate={generate}
                hasVersions={!!versions}
              />
            )}

            <VersionList
              versions={versions}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />

            {canPin && versions && (
              <>
                <hr className="ds-rule" />
                <div className="iterate">
                  <Eyebrow style={{ display: "block", marginBottom: 10 }}>Iterate · pin & regenerate</Eyebrow>
                  <p className="disclaim" style={{ marginBottom: 12 }}>
                    Click rooms on the plan to pin them, adjust the program above, then regenerate —
                    pinned rooms stay put while the rest re-places.
                  </p>
                  <div className="iterate-head">
                    <span className="brief-label">
                      {pinned.length} pinned
                    </span>
                    {pinned.length > 0 && (
                      <button type="button" className="link-btn" onClick={() => setPinned([])}>
                        Clear
                      </button>
                    )}
                  </div>
                  <button
                    className="export-btn export-btn--primary"
                    style={{ marginTop: 10, width: "100%" }}
                    onClick={regenerate}
                    disabled={busy}
                  >
                    <span className="export-btn-label">
                      {busy ? "Regenerating…" : "Regenerate"}
                    </span>
                    <span className="export-btn-meta">
                      {pinned.length > 0 ? `keep ${pinned.length} pinned` : "re-place all"}
                    </span>
                  </button>
                </div>
              </>
            )}

            {versions && selected && (
              <>
                <hr className="ds-rule" />
                <div className="exports">
                  <Eyebrow style={{ display: "block", marginBottom: 14 }}>
                    Export · version {selected.id}
                  </Eyebrow>
                  <div className="export-actions">
                    <button
                      className="export-btn export-btn--primary"
                      onClick={() =>
                        runExport("report", () =>
                          downloadReport({
                            project: { client: "", building, style: "Modern", floor: "" },
                            plan: versions.plan,
                            alternatives: versions.alternatives,
                          }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">Space-planning report</span>
                      <span className="export-btn-meta">{exporting === "report" ? "Preparing…" : "PDF · 3 options"}</span>
                    </button>
                    <button
                      className="export-btn"
                      onClick={() =>
                        runExport("takeoff", () =>
                          downloadTakeoffFromFit({ plan: versions.plan, testfit: selected.testfit }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">Quantity takeoff</span>
                      <span className="export-btn-meta">{exporting === "takeoff" ? "Preparing…" : "Excel · BOM"}</span>
                    </button>
                    <button
                      className="export-btn"
                      onClick={() =>
                        runExport("ifc", () =>
                          downloadIfcFromFit({ plan: versions.plan, testfit: selected.testfit }),
                        )
                      }
                      disabled={!!exporting}
                    >
                      <span className="export-btn-label">BIM model</span>
                      <span className="export-btn-meta">{exporting === "ifc" ? "Preparing…" : "IFC"}</span>
                    </button>
                  </div>
                  <p className="disclaim" style={{ marginTop: 12 }}>
                    Report compares all three versions; takeoff &amp; BIM export the selected one.
                  </p>
                </div>
              </>
            )}
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

function ConceptForm({
  concept,
  onChange,
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  concept: ConceptProgram;
  onChange: (c: ConceptProgram) => void;
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  const sizeValue = `${concept.desk_width_cm}x${concept.desk_depth_cm}`;
  const ratioPct = Math.round(concept.closed_ratio * 100);

  return (
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

      <GenerateButton busy={busy} file={file} onGenerate={onGenerate} hasVersions={hasVersions} />
    </div>
  );
}

function DetailedForm({
  program,
  onChange,
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  program: DetailedProgram;
  onChange: (p: DetailedProgram) => void;
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  const sizeValue = `${program.desk_width_cm}x${program.desk_depth_cm}`;
  // Upsert a room by type (count 0 prunes it); placement defaults to the catalog entry's.
  const setCount = (type: RoomType, fallback: Placement, count: number) => {
    const others = program.rooms.filter((r) => r.type !== type);
    const existing = program.rooms.find((r) => r.type === type);
    onChange({
      ...program,
      rooms:
        count > 0
          ? [...others, { type, count, placement: existing?.placement ?? fallback }]
          : others,
    });
  };
  const setPlacement = (type: RoomType, placement: Placement) =>
    onChange({
      ...program,
      rooms: program.rooms.map((r) => (r.type === type ? { ...r, placement } : r)),
    });

  return (
    <div className="brief">
      <Eyebrow style={{ display: "block", marginBottom: 12 }}>Program · rooms</Eyebrow>

      {ROOM_CATALOG.map(({ family, rooms }) => (
        <div className="room-family" key={family}>
          <span className="room-family-label">{family}</span>
          <div className="room-reqs">
            {rooms.map(({ type, label, placement }) => {
              const room = program.rooms.find((r) => r.type === type);
              const count = room?.count ?? 0;
              return (
                <div className="room-req" key={type} data-active={count > 0}>
                  <div className="room-req-head">
                    <span className="brief-label">{label}</span>
                    <div className="room-stepper" role="group" aria-label={`${label} count`}>
                      <button
                        type="button"
                        className="room-step"
                        aria-label={`Fewer ${label}`}
                        disabled={count <= 0}
                        onClick={() => setCount(type, placement, Math.max(0, count - 1))}
                      >
                        −
                      </button>
                      <span className="room-count" aria-live="polite">
                        {num(count)}
                      </span>
                      <button
                        type="button"
                        className="room-step"
                        aria-label={`More ${label}`}
                        onClick={() => setCount(type, placement, count + 1)}
                      >
                        +
                      </button>
                    </div>
                  </div>
                  {count > 0 && (
                    <Segmented
                      value={room?.placement ?? placement}
                      onChange={(v) => setPlacement(type, v)}
                      options={PLACEMENTS}
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="brief-field">
        <span className="brief-label">Desk type</span>
        <Segmented
          value={program.desk_type}
          onChange={(v) => onChange({ ...program, desk_type: v })}
          options={DESK_TYPES}
        />
      </div>

      <div className="brief-field">
        <span className="brief-label">Desk size · cm</span>
        <Segmented
          value={sizeValue}
          onChange={(v) => {
            const s = DESK_SIZES.find((d) => d.value === v);
            if (s) onChange({ ...program, desk_width_cm: s.w, desk_depth_cm: s.d });
          }}
          options={DESK_SIZES.map((s) => ({ value: s.value, label: s.label }))}
        />
      </div>

      <GenerateButton busy={busy} file={file} onGenerate={onGenerate} hasVersions={hasVersions} />
    </div>
  );
}

function GenerateButton({
  busy,
  file,
  onGenerate,
  hasVersions,
}: {
  busy: boolean;
  file: File | null;
  onGenerate: (f: File) => void;
  hasVersions: boolean;
}) {
  return (
    <button
      className="ds-btn ds-btn--primary brief-go"
      onClick={() => file && onGenerate(file)}
      disabled={!file || busy}
    >
      {busy ? "Generating…" : hasVersions ? "Regenerate versions" : "Generate versions"}
    </button>
  );
}

function VersionList({
  versions,
  selectedId,
  onSelect,
}: {
  versions: { plan: Plan; alternatives: Alternative[] } | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!versions || versions.alternatives.length === 0) return null;
  return (
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
  );
}

function VersionCard({
  alt,
  plan,
  selected,
  onSelect,
}: {
  alt: Alternative;
  plan: Plan;
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
