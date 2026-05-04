import { useState } from "react";

const ACTION_COLORS = {
  dataset_summary:           "#94a3b8",
  top_variable_genes:        "#60a5fa",
  differential_expression:   "#f472b6",
  gene_expression_by_group:  "#4ade80",
  nonlinear_rule:            "#fb923c",
  contextual_modules:        "#facc15",
  pathway_enrichment:        "#a3e635",
  batch_detection:           "#c084fc",
  subgroup_discovery:        "#22d3ee",
  gene_network_hub:          "#fbbf24",
  cross_dataset_de:          "#34d399",
  cross_dataset_correlation: "#38bdf8",
  invariant_axis:            "#f59e0b",
  cross_dataset_rewiring:    "#fb7185",
  execute_code:              "#a78bfa",
};

const VERDICT_STYLE = {
  confirmed: { color: "#4ade80", icon: "✓", label: "Confirmed" },
  rejected:  { color: "#f87171", icon: "✗", label: "Rejected"  },
  uncertain: { color: "#fbbf24", icon: "?", label: "Uncertain"  },
  pending:   { color: "#94a3b8", icon: "○", label: "Pending"    },
};

function renderInline(text, t) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} style={{ color: t.textPrimary, fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
    }
    return <span key={i}>{part}</span>;
  });
}

function renderSummary(text, t) {
  const lines = text.split("\n");
  const elements = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} style={{ margin: "4px 0 12px 0", paddingLeft: 20 }}>
          {listItems}
        </ul>
      );
      listItems = [];
    }
  };

  lines.forEach((line, i) => {
    if (line.startsWith("## ")) {
      flushList();
      elements.push(
        <div key={i} style={{ fontSize: 11, fontWeight: 700, color: "#4ade80", letterSpacing: 1.2, textTransform: "uppercase", marginTop: elements.length === 0 ? 0 : 14, marginBottom: 6 }}>
          {line.slice(3)}
        </div>
      );
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      listItems.push(
        <li key={i} style={{ fontSize: 13, color: t.textSecondary, lineHeight: 1.65, marginBottom: 3 }}>
          {renderInline(line.slice(2), t)}
        </li>
      );
    } else if (line.trim()) {
      flushList();
      elements.push(
        <div key={i} style={{ fontSize: 13, color: t.textSecondary, lineHeight: 1.75, marginBottom: 4 }}>
          {renderInline(line, t)}
        </div>
      );
    }
  });
  flushList();
  return elements;
}

function renderThought(text, t) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith("```")) {
      const body = part.slice(3, -3).replace(/^\w+\n/, "");
      return (
        <pre key={i} style={{ margin: "8px 0", padding: "10px 12px", background: t.appBg, border: `1px solid ${t.border}`, fontSize: 12, color: t.codeText, overflowX: "auto", lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace", whiteSpace: "pre-wrap" }}>
          {body}
        </pre>
      );
    }
    if (!part) return null;
    return <span key={i} style={{ whiteSpace: "pre-wrap" }}>{part}</span>;
  });
}

export default function LogEntry({ entry, theme: t }) {
  const [expanded, setExpanded] = useState(true);
  const ac = ACTION_COLORS[entry.action] || "#94a3b8";
  const isStep = entry.type === "thinking";

  return (
    <div className="ent" style={{ marginBottom: isStep ? 24 : 8, marginTop: isStep ? 20 : 0 }}>
      <div style={{ display: "flex", alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>

          {entry.type === "thinking" && (
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, height: 1, background: t.border }} />
              <span style={{ fontSize: 10, color: t.accent, letterSpacing: 1.5, whiteSpace: "nowrap", fontWeight: 700, textTransform: "uppercase" }}>
                {entry.text.replace("Agent thinking... ", "")}
              </span>
              <div style={{ flex: 1, height: 1, background: t.border }} />
            </div>
          )}

          {entry.type === "thought" && (
            <div style={{ fontSize: 14, color: t.textPrimary, lineHeight: 1.75, paddingLeft: 16, borderLeft: `2px solid ${t.border}` }}>
              {renderThought(entry.text, t)}
            </div>
          )}

          {entry.type === "code" && (
            <div style={{ paddingLeft: 16, borderLeft: `2px solid ${t.border}` }}>
              <div style={{ fontSize: 10, color: t.codeText, marginBottom: 6, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>Code</div>
              <pre style={{ padding: "10px 12px", background: t.appBg, border: `1px solid ${t.border}`, fontSize: 12, color: t.codeText, overflowX: "auto", maxHeight: 180, lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                {entry.code}
              </pre>
            </div>
          )}

          {entry.type === "result" && (
            <div style={{ paddingLeft: 16, borderLeft: `2px solid ${ac}35` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                <span className="tag" style={{ background: `${ac}15`, color: ac, fontWeight: 600, fontSize: 11, fontFamily: "'JetBrains Mono',monospace", border: `1px solid ${ac}30` }}>
                  {entry.action}
                </span>
                <span style={{ fontSize: 13, color: t.textSecondary, flex: 1, lineHeight: 1.5 }}>{entry.summary}</span>
              </div>
              <pre style={{ margin: 0, padding: "10px 12px", background: t.appBg, border: `1px solid ${t.border}`, fontSize: 12, color: t.textMuted, overflowX: "auto", maxHeight: 400, overflowY: "auto", lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                {JSON.stringify(entry.result, null, 2).slice(0, 6000)}
              </pre>
            </div>
          )}

          {entry.type === "hypothesis_propose" && (
            <div style={{ padding: "10px 14px", background: t.cardBg, border: `1px solid ${t.accent}22`, borderLeft: `3px solid ${t.accent}`, borderRadius: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <span className="tag" style={{ background: `${t.accent}18`, color: t.accent, fontSize: 11, border: `1px solid ${t.accent}30` }}>
                  {entry.hypothesis.id}
                </span>
                <span style={{ fontSize: 10, color: t.accent, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>New hypothesis</span>
              </div>
              <div style={{ fontSize: 13, color: t.textPrimary, lineHeight: 1.65 }}>{entry.hypothesis.text}</div>
            </div>
          )}

          {entry.type === "hypothesis_eval" && (() => {
            const vs = VERDICT_STYLE[entry.hypothesis.status] || VERDICT_STYLE.uncertain;
            return (
              <div style={{ padding: "10px 14px", background: t.cardBg, border: `1px solid ${vs.color}22`, borderLeft: `3px solid ${vs.color}`, borderRadius: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: entry.reasoning ? 6 : 0 }}>
                  <span className="tag" style={{ background: `${vs.color}15`, color: vs.color, fontSize: 11, border: `1px solid ${vs.color}30` }}>
                    {entry.hypothesis.id}
                  </span>
                  <span style={{ fontSize: 10, color: vs.color, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>{vs.icon} {vs.label}</span>
                </div>
                {entry.reasoning && (
                  <div style={{ fontSize: 13, color: t.textSecondary, lineHeight: 1.65 }}>{entry.reasoning}</div>
                )}
              </div>
            );
          })()}

          {entry.type === "mode" && (
            <div style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "4px 10px", background: t.cardBg, border: `1px solid ${t.border}`, borderRadius: 4, fontSize: 12, color: entry.mode === "reproduce" ? t.accent : "#c084fc", marginBottom: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor", opacity: 0.7, flexShrink: 0 }} />
              {entry.mode === "reproduce" ? "Reproduce — deterministic" : "Explore — creative"}
            </div>
          )}

          {entry.type === "seed" && (
            <div style={{ padding: "12px 14px", background: t.cardBg, border: `1px solid ${t.border}`, borderLeft: "3px solid #60a5fa", borderRadius: 6 }}>
              <div style={{ fontSize: 10, color: "#60a5fa", letterSpacing: 1.5, marginBottom: 8, fontWeight: 700, textTransform: "uppercase" }}>Pre-Analysis</div>
              {entry.summary
                ? <div style={{ fontSize: 12, color: t.textSecondary, lineHeight: 1.75, whiteSpace: "pre-line" }}>{entry.summary}</div>
                : <div style={{ fontSize: 12, color: t.textMuted }}>No common groups across datasets — starting without seed hypotheses.</div>
              }
            </div>
          )}

          {entry.type === "error" && (
            <div style={{ fontSize: 13, color: "#f87171", padding: "6px 10px", background: "#f8717110", border: "1px solid #f8717125", borderRadius: 4 }}>
              {entry.text}
            </div>
          )}

          {entry.type === "done" && !entry.exhausted && (
            <div style={{ marginTop: 12, borderRadius: 8, overflow: "hidden", background: "#4ade80", color: "#052e16" }}>
              <div style={{ padding: "10px 16px", background: "#22c55e", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 15, lineHeight: 1 }}>✓</span>
                <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase" }}>Analysis Complete</span>
              </div>
              <div style={{ padding: "16px 20px" }}>
                {renderSummary(entry.text, { ...t, textPrimary: "#052e16", textSecondary: "#14532d", accent: "#15803d" })}
              </div>
            </div>
          )}

          {entry.type === "done" && entry.exhausted && (
            <div style={{ fontSize: 13, color: "#fbbf24", padding: "6px 10px", background: "#fbbf2410", border: "1px solid #fbbf2425", borderRadius: 4 }}>
              ⚠ {entry.text}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
