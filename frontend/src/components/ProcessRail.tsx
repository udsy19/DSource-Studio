/**
 * ProcessRail — a quiet narrative indicator for the DSource Studio pipeline:
 * Design → Spec → Wellbeing → Source → Procurement.
 * Styled entirely from the design tokens (see styles.css .rail*).
 */
type Step = { key: string; label: string; soon?: boolean };

const STEPS: Step[] = [
  { key: "design", label: "Design" },
  { key: "spec", label: "Spec" },
  { key: "wellbeing", label: "Wellbeing" },
  { key: "source", label: "Source" },
  { key: "procurement", label: "Procurement" },
];

export default function ProcessRail({ active }: { active?: boolean }) {
  return (
    <nav className="rail" aria-label="DSource pipeline">
      {STEPS.map((s, i) => (
        <span className="rail-step" key={s.key}>
          {i > 0 && <i className="rail-sep" aria-hidden="true" />}
          <span
            className={`rail-dot ${s.soon ? "soon" : active ? "on" : ""}`}
            aria-hidden="true"
          />
          <span className={`rail-label ${s.soon ? "soon" : ""}`}>
            {s.label}
            {s.soon && <em className="rail-soon">soon</em>}
          </span>
        </span>
      ))}
    </nav>
  );
}
