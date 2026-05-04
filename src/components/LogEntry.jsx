import { useState } from "react";

const ACTION_COLORS = {
  dataset_summary:           "#8b949e",
  top_variable_genes:        "#6e9fd4",
  differential_expression:   "#c98ea8",
  gene_expression_by_group:  "#7ab87a",
  nonlinear_rule:            "#c8a066",
  contextual_modules:        "#b8a84a",
  pathway_enrichment:        "#8ab86a",
  batch_detection:           "#9a80b8",
  subgroup_discovery:        "#6ab8c8",
  gene_network_hub:          "#b8b860",
  cross_dataset_de:          "#3fb950",
  cross_dataset_correlation: "#39d3f2",
  invariant_axis:            "#d29922",
  cross_dataset_rewiring:    "#d08830",
  execute_code:              "#a371f7",
};

const VERDICT_STYLE = {
  confirmed: { color: "#3fb950", icon: "✓", label: "Confirmed" },
  rejected:  { color: "#f85149", icon: "✗", label: "Rejected"  },
  uncertain: { color: "#d29922", icon: "?", label: "Uncertain"  },
  pending:   { color: "#388bfd", icon: "○", label: "Pending"    },
};

export default function LogEntry({ entry }) {
  const [expanded, setExpanded] = useState(false);
  const ac = ACTION_COLORS[entry.action] || "#8b949e";

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
              <div style={{ flex: 1, height: 1, background: "#21262d" }} />
              <span style={{ fontSize: 11, color: "#6e7681", letterSpacing: 0.8, whiteSpace: "nowrap", fontWeight: 500 }}>
                {entry.text.replace("Agent thinking... ", "").toUpperCase()}
              </span>
              <div style={{ flex: 1, height: 1, background: "#21262d" }} />
            </div>
          )}

          {entry.type === "thought" && (
            <div style={{ fontSize: 14, color: "#c9d1d9", lineHeight: 1.7 }}>{entry.text}</div>
          )}

          {entry.type === "code" && (
            <div>
              <div style={{ fontSize: 12, color: "#a371f7", marginBottom: 5 }}>Custom code</div>
              <pre style={{ padding: 10, background: "#161b22", border: "1px solid #30363d", fontSize: 12, color: "#c9d1d9", overflowX: "auto", maxHeight: 160, lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                {entry.code}
              </pre>
            </div>
          )}

          {entry.type === "result" && (
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                <span
                  className="tag"
                  style={{ background: `${ac}18`, color: ac, fontWeight: entry.isCross || entry.isDynamic ? 700 : 500, fontSize: 11, fontFamily: "'JetBrains Mono',monospace" }}
                >
                  {entry.action}
                </span>
                <span style={{ fontSize: 13, color: "#8b949e", flex: 1 }}>{entry.summary}</span>
                <span style={{ fontSize: 12, color: "#484f58" }}>{expanded ? "▲" : "▼"}</span>
              </div>
              {expanded && (
                <pre style={{ marginTop: 8, padding: 10, background: "#161b22", border: "1px solid #21262d", fontSize: 12, color: "#8b949e", overflowX: "auto", maxHeight: 300, overflowY: "auto", lineHeight: 1.6, borderRadius: 6, fontFamily: "'JetBrains Mono',monospace" }}>
                  {JSON.stringify(entry.result, null, 2).slice(0, 4000)}
                </pre>
              )}
            </div>
          )}

          {entry.type === "hypothesis_propose" && (
            <div style={{ padding: "9px 12px", background: "#161b22", border: "1px solid #1f3a6e", borderRadius: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                <span className="tag" style={{ background: "#1f3a6e", color: "#79c0ff", fontSize: 11 }}>
                  {entry.hypothesis.id}
                </span>
                <span style={{ fontSize: 12, color: "#6e9fd4" }}>New hypothesis</span>
              </div>
              <div style={{ fontSize: 13, color: "#c9d1d9", lineHeight: 1.6 }}>{entry.hypothesis.text}</div>
            </div>
          )}

          {entry.type === "hypothesis_eval" && (() => {
            const vs = VERDICT_STYLE[entry.hypothesis.status] || VERDICT_STYLE.uncertain;
            return (
              <div style={{ padding: "9px 12px", background: "#161b22", border: `1px solid ${vs.color}33`, borderRadius: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
                  <span className="tag" style={{ background: `${vs.color}18`, color: vs.color, fontSize: 11 }}>
                    {entry.hypothesis.id}
                  </span>
                  <span style={{ fontSize: 12, color: vs.color }}>{vs.icon} {vs.label}</span>
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
              color: entry.mode === "reproduce" ? "#3fb950" : "#a371f7",
              marginBottom: 8,
            }}>
              {entry.mode === "reproduce"
                ? "Reproduce mode — temperature=0, fully deterministic"
                : "Explore mode — temperature=1, creative exploration"}
            </div>
          )}

          {entry.type === "seed" && (
            <div style={{ padding: "9px 12px", background: "#161b22", border: "1px solid #1f3464", borderRadius: 6 }}>
              <div style={{ fontSize: 11, color: "#6e9fd4", letterSpacing: 0.5, marginBottom: 5, fontWeight: 600, textTransform: "uppercase" }}>Statistical Pre-Analysis</div>
              {entry.summary
                ? <div style={{ fontSize: 12, color: "#8b949e", lineHeight: 1.7, whiteSpace: "pre-line" }}>{entry.summary}</div>
                : <div style={{ fontSize: 12, color: "#484f58" }}>No common groups across datasets — agent starting without seed hypotheses.</div>
              }
            </div>
          )}

          {entry.type === "error" && (
            <span style={{ fontSize: 13, color: "#f85149" }}>{entry.text}</span>
          )}

          {entry.type === "done" && !entry.exhausted && (
            <span style={{ fontSize: 14, color: "#3fb950", fontWeight: 600 }}>{entry.text}</span>
          )}

          {entry.type === "done" && entry.exhausted && (
            <span style={{ fontSize: 13, color: "#d29922" }}>⚠ {entry.text}</span>
          )}

        </div>
      </div>
    </div>
  );
}
