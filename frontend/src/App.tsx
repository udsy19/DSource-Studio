import { useState } from "react";
import DesignSystem from "./design/DesignSystem";
import Projects from "./components/Projects";
import Results from "./components/Results";
import SceneEditor from "./components/SceneEditor";
import Studio, { type SubmitInputs } from "./Studio";
import { fetchGenerateJob, submitGenerateDetailed, submitGenerateFromConcept } from "./api";
import {
  getProject,
  saveGeneratedAlternatives,
  updateProject,
  type EditedDesign,
  type WorkflowProject,
} from "./workflowProjects";
import type { Alternative, Plan } from "./types";

type View = "projects" | "studio" | "results" | "editor" | "system";

// What the editor was opened on: a fresh FORK of a generated alternative (built from-fit), or a
// REOPEN of an already-saved edited design (seeded from its scene). Held only in memory.
type EditorTarget =
  | { kind: "fork"; plan: Plan; testfit: Alternative["testfit"]; forkedFrom: string; designName: string; programTargets?: Record<string, number> }
  | { kind: "reopen"; design: EditedDesign };

export default function App() {
  const [view, setView] = useState<View>("projects");
  const [active, setActive] = useState<WorkflowProject | null>(null);
  const [editorTarget, setEditorTarget] = useState<EditorTarget | null>(null);
  const [genError, setGenError] = useState<string | null>(null);
  const [lastSubmit, setLastSubmit] = useState<SubmitInputs | null>(null);

  const refreshActive = (id: string) => setActive(getProject(id) ?? null);

  // Open a project: a generated project lands on its Results destination; a fresh (or legacy, no
  // generatedAlternatives) project resumes the wizard. Back-compat: legacy records simply lack the
  // field and route to the wizard, never crash.
  const openProject = (p: WorkflowProject) => {
    setActive(p);
    setGenError(null);
    setView(p.generatedAlternatives ? "results" : "studio");
  };

  // Submit from the wizard: App owns the generation job so Results can reflect it (processing →
  // ready / error). The wizard hands over its inputs and we navigate to Results immediately.
  const runGeneration = async (inputs: SubmitInputs, projectId: string) => {
    updateProject(projectId, { status: "processing" });
    refreshActive(projectId);
    setGenError(null);
    setView("results");
    try {
      const { job_id } =
        inputs.genMode === "detailed"
          ? await submitGenerateDetailed(inputs.file, inputs.detailed)
          : await submitGenerateFromConcept(inputs.file, inputs.concept);
      let job = await fetchGenerateJob(job_id);
      for (let tries = 0; job.status === "processing" && tries < 120; tries++) {
        await new Promise((r) => setTimeout(r, 1500));
        job = await fetchGenerateJob(job_id);
      }
      if (job.status !== "ready" || !job.result || job.result.alternatives.length === 0) {
        throw new Error(job.error || (job.status === "processing" ? "Generation timed out." : "No test-fits could be generated for this plate + program."));
      }
      const saved = saveGeneratedAlternatives(projectId, { ...job.result, programTargets: inputs.programTargets });
      if (!saved.ok) throw new Error(saved.error);
      refreshActive(projectId);
    } catch (e) {
      updateProject(projectId, { status: "draft" });
      refreshActive(projectId);
      setGenError(e instanceof Error ? e.message : String(e));
    }
  };

  const onSubmit = (inputs: SubmitInputs) => {
    if (!active) return;
    setLastSubmit(inputs);
    void runGeneration(inputs, active.id);
  };

  const retryGeneration = () => {
    if (active && lastSubmit) void runGeneration(lastSubmit, active.id);
  };

  const openEditorFork = (alt: Alternative, plan: Plan) => {
    setEditorTarget({
      kind: "fork", plan, testfit: alt.testfit, forkedFrom: alt.id, designName: `Design ${alt.id}`,
      programTargets: active?.generatedAlternatives?.programTargets,
    });
    setView("editor");
  };
  const openEditorReopen = (design: EditedDesign) => {
    setEditorTarget({ kind: "reopen", design });
    setView("editor");
  };
  const exitEditor = () => {
    if (active) refreshActive(active.id); // pick up any newly saved edited design
    setEditorTarget(null);
    setView("results");
  };

  return (
    <div className="app">
      <header className="bar">
        <button className="wordmark wordmark-btn" onClick={() => setView("projects")}>
          DSOURCE <span className="studio-mark">STUDIO</span>
        </button>
        <span className="sub">{view === "system" ? "Design system" : "Workplace design intelligence"}</span>

        {active && (view === "studio" || view === "results" || view === "editor") && (
          <nav className="crumbs" aria-label="Breadcrumb">
            <button className="crumb-link" onClick={() => setView("projects")}>Projects</button>
            <span className="crumb-sep">›</span>
            {view === "editor" ? (
              <button className="crumb-link" onClick={exitEditor}>{active.name}</button>
            ) : (
              <span className="crumb-here">{active.name}</span>
            )}
            {view === "editor" && <><span className="crumb-sep">›</span><span className="crumb-here">Editor</span></>}
          </nav>
        )}

        <div className="bar-right">
          <button className={`link-btn ${view === "system" ? "is-on" : ""}`} onClick={() => setView(view === "system" ? "projects" : "system")}>
            System
          </button>
          <span className="right">plate → wellbeing → budget</span>
        </div>
      </header>

      <div className="view">
        {view === "projects" && <Projects onOpen={openProject} />}
        {view === "studio" && active && <Studio project={active} onSubmit={onSubmit} />}
        {view === "results" && active && (
          <Results
            project={active}
            error={genError}
            onOpenEditor={openEditorFork}
            onReopen={openEditorReopen}
            onRetry={retryGeneration}
            onBack={() => setView("projects")}
          />
        )}
        {view === "editor" && editorTarget && active && (
          editorTarget.kind === "fork" ? (
            <SceneEditor
              plan={editorTarget.plan}
              testfit={editorTarget.testfit}
              program={editorTarget.programTargets}
              projectId={active.id}
              forkedFrom={editorTarget.forkedFrom}
              designName={editorTarget.designName}
              onExit={exitEditor}
            />
          ) : (
            <SceneEditor
              savedScene={editorTarget.design.scene as Parameters<typeof SceneEditor>[0]["savedScene"]}
              projectId={active.id}
              designId={editorTarget.design.id}
              designName={editorTarget.design.name}
              forkedFrom={editorTarget.design.forkedFrom}
              onExit={exitEditor}
            />
          )
        )}
        {view === "system" && <DesignSystem />}
      </div>
    </div>
  );
}
