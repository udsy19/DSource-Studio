import { useState } from "react";
import { Button, Card, Field, Tag } from "../design/ui";
import {
  createProject,
  deleteProject,
  listProjects,
  type ProjectStatus,
  type WorkflowProject,
} from "../workflowProjects";

const STATUS_LABEL: Record<ProjectStatus, string> = {
  draft: "Draft",
  processing: "Processing",
  ready: "Ready",
};

function fmtDate(ms: number): string {
  return new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// The app home — a grid of workflow projects (qbiq "My Projects"). New Project starts the pipeline;
// a card opens it. Client-side store for now (see workflowProjects.ts).
export default function Projects({ onOpen }: { onOpen: (p: WorkflowProject, resume?: boolean) => void }) {
  const [projects, setProjects] = useState<WorkflowProject[]>(listProjects);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "", address: "", floor: "" });

  const refresh = () => setProjects(listProjects());

  const create = () => {
    const p = createProject(form);
    setForm({ name: "", address: "", floor: "" });
    setCreating(false);
    refresh();
    onOpen(p);
  };

  const remove = (id: string) => {
    deleteProject(id);
    refresh();
  };

  return (
    <main className="projects">
      <div className="projects-head">
        <h1 className="ds-eyebrow projects-title">My projects</h1>
        {!creating && <Button onClick={() => setCreating(true)}>+ New project</Button>}
      </div>

      {creating && (
        <Card variant="raised" style={{ marginBottom: 20 }}>
          <div className="new-project-form">
            <Field
              label="Property name"
              placeholder="e.g. Chronos Office — 6th Floor"
              value={form.name}
              autoFocus
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Field
              label="Address"
              placeholder="City, area"
              value={form.address}
              onChange={(e) => setForm({ ...form, address: e.target.value })}
            />
            <Field
              label="Floor"
              placeholder="e.g. 6"
              value={form.floor}
              onChange={(e) => setForm({ ...form, floor: e.target.value })}
            />
            <div className="new-project-actions">
              <Button variant="quiet" onClick={() => setCreating(false)}>Cancel</Button>
              <Button onClick={create} disabled={!form.name.trim()}>Create &amp; open</Button>
            </div>
          </div>
        </Card>
      )}

      {projects.length === 0 && !creating ? (
        <div className="empty">
          <div className="glyph" aria-hidden="true">▦</div>
          <p>No projects yet. Start one — upload a floor plate, set the program, and generate test-fits.</p>
        </div>
      ) : (
        <div className="projects-grid">
          {projects.map((p) => (
            <div key={p.id} className="project-card">
              <button className="project-open" onClick={() => onOpen(p)} aria-label={`Open ${p.name}`}>
                <div className="project-card-top">
                  <span className="project-id">#{p.id.slice(-5)}</span>
                  <Tag accent={p.status === "ready"}>{STATUS_LABEL[p.status]}</Tag>
                </div>
                <div className="project-thumb" aria-hidden="true">▤</div>
                <div className="project-name">{p.name}</div>
                <div className="project-meta">{p.address || "—"}</div>
                <div className="project-meta">
                  {p.floor ? `Floor ${p.floor} · ` : ""}{fmtDate(p.createdAt)}
                </div>
              </button>
              {p.editedDesigns?.length ? (
                <button
                  className="project-resume link-btn"
                  onClick={() => onOpen(p, true)}
                  aria-label={`Resume editing ${p.name}`}
                >
                  Resume editing →
                </button>
              ) : null}
              <button
                className="project-del"
                onClick={() => remove(p.id)}
                aria-label={`Delete ${p.name}`}
                title="Delete project"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
