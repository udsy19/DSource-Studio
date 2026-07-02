import { Button, Eyebrow } from "../design/ui";
import { num, pct } from "../api";
import PlanCanvas from "./PlanCanvas";
import { listEditedDesigns, type EditedDesign, type WorkflowProject } from "../workflowProjects";
import type { Alternative, Plan } from "../types";

// The project's Results destination (qbiq "alternatives" page): the generated test-fit set as a grid
// of scored cards, each opening into the editor, with the project's edited designs listed alongside
// the untouched originals. Generation states (pending / error / empty) are honoured — never a blank
// grid. Thumbnails reuse PlanCanvas's `compact` mode, which is an inert static <svg> (no pan/zoom
// handlers), so a gridful of them carries no interaction machinery.
export default function Results({
  project,
  error,
  onOpenEditor,
  onReopen,
  onRetry,
  onBack,
}: {
  project: WorkflowProject;
  error?: string | null;
  onOpenEditor: (alt: Alternative, plan: Plan) => void;
  onReopen: (design: EditedDesign) => void;
  onRetry: () => void;
  onBack: () => void;
}) {
  const gen = project.generatedAlternatives;
  const edits = listEditedDesigns(project.id);
  const alternatives = (gen?.alternatives ?? []) as Alternative[];

  return (
    <main className="results">
      <div className="results-head">
        <div>
          <h1 className="ds-eyebrow results-title">{project.name}</h1>
          <p className="results-sub">{project.address || "—"}{project.floor ? ` · Floor ${project.floor}` : ""}</p>
        </div>
        <Button variant="quiet" onClick={onBack}>← Projects</Button>
      </div>

      {project.status === "processing" ? (
        <div className="results-state" role="status">
          <div className="glyph" aria-hidden="true">◴</div>
          <p>Generating test-fits — scoring the candidates and surfacing the best.</p>
        </div>
      ) : error ? (
        <div className="results-state" role="alert">
          <div className="glyph" aria-hidden="true">⚠</div>
          <p>{error}</p>
          <Button onClick={onRetry}>Retry generation</Button>
        </div>
      ) : alternatives.length === 0 ? (
        <div className="results-state">
          <div className="glyph" aria-hidden="true">▦</div>
          <p>No test-fits yet for this plate + program.</p>
          <Button onClick={onRetry}>Generate</Button>
        </div>
      ) : (
        <>
          <Eyebrow style={{ display: "block", margin: "4px 0 12px" }}>Test-fits · {alternatives.length}</Eyebrow>
          <div className="results-grid" role="list">
            {alternatives.map((alt) => (
              <ResultCard key={alt.id} alt={alt} plan={gen!.plan as Plan} onOpen={() => onOpenEditor(alt, gen!.plan as Plan)} />
            ))}
          </div>
        </>
      )}

      {edits.length > 0 && (
        <section className="results-edits">
          <Eyebrow style={{ display: "block", margin: "24px 0 12px" }}>Edited designs · {edits.length}</Eyebrow>
          <div className="results-edit-list">
            {edits.map((d) => (
              <button key={d.id} type="button" className="results-edit-row" onClick={() => onReopen(d)}>
                <span className="results-edit-name">{d.name}</span>
                <span className="results-edit-meta">
                  {d.forkedFrom ? `from ${d.forkedFrom} · ` : ""}{fmtDate(d.updatedAt)}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}

function ResultCard({ alt, plan, onOpen }: { alt: Alternative; plan: Plan; onOpen: () => void }) {
  return (
    <div className={`result-card${alt.recommended ? " is-recommended" : ""}`} role="listitem">
      {alt.recommended && <span className="version-badge">Recommended · {pct(alt.score)} match</span>}
      <div className="result-thumb">
        <PlanCanvas plan={plan} instances={alt.testfit.instances} compact />
      </div>
      <div className="result-meta">
        <div className="result-seats">
          <span className="version-seats-n">{num(alt.metrics.seats)}</span>
          <span className="version-seats-k">seats</span>
        </div>
        <MetricRow label="Match" value={pct(alt.score)} />
        <MetricRow label="Density" value={`${num(alt.metrics.density_sf_per_person)} sf/p`} />
        <MetricRow label="Daylight" value={pct(alt.metrics.daylight_pct)} />
        {/* privacy is a planning-heuristic estimate (privacy_basis) — flag it, don't imply precision */}
        <MetricRow label="Privacy" value={`~${pct(alt.metrics.privacy_pct)}`} />
        <MetricRow label="Efficiency" value={pct(alt.metrics.efficiency_pct)} />
      </div>
      <Button onClick={onOpen} style={{ width: "100%" }}>Open in editor →</Button>
    </div>
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

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
