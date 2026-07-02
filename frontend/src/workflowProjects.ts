// Client-side workflow-project store (localStorage). The backend `Project` model is the pricing/BOM
// entity, not a qbiq-style test-fit project — so until a workflow-project table exists (roadmap
// Phase A backend), a "project" (property + space + program + generated designs + status) lives here.
// One concept, one file; swap the impl for an API later without touching callers.

export type ProjectStatus = "draft" | "processing" | "ready";

// An edited design forked from a generated version — qbiq's immutability rule kept in the schema:
// generated versions are never overwritten; every edit lands here as its own record. We persist ONLY
// the current scene (never the undo history — N full 300-item snapshots would blow the ~5MB quota;
// undo is session-scoped and reopening starts a fresh stack).
export interface EditedDesign {
  id: string;
  name: string;
  forkedFrom: string | null; // the generated version id this was forked from
  scene: unknown; // the current scene JSON (scene_to_dict shape) — NOT the undo stack
  updatedAt: number;
}

// The generated test-fit set for a project: the plan is stored ONCE (not duplicated onto every
// alternative), and only the SURFACED alternatives are kept (never the wider internal candidate pool
// the scorer culls). Replaced wholesale on a re-generation; edits never touch it (they fork into
// editedDesigns[]), so a generated version is never overwritten by an edit.
export interface GeneratedResult {
  plan: unknown;
  alternatives: unknown[];
  updatedAt: number;
}

export interface WorkflowProject {
  id: string;
  name: string;
  address: string;
  floor: string;
  status: ProjectStatus;
  createdAt: number; // epoch ms
  updatedAt: number;
  generatedAlternatives?: GeneratedResult;
  editedDesigns?: EditedDesign[];
}

const KEY = "dsource.projects.v1";

function read(): WorkflowProject[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as WorkflowProject[]) : [];
  } catch {
    return [];
  }
}

function write(projects: WorkflowProject[]): void {
  localStorage.setItem(KEY, JSON.stringify(projects));
}

export function listProjects(): WorkflowProject[] {
  return read().sort((a, b) => b.updatedAt - a.updatedAt);
}

export function createProject(input: { name: string; address: string; floor: string }): WorkflowProject {
  const now = Date.now();
  const project: WorkflowProject = {
    id: `p-${now.toString(36)}`,
    name: input.name.trim() || "Untitled project",
    address: input.address.trim(),
    floor: input.floor.trim(),
    status: "draft",
    createdAt: now,
    updatedAt: now,
  };
  write([project, ...read()]);
  return project;
}

export function updateProject(id: string, patch: Partial<Omit<WorkflowProject, "id" | "createdAt">>): void {
  write(read().map((p) => (p.id === id ? { ...p, ...patch, updatedAt: Date.now() } : p)));
}

export function deleteProject(id: string): void {
  write(read().filter((p) => p.id !== id));
}

export function getProject(id: string): WorkflowProject | undefined {
  return read().find((p) => p.id === id);
}

// The one quota-safe write both persist paths share: a full scene or a generated set can exceed the
// ~5MB localStorage quota, and a design tool that silently loses work is dead — so surface a full
// store as a visible failure instead of dropping the write.
function safeWrite(projects: WorkflowProject[]): { ok: true } | { ok: false; error: string } {
  try {
    write(projects);
    return { ok: true };
  } catch (e) {
    const quota = e instanceof DOMException && (e.name === "QuotaExceededError" || e.code === 22);
    return { ok: false, error: quota ? "Couldn't save — browser storage is full." : "Couldn't save." };
  }
}

// Persist a project's generated test-fit set (from Submit). Replaces any prior set — regeneration is
// a fresh Submit, and edits live separately in editedDesigns[], so this never overwrites an edit.
export function saveGeneratedAlternatives(
  projectId: string,
  result: { plan: unknown; alternatives: unknown[] },
): { ok: true } | { ok: false; error: string } {
  const projects = read();
  if (!projects.some((p) => p.id === projectId)) return { ok: false, error: "Project not found." };
  const gen: GeneratedResult = { plan: result.plan, alternatives: result.alternatives, updatedAt: Date.now() };
  const next = projects.map((p) =>
    p.id === projectId ? { ...p, generatedAlternatives: gen, status: "ready" as ProjectStatus, updatedAt: Date.now() } : p,
  );
  return safeWrite(next);
}

export function listEditedDesigns(projectId: string): EditedDesign[] {
  const p = read().find((x) => x.id === projectId);
  return (p?.editedDesigns ?? []).slice().sort((a, b) => b.updatedAt - a.updatedAt);
}

// Persist (append or update by id) an edited design onto its project — the ONLY mutation of the
// editedDesigns array, so a generated version's data is never overwritten. Saving a large scene can
// exceed the localStorage quota; surface that as a visible failure instead of silently dropping the
// user's edits (a design tool that loses an hour of work is dead).
export function saveEditedDesign(
  projectId: string,
  design: EditedDesign,
): { ok: true } | { ok: false; error: string } {
  const projects = read();
  const project = projects.find((p) => p.id === projectId);
  if (!project) return { ok: false, error: "Project not found." };
  const rest = (project.editedDesigns ?? []).filter((d) => d.id !== design.id);
  const next = projects.map((p) =>
    p.id === projectId
      ? { ...p, editedDesigns: [...rest, design], updatedAt: Date.now(), status: "ready" as ProjectStatus }
      : p,
  );
  return safeWrite(next);
}
