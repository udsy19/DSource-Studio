import { useState } from "react";
import DesignSystem from "./design/DesignSystem";
import Projects from "./components/Projects";
import Studio from "./Studio";
import { updateProject, type ProjectStatus, type WorkflowProject } from "./workflowProjects";

type View = "projects" | "studio" | "system";

export default function App() {
  const [view, setView] = useState<View>("projects");
  const [active, setActive] = useState<WorkflowProject | null>(null);
  const [resume, setResume] = useState(false); // reopen straight into the scene editor on a saved design

  const openProject = (p: WorkflowProject, resumeEditing = false) => {
    setActive(p);
    setResume(resumeEditing);
    setView("studio");
  };

  const setStatus = (status: ProjectStatus) => {
    if (!active) return;
    updateProject(active.id, { status });
    setActive({ ...active, status });
  };

  return (
    <div className="app">
      <header className="bar">
        <button className="wordmark wordmark-btn" onClick={() => setView("projects")}>
          DSOURCE <span className="studio-mark">STUDIO</span>
        </button>
        <span className="sub">
          {view === "system" ? "Design system" : "Workplace design intelligence"}
        </span>

        {view === "studio" && active && (
          <nav className="crumbs" aria-label="Breadcrumb">
            <button className="crumb-link" onClick={() => setView("projects")}>Projects</button>
            <span className="crumb-sep">›</span>
            <span className="crumb-here">{active.name}</span>
          </nav>
        )}

        <div className="bar-right">
          <button
            className={`link-btn ${view === "system" ? "is-on" : ""}`}
            onClick={() => setView(view === "system" ? "projects" : "system")}
          >
            System
          </button>
          <span className="right">plate → wellbeing → budget</span>
        </div>
      </header>

      <div className="view">
        {view === "projects" && <Projects onOpen={openProject} />}
        {view === "studio" && (
          <Studio
            project={active}
            onStatus={setStatus}
            resume={resume}
            onClose={() => { setResume(false); setView("projects"); }}
          />
        )}
        {view === "system" && <DesignSystem />}
      </div>
    </div>
  );
}
