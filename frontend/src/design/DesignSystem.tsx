import { useState } from "react";
import { Button, Callout, Card, Divider, Eyebrow, Field, Segmented, Stat, Tag } from "./ui";

const COLORS = [
  { nm: "Paper", v: "--paper", hex: "#F4F1EA" },
  { nm: "Paper 2", v: "--paper-2", hex: "#EFEAE0" },
  { nm: "Paper 3", v: "--paper-3", hex: "#E8E1D4" },
  { nm: "Ink", v: "--ink", hex: "#1A1813" },
  { nm: "Ink 2", v: "--ink-2", hex: "#3C382F" },
  { nm: "Muted", v: "--muted", hex: "#97917F" },
  { nm: "Faint", v: "--faint", hex: "#B9B3A3" },
  { nm: "Line", v: "--line", hex: "#E2DDD0" },
  { nm: "Accent", v: "--accent", hex: "#B8552F" },
  { nm: "Accent Press", v: "--accent-press", hex: "#9C4627" },
];

const TYPE = [
  { tag: "Display", cls: "ds-display", s: "Plate to budget" },
  { tag: "Title", cls: "ds-title", s: "A furnished test-fit" },
  { tag: "Lead", cls: "ds-lead", s: "Drop a floor plate and watch it furnish itself." },
  { tag: "Numeral", cls: "ds-numeral", s: "$176,613" },
  { tag: "Body", cls: "ds-body", s: "List minus the dealer’s standard discount, plus install, freight and tax." },
  { tag: "Small", cls: "ds-body ds-muted", s: "Budgetary — a dealer confirms the firm number." },
  { tag: "Eyebrow", cls: "ds-eyebrow", s: "Bill of materials" },
];

const SPACE = [
  ["--s1", "4"], ["--s2", "8"], ["--s3", "12"], ["--s4", "16"],
  ["--s5", "22"], ["--s6", "30"], ["--s7", "40"], ["--s8", "56"],
];

const RADII = [
  ["--r0", "0"], ["--r1", "3"], ["--r2", "8"], ["--r-pill", "pill"],
];

export default function DesignSystem() {
  const [seg, setSeg] = useState<"day" | "week" | "month">("week");

  return (
    <div className="ds-page">
      <Eyebrow>DSource · design language</Eyebrow>
      <h1>Warm paper, ink, one ember.</h1>
      <p className="ds-sub">
        A quiet, editorial system for an architectural tool — gallery, not dashboard. Every
        primitive below is built only from the design tokens.
      </p>

      {/* ── Color ── */}
      <section className="ds-section">
        <Eyebrow>Color</Eyebrow>
        <div className="ds-grid ds-swatches">
          {COLORS.map((c) => (
            <div className="ds-swatch" key={c.v}>
              <div className="chip" style={{ background: `var(${c.v})` }} />
              <div className="meta">
                <span className="nm">{c.nm}</span>
                <span className="hex">{c.hex}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Type ── */}
      <section className="ds-section">
        <Eyebrow>Typography — Fraunces · Inter</Eyebrow>
        <div>
          {TYPE.map((t) => (
            <div className="ds-type-row" key={t.tag}>
              <span className="tag">{t.tag}</span>
              <span className={t.cls}>{t.s}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Space & radius ── */}
      <section className="ds-section">
        <Eyebrow>Space &amp; radius</Eyebrow>
        <div className="ds-row" style={{ alignItems: "flex-start", gap: 56 }}>
          <div style={{ flex: 1 }}>
            {SPACE.map(([v, px]) => (
              <div className="ds-space-row" key={v}>
                <span className="lbl">{v} · {px}</span>
                <div className="bar" style={{ width: `var(${v})` }} />
              </div>
            ))}
          </div>
          <div className="ds-row">
            {RADII.map(([v, label]) => (
              <div key={v} style={{ textAlign: "center" }}>
                <div
                  style={{
                    width: 64, height: 64, background: "var(--accent-soft)",
                    border: "1px solid var(--accent-line)", borderRadius: `var(${v})`,
                  }}
                />
                <div className="ds-eyebrow" style={{ marginTop: 8 }}>{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Components ── */}
      <section className="ds-section">
        <Eyebrow>Buttons</Eyebrow>
        <div className="ds-row">
          <Button variant="primary">Generate test-fit</Button>
          <Button variant="ghost">Reset</Button>
          <Button variant="quiet">Learn more</Button>
          <Button variant="primary" disabled>Working…</Button>
        </div>
      </section>

      <section className="ds-section">
        <Eyebrow>Inputs</Eyebrow>
        <div className="ds-row" style={{ alignItems: "flex-start", maxWidth: 620 }}>
          <div style={{ flex: 1 }}>
            <Field label="Headcount" placeholder="e.g. 42" hint="Leave blank to derive from area." />
          </div>
          <div style={{ flex: 1 }}>
            <Field label="Density (rsf / person)" defaultValue="175" />
          </div>
        </div>
      </section>

      <section className="ds-section">
        <Eyebrow>Tags</Eyebrow>
        <div className="ds-row">
          <Tag swatch={{ fill: "rgba(184,85,47,0.11)", stroke: "rgba(184,85,47,0.5)" }}>Workstation</Tag>
          <Tag swatch={{ fill: "rgba(26,24,19,0.045)", stroke: "rgba(26,24,19,0.34)" }}>Office</Tag>
          <Tag swatch={{ fill: "rgba(26,24,19,0.07)", stroke: "rgba(26,24,19,0.4)" }}>Meeting</Tag>
          <Tag accent>budgetary</Tag>
        </div>
      </section>

      <section className="ds-section">
        <Eyebrow>Stats</Eyebrow>
        <div className="ds-row" style={{ gap: 56 }}>
          <Stat value="7,500" label="usable sf" />
          <Stat value="89" label="workstations" />
          <Stat value="$176,613" label="budgetary total" accent />
        </div>
      </section>

      <section className="ds-section">
        <Eyebrow>Surfaces &amp; callouts</Eyebrow>
        <div className="ds-grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 22 }}>
          <Card variant="flat">
            <Eyebrow>Flat card</Eyebrow>
            <p className="ds-body" style={{ marginBottom: 0 }}>The default panel surface — a hairline on paper.</p>
          </Card>
          <Card variant="raised">
            <Eyebrow>Raised card</Eyebrow>
            <p className="ds-body" style={{ marginBottom: 0 }}>A whisper of elevation for moments that lift.</p>
          </Card>
          <Callout>Budgetary — list minus the dealer’s standard discount. A dealer confirms the firm number.</Callout>
          <Callout quiet>Vector input for the pilot; raster floor plans need a human confirm step.</Callout>
        </div>
      </section>

      <section className="ds-section">
        <Eyebrow>Segmented control</Eyebrow>
        <Segmented
          value={seg}
          onChange={setSeg}
          options={[
            { value: "day", label: "Day" },
            { value: "week", label: "Week" },
            { value: "month", label: "Month" },
          ]}
        />
      </section>

      <Divider style={{ marginTop: 40 }} />
      <p className="ds-eyebrow" style={{ marginTop: 22 }}>End of system · {COLORS.length} colors · 7 type styles · 8 components</p>
    </div>
  );
}
