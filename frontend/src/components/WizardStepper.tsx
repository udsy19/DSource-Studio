// The guided-pipeline left rail (qbiq-style). Shows the ordered stages, the current one, which are
// done, and lets the user jump to any reachable step. Purely presentational — the host owns `step`.
export type WizardStep = "property" | "space" | "program" | "visualize" | "review";

const STEPS: { key: WizardStep; label: string; hint: string }[] = [
  { key: "property", label: "Property", hint: "Name, address, units" },
  { key: "space", label: "Space", hint: "Upload the floor plate" },
  { key: "program", label: "Program", hint: "Headcount & mix" },
  { key: "visualize", label: "Visualize", hint: "Finishes & render" },
  { key: "review", label: "Review", hint: "Test-fits & export" },
];

export default function WizardStepper({
  step,
  onStep,
  reachable,
}: {
  step: WizardStep;
  onStep: (s: WizardStep) => void;
  reachable: (s: WizardStep) => boolean;
}) {
  const currentIdx = STEPS.findIndex((s) => s.key === step);
  return (
    <nav className="wizard-rail" aria-label="Pipeline steps">
      <ol>
        {STEPS.map((s, i) => {
          const state = i < currentIdx ? "done" : i === currentIdx ? "current" : "todo";
          const canJump = reachable(s.key);
          return (
            <li key={s.key} className={`wizard-step is-${state}`}>
              <button
                className="wizard-step-btn"
                onClick={() => canJump && onStep(s.key)}
                disabled={!canJump}
                aria-current={state === "current" ? "step" : undefined}
              >
                <span className="wizard-step-mark" aria-hidden="true">
                  {state === "done" ? "✓" : i + 1}
                </span>
                <span className="wizard-step-text">
                  <span className="wizard-step-label">{s.label}</span>
                  <span className="wizard-step-hint">{s.hint}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
