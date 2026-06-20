import { FONT_MONO } from "../theme";

/* Coverage map — the deterministic coverage grid the backend builds before the
   loop (G1, G2, …). Those grid cells are streamed as ordinary hypotheses that
   carry question_type + tool_params + a live status, so this dock is derived
   entirely client-side from the hypotheses array; no backend payload needed.
   Rows = question type; one cell per grid hypothesis, coloured by its verdict. */

const QT = {
  gradient:         { order: 0, label: "Gradient" },
  specificity:      { order: 1, label: "Specificity" },
  shared_vs_unique: { order: 2, label: "Shared / unique" },
  biomarker:        { order: 3, label: "Biomarker" },
  hub:              { order: 4, label: "Hub" },
  subtype:          { order: 5, label: "Subtype" },
};

const isGridCell = (h) => typeof h.id === "string" && /^G\d+$/.test(h.id) && h.question_type;

function cellLabel(h) {
  const p = h.tool_params || {};
  switch (h.question_type) {
    case "gradient":         return "all groups";
    case "specificity":      return `${p.group} vs rest`;
    case "shared_vs_unique": return `${p.comparisonA_groupA}/${p.comparisonA_groupB} × ${p.comparisonB_groupA}/${p.comparisonB_groupB}`;
    case "biomarker":        return `${p.groupA} vs ${p.groupB}`;
    case "hub":              return p.datasetName || `${p.groupA} vs ${p.groupB}`;
    case "subtype":          return `${p.datasetName}: ${p.group}`;
    default:                 return h.question_type;
  }
}

function cellStyle(status, t) {
  switch (status) {
    case "confirmed": return { background: t.confirmedSoft, border: `1px solid ${t.confirmedBd}` };
    case "uncertain": return { background: t.uncertainSoft, border: `1px solid ${t.uncertainBd}` };
    case "rejected":  return { background: t.rejectedSoft,  border: `1px solid ${t.rejectedBd}` };
    case "testing":   return { background: t.accentSoft,    border: `1px solid ${t.accent}` };
    default:          return { background: "transparent",   border: `1px solid ${t.borderStrong}` }; // pending
  }
}

export default function CoverageDock({ hypotheses, theme: t }) {
  const cells = hypotheses.filter(isGridCell);
  if (cells.length === 0) return null;

  // group by question type, ordered
  const rows = {};
  for (const h of cells) (rows[h.question_type] ||= []).push(h);
  const ordered = Object.keys(rows).sort((a, b) => (QT[a]?.order ?? 99) - (QT[b]?.order ?? 99));

  const Legend = ({ status, label }) => (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 9.5, color: t.textMuted }}>
      <i style={{ width: 9, height: 9, borderRadius: 2, display: "inline-block", ...cellStyle(status, t) }} />
      {label}
    </span>
  );

  return (
    <div style={{ flex: "none", borderTop: `1px solid ${t.border}`, background: t.sidebarBg, padding: "10px 16px", display: "flex", gap: 16, alignItems: "flex-start", overflowX: "auto" }}>
      <span style={{ flex: "none", fontSize: 9.5, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: t.textMuted, lineHeight: 1.3, paddingTop: 2 }}>
        Coverage<br />map
      </span>

      <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 5 }}>
        {ordered.map((qt) => (
          <div key={qt} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ flex: "none", width: 92, fontSize: 10, color: t.textMuted }}>{QT[qt]?.label || qt}</span>
            <div style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
              {rows[qt].map((h) => (
                <div key={h.id} title={`${h.id} · ${cellLabel(h)} · ${h.status}`}
                  style={{ width: 14, height: 14, borderRadius: 3, cursor: "default", ...cellStyle(h.status, t) }} />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div style={{ flex: "none", display: "flex", flexDirection: "column", gap: 3, paddingTop: 1 }}>
        <Legend status="confirmed" label="confirmed" />
        <Legend status="uncertain" label="uncertain" />
        <Legend status="rejected" label="rejected" />
        <Legend status="pending" label="pending" />
      </div>
    </div>
  );
}
