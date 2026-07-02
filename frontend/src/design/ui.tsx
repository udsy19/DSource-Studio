/**
 * DSource UI — the component library. Every primitive is built only from the design
 * tokens (tokens.css) and styled in system.css. Import these instead of writing ad-hoc markup.
 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/* ── Eyebrow ── */
export function Eyebrow({ children, style }: { children: ReactNode; style?: React.CSSProperties }) {
  return (
    <span className="ds-eyebrow" style={style}>
      {children}
    </span>
  );
}

/* ── Button ── */
type BtnVariant = "primary" | "ghost" | "quiet";
export function Button({
  variant = "primary",
  children,
  ...rest
}: { variant?: BtnVariant } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`ds-btn ds-btn--${variant}`} {...rest}>
      {children}
    </button>
  );
}

/* ── Field ── */
export function Field({
  label,
  hint,
  ...rest
}: { label?: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="ds-field">
      {label && <Eyebrow>{label}</Eyebrow>}
      <input className="ds-input" {...rest} />
      {hint && <span className="ds-hint">{hint}</span>}
    </label>
  );
}

/* ── Card ── */
export function Card({
  children,
  variant = "flat",
  style,
}: {
  children: ReactNode;
  variant?: "flat" | "raised";
  style?: React.CSSProperties;
}) {
  return (
    <div className={`ds-card ds-card--${variant}`} style={style}>
      {children}
    </div>
  );
}

/* ── Stat ── */
export function Stat({ value, label, accent }: { value: ReactNode; label: string; accent?: boolean }) {
  return (
    <div className="ds-stat">
      <div className={`v ${accent ? "accent" : ""}`}>{value}</div>
      <div className="k">{label}</div>
    </div>
  );
}

/* ── Tag ── */
export function Tag({
  children,
  swatch,
  accent,
}: {
  children: ReactNode;
  swatch?: { fill: string; stroke: string };
  accent?: boolean;
}) {
  return (
    <span className={`ds-tag ${accent ? "ds-tag--accent" : ""}`}>
      {swatch && <i style={{ background: swatch.fill, boxShadow: `inset 0 0 0 1px ${swatch.stroke}` }} />}
      {children}
    </span>
  );
}

/* ── Callout ── */
export function Callout({ children, quiet }: { children: ReactNode; quiet?: boolean }) {
  return <div className={`ds-callout ${quiet ? "ds-callout--quiet" : ""}`}>{children}</div>;
}

/* ── Divider ── */
export function Divider({ style }: { style?: React.CSSProperties }) {
  return <hr className="ds-rule" style={style} />;
}

/* ── Segmented control ── */
export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div className="ds-seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
