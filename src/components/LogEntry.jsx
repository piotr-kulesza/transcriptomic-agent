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

export default function LogEntry({ entry }) {
  const [expanded, setExpanded] = useState(false);
  const ac = ACTION_COLORS[entry.action] || "#94a3b8";

  const isStep = entry.type === "thinking";

  return (
    <div className="ent" style={{ marginBottom: isStep ? 20 : 10, marginTop: isStep ? 16 : 0, paddingLeft: isStep ? 0 : 14, borderLeft: isStep ? "none" : "2px solid #21262d" }}>
      <div
        style={{ display: "flex", alignItems: "flex-start", gap: 9, cursor: entry.type === "result" ? "pointer" : "default" }}
        onClick={() => entry.type === "result" && setExpanded(e => !e)}
      >
        <div style={{ flex: 1, minWidth: 0 }}>

          {entry.type === "thinking" && (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, height: 1, background: "#1e293b" }} />
              <span style={{ fontSize: 11, color: "#2dd4bf", letterSpacing: 0.8, whiteSpace: "nowrap", fontWeight: 600, opacity: 0.8 }}>
                {entry.text.replace("Agent thinking... ", "").toUpperCase()}
              </span>
              <div style={{ flex: 1, height: 1, background: "#1e293b" }} />
            </div>
          )}

          {entry.type === "thought" && (
            <div style={{ fontSize: 14, color: "#c9d1d9", lineHeight: 1.7 }}>{entry.text}</div>
          )}

          {entry.type === "code" && (
            <div>
              <div style={{ fontSize: 12, color: "#a78bfa", marginBottom: 5, fontWeight: 500 }}>Custom code</div>
              <pre style={{ padding: 10, background: "#161b22", border: "1px solid #2a1f4a", fontSize: 12, color: "#c4b5fd", overflowX: "auto", maxHeight: 160, lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                {entry.code}
              </pre>
            </div>
          )}

          {entry.type === "result" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                <span
                  className="tag"
                  style={{ background: `${ac}15`, color: ac, fontWeight: 600, fontSize: 11, fontFamily: "'JetBrains Mono',monospace", border: `1px solid ${ac}30` }}
                >
                  {entry.action}
                </span>
                <span style={{ fontSize: 13, color: "#8b949e", flex: 1 }}>{entry.summary}</span>
                <span style={{ fontSize: 12, color: "#334155" }}>{expanded ? "▲" : "▼"}</span>
              </div>
              {expanded && (
                <pre style={{ marginTop: 8, padding: 10, background: "#0d1117", border: "1px solid #21262d", fontSize: 12, color: "#64748b", overflowX: "auto", maxHeight: 300, overflowY: "auto", lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                  {JSON.stringify(entry.result, null, 2).slice(0, 4000)}
                </pre>
              )}
            </div>
          )}

          {entry.type === "hypothesis_propose" && (
            <div style={{ padding: "9px 12px", background: "#161b22", border: "1px solid #1e3a5f", borderRadius: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <span className="tag" style={{ background: "#1e3a5f", color: "#60a5fa", fontSize: 11 }}>
                  {entry.hypothesis.id}
                </span>
                <span style={{ fontSize: 12, color: "#60a5fa", fontWeight: 500 }}>New hypothesis</span>
              </div>
              <div style={{ fontSize: 13, color: "#c9d1d9", lineHeight: 1.6 }}>{entry.hypothesis.text}</div>
            </div>
          )}

          {entry.type === "hypothesis_eval" && (() => {
            const vs = VERDICT_STYLE[entry.hypothesis.status] || VERDICT_STYLE.uncertain;
            return (
              <div style={{ padding: "9px 12px", background: "#161b22", border: `1px solid ${vs.color}30`, borderRadius: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                  <span className="tag" style={{ background: `${vs.color}15`, color: vs.color, fontSize: 11, border: `1px solid ${vs.color}30` }}>
                    {entry.hypothesis.id}
                  </span>
                  <span style={{ fontSize: 12, color: vs.color, fontWeight: 500 }}>{vs.icon} {vs.label}</span>
                </div>
                {entry.reasoning && (
                  <div style={{ fontSize: 13, color: "#8b949e", lineHeight: 1.6 }}>{entry.reasoning}</div>
                )}
              </div>
            );
          })()}

          {entry.type === "mode" && (
            <div style={{
              padding: "5px 10px",
              background: "#161b22",
              border: "1px solid #21262d",
              borderRadius: 4,
              fontSize: 12,
              color: entry.mode === "reproduce" ? "#2dd4bf" : "#c084fc",
              marginBottom: 8,
            }}>
              {entry.mode === "reproduce"
                ? "Reproduce mode — temperature=0, fully deterministic"
                : "Explore mode — temperature=1, creative exploration"}
            </div>
          )}

          {entry.type === "seed" && (
            <div style={{ padding: "9px 12px", background: "#161b22", border: "1px solid #1e293b", borderLeft: "3px solid #60a5fa", borderRadius: 6 }}>
              <div style={{ fontSize: 11, color: "#60a5fa", letterSpacing: 0.5, marginBottom: 6, fontWeight: 600, textTransform: "uppercase" }}>Statistical Pre-Analysis</div>
              {entry.summary
                ? <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.7, whiteSpace: "pre-line" }}>{entry.summary}</div>
                : <div style={{ fontSize: 12, color: "#334155" }}>No common groups across datasets — agent starting without seed hypotheses.</div>
              }
            </div>
          )}

          {entry.type === "error" && (
            <span style={{ fontSize: 13, color: "#f87171" }}>{entry.text}</span>
          )}

          {entry.type === "done" && !entry.exhausted && (
            <span style={{ fontSize: 14, color: "#4ade80", fontWeight: 600 }}>{entry.text}</span>
          )}

          {entry.type === "done" && entry.exhausted && (
            <span style={{ fontSize: 13, color: "#fbbf24" }}>⚠ {entry.text}</span>
          )}

        </div>
      </div>
    </div>
  );
}
