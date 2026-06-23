import { useState } from "react";
import ProcessRail from "./components/ProcessRail";
import DesignSystem from "./design/DesignSystem";
import { Segmented } from "./design/ui";
import Studio from "./Studio";

type View = "studio" | "system";

export default function App() {
  const [view, setView] = useState<View>("studio");

  return (
    <div className="app">
      <header className="bar">
        <span className="wordmark">
          DSOURCE <span className="studio-mark">STUDIO</span>
        </span>
        <span className="sub">
          {view === "studio" ? "Workplace design intelligence" : "Design system"}
        </span>
        {view === "studio" && (
          <div className="bar-rail">
            <ProcessRail active />
          </div>
        )}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 22 }}>
          <Segmented
            value={view}
            onChange={setView}
            options={[
              { value: "studio", label: "Studio" },
              { value: "system", label: "System" },
            ]}
          />
          <span className="right">plate → wellbeing → budget</span>
        </div>
      </header>

      <div className="view">{view === "studio" ? <Studio /> : <DesignSystem />}</div>
    </div>
  );
}
