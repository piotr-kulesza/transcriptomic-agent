import { useState } from "react";
import { verdictStyle } from "../theme";

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

function ResultTable({ rows, t }) {
  if (!rows || rows.length === 0) return null;
  const keys = Object.keys(rows[0]);
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "'IBM Plex Mono',ui-monospace,monospace" }}>
      <thead>
        <tr>
          {keys.map(k => (
            <th key={k} style={{ textAlign: "left", padding: "3px 8px", color: t.textMuted, fontWeight: 600, borderBottom: `1px solid ${t.border}`, fontSize: 10, textTransform: "uppercase", letterSpacing: 0.5, whiteSpace: "nowrap" }}>
              {k}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} style={{ background: i % 2 === 0 ? "transparent" : `${t.border}60` }}>
            {keys.map(k => (
              <td key={k} style={{ padding: "3px 8px", color: t.textSecondary, whiteSpace: "nowrap" }}>
                {String(row[k] ?? "")}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderResult(result, t) {
  if (!result || typeof result !== "object") {
    return <pre style={{ fontSize: 11, color: t.textMuted, fontFamily: "'IBM Plex Mono',ui-monospace,monospace", whiteSpace: "pre-wrap", margin: 0 }}>{String(result)}</pre>;
  }
  if (result.error) {
    return <span style={{ fontSize: 12, color: "#f87171" }}>{result.error}</span>;
  }

  const scalars = [];
  const tables  = [];

  for (const [key, value] of Object.entries(result)) {
    if (value === null || value === undefined) continue;
    if (Array.isArray(value)) {
      if (value.length === 0) continue;
      if (typeof value[0] === "object" && value[0] !== null) {
        tables.push([key, value]);
      } else {
        // array of primitives — show count + preview, skip huge gene lists
        const preview = value.length > 8 ? `${value.slice(0, 8).join(", ")} … (${value.length} total)` : value.join(", ");
        scalars.push([key, preview]);
      }
    } else if (typeof value !== "object") {
      scalars.push([key, value]);
    }
  }

  // If nothing structured, fall back to JSON
  if (scalars.length === 0 && tables.length === 0) {
    return (
      <pre style={{ fontSize: 11, color: t.textMuted, fontFamily: "'IBM Plex Mono',ui-monospace,monospace", whiteSpace: "pre-wrap", margin: 0 }}>
        {JSON.stringify(result, null, 2).slice(0, 4000)}
      </pre>
    );
  }

  return (
    <div>
      {scalars.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 20px", marginBottom: tables.length > 0 ? 10 : 0 }}>
          {scalars.map(([k, v]) => (
            <span key={k} style={{ fontSize: 11, color: t.textMuted, fontFamily: "'IBM Plex Mono',ui-monospace,monospace" }}>
              <span style={{ color: t.textSecondary }}>{k}:</span> {String(v)}
            </span>
          ))}
        </div>
      )}
      {tables.map(([key, rows]) => (
        <div key={key} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 10, color: t.textMuted, textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 4 }}>{key}</div>
          <div style={{ overflowX: "auto" }}>
            <ResultTable rows={rows} t={t} />
          </div>
        </div>
      ))}
    </div>
  );
}

function renderThought(text, t) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return parts.map((part, i) => {
    if (part.startsWith("```")) {
      const body = part.slice(3, -3).replace(/^\w+\n/, "");
      return (
        <pre key={i} style={{ margin: "8px 0", padding: "10px 12px", background: t.appBg, border: `1px solid ${t.border}`, fontSize: 12, color: t.codeText, overflowX: "auto", lineHeight: 1.6, borderRadius: 6, fontFamily: "'IBM Plex Mono',ui-monospace,monospace", whiteSpace: "pre-wrap" }}>
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
              <div style={{ fontSize: 10, color: t.codeText, marginBottom: 4, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>Code</div>
              <pre style={{ padding: "7px 10px", background: t.appBg, border: `1px solid ${t.border}`, fontSize: 10, color: t.codeText, overflowX: "auto", maxHeight: 120, overflowY: "auto", lineHeight: 1.5, borderRadius: 6, fontFamily: "'IBM Plex Mono',ui-monospace,monospace" }}>
                {entry.code}
              </pre>
            </div>
          )}

          {entry.type === "result" && (
            <div style={{ paddingLeft: 16, borderLeft: `2px solid ${ac}35` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 6 }}>
                <span className="tag" style={{ background: `${ac}15`, color: ac, fontWeight: 600, fontSize: 11, fontFamily: "'IBM Plex Mono',ui-monospace,monospace", border: `1px solid ${ac}30` }}>
                  {entry.action}
                </span>
                <span style={{ fontSize: 13, color: t.textSecondary, flex: 1, lineHeight: 1.5 }}>{entry.summary}</span>
              </div>
              <div style={{ padding: "8px 10px", background: t.appBg, border: `1px solid ${t.border}`, borderRadius: 6, maxHeight: 320, overflowY: "auto" }}>
                {renderResult(entry.result, t)}
              </div>
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
            const vs = verdictStyle(t, entry.hypothesis.status);
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
                : <div style={{ fontSize: 12, color: t.textMuted }}>Pre-analysis produced no results — check that datasets are log-transformed and group columns are set correctly.</div>
              }
            </div>
          )}

          {entry.type === "error" && (
            <div style={{ fontSize: 13, color: "#f87171", padding: "6px 10px", background: "#f8717110", border: "1px solid #f8717125", borderRadius: 4 }}>
              {entry.text}
            </div>
          )}

          {entry.type === "done" && !entry.exhausted && (
            <div style={{ marginTop: 12, borderRadius: 8, overflow: "hidden", background: "#0d2818", border: "1px solid #4ade8025" }}>
              <div style={{ padding: "10px 16px", background: "#0a2014", borderBottom: "1px solid #4ade8020", display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 14, lineHeight: 1, color: "#4ade80" }}>✓</span>
                <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1.5, textTransform: "uppercase", color: "#4ade80" }}>Analysis Complete</span>
              </div>
              <div style={{ padding: "16px 20px" }}>
                {renderSummary(entry.text, { ...t, textPrimary: "#dcfce7", textSecondary: "#86efac", accent: "#4ade80" })}
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
