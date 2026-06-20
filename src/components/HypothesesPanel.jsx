import { useState } from "react";
import { buildCard } from "../cardModel";
import { RADII, FONT_MONO } from "../theme";

/* ── Minimal inline SVG icon set (stroke = currentColor) ─────────────────── */
const Ic = {
  arrowUp:   (s = 11) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 13V3M4 7l4-4 4 4" /></svg>,
  arrowDown: (s = 11) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v10M4 9l4 4 4-4" /></svg>,
  check:     (s = 13) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8.5l3.5 3.5L13 4" /></svg>,
  x:         (s = 13) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4l8 8M12 4l-8 8" /></svg>,
  alert:     (s = 11) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2.2l6 11.3H2z" /><path d="M8 6.5v3.2" /><circle cx="8" cy="11.4" r="0.5" fill="currentColor" stroke="none" /></svg>,
  minus:     (s = 11) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 8h8" /></svg>,
  chevDown:  (s = 12) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M4 6l4 4 4-4" /></svg>,
  link:      (s = 9)  => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6.5 9.5a3 3 0 004.2 0l2-2a3 3 0 00-4.2-4.2l-1 1" /><path d="M9.5 6.5a3 3 0 00-4.2 0l-2 2a3 3 0 004.2 4.2l1-1" /></svg>,
  shield:    (s = 12) => <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 1.8l5.2 2v4.1c0 3.2-2.1 5.4-5.2 6.3-3.1-.9-5.2-3.1-5.2-6.3V3.8z" /></svg>,
  checkCircle:(s = 11)=> <svg width={s} height={s} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><circle cx="8" cy="8" r="6.2" /><path d="M5.2 8.2l1.9 1.9L11 5.8" /></svg>,
};

const VERDICT = {
  confirmed: { label: "Confirmed", icon: Ic.checkCircle, key: "confirmed" },
  uncertain: { label: "Uncertain", icon: Ic.alert,       key: "uncertain" },
  rejected:  { label: "Rejected",  icon: Ic.minus,        key: "rejected" },
  testing:   { label: "Testing",   icon: null,            key: "accent" },
  pending:   { label: "Pending",   icon: null,            key: "pending" },
};

function badgeColors(state, t) {
  switch (state) {
    case "confirmed": return { color: t.confirmed, bg: t.confirmedSoft, border: "transparent" };
    case "uncertain": return { color: t.uncertain, bg: t.uncertainSoft, border: "transparent" };
    case "rejected":  return { color: t.rejected,  bg: t.rejectedSoft,  border: "transparent" };
    case "testing":   return { color: t.accent,    bg: t.accentSoft,    border: "transparent" };
    default:          return { color: t.textMuted, bg: "transparent",   border: t.borderStrong };
  }
}

function railColor(state, t) {
  return { confirmed: t.confirmed, uncertain: t.uncertain, rejected: t.rejectedBd, testing: t.accent }[state] || "transparent";
}

function VerdictBadge({ state, t }) {
  const v = VERDICT[state] || VERDICT.pending;
  const c = badgeColors(state, t);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 99, whiteSpace: "nowrap", flex: "none", color: c.color, background: c.bg, border: `1px solid ${c.border}` }}>
      {v.icon ? v.icon() : null}
      {v.label}
    </span>
  );
}

function Direction({ d, t }) {
  const isFlat = d.reg === "flat";
  const regColor = d.reg === "up" ? t.up : d.reg === "down" ? t.down : t.textFaint;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, color: t.textSecondary }}>
      <span style={{ color: t.textMuted }}>{d.grp}</span>
      <span style={{ fontFamily: FONT_MONO, fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 2, color: regColor }}>
        {isFlat ? <>{Ic.minus()} n.s.</> : d.reg === "up" ? Ic.arrowUp() : Ic.arrowDown()}
      </span>
    </span>
  );
}

function ReplMini({ replication, t }) {
  if (!replication.length) return null;
  const ok = replication.filter((r) => r.status === "ok").length;
  const dotColor = (s) => (s === "ok" ? t.confirmed : s === "warn" ? t.uncertain : t.rejectedBd);
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: "auto" }}>
      <span style={{ fontSize: 10, color: t.textMuted }}>{ok}/{replication.length} cohorts</span>
      <span style={{ display: "flex", gap: 2 }}>
        {replication.map((r, i) => <i key={i} style={{ width: 6, height: 6, borderRadius: 99, background: dotColor(r.status), display: "inline-block" }} />)}
      </span>
    </span>
  );
}

const ladderRowStyle = (t) => ({ display: "flex", alignItems: "center", gap: 8, padding: "7px 9px", borderRadius: RADII.sm, background: t.sidebarBg, border: `1px solid ${t.border}` });

function Evidence({ card, t }) {
  const heteroFlag = card.heterogeneity && (card.state === "uncertain" || card.state === "rejected");
  const markColor = (s) => (s === "ok" ? t.confirmed : s === "warn" ? t.uncertain : t.rejected);
  return (
    <div style={{ borderTop: `1px solid ${t.border}`, padding: 12, display: "flex", flexDirection: "column", gap: 14, background: t.surface2 }}>
      {/* effect direction */}
      {card.directions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <div style={evTitleStyle(t)}>Effect direction</div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            {card.directions.map((d, i) => <Direction key={i} d={d} t={t} />)}
          </div>
        </div>
      )}

      {/* evidence ladder */}
      <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
        <div style={evTitleStyle(t)}>
          Evidence ladder
          {heteroFlag && (
            <span style={{ color: t.warning, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9.5 }}>
              {Ic.alert()} cohorts disagree
            </span>
          )}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {card.methodFamilies.length > 0 && (
            <div style={ladderRowStyle(t)}>
              <span style={{ fontSize: 10.5, color: t.textMuted }}>Method families</span>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginLeft: "auto" }}>
                {card.methodFamilies.map((mf, i) => (
                  <span key={i} style={{ fontFamily: FONT_MONO, fontSize: 9.5, fontWeight: 500, padding: "2px 6px", borderRadius: 99, border: `1px solid ${t.confirmedBd}`, color: t.confirmed, background: t.confirmedSoft }}>{mf.name}</span>
                ))}
              </div>
            </div>
          )}
          {card.replication.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {card.replication.map((r, i) => (
                <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 10.5, padding: "5px 8px", borderRadius: RADII.sm, background: t.sidebarBg, border: `1px solid ${t.border}` }}>
                  <span style={{ width: 14, height: 14, display: "grid", placeItems: "center", flex: "none", color: markColor(r.status) }}>
                    {r.status === "ok" ? Ic.check() : r.status === "warn" ? Ic.alert() : Ic.x()}
                  </span>
                  <span style={{ fontFamily: FONT_MONO, color: t.textPrimary, fontSize: 10.5 }}>{r.acc}</span>
                  <span style={{ marginLeft: "auto", fontFamily: FONT_MONO, fontSize: 10, color: t.textSecondary }}>{r.stat}</span>
                </div>
              ))}
            </div>
          )}
          {card.metaFDR && (
            <div style={ladderRowStyle(t)}>
              <span style={{ fontSize: 10.5, color: t.textMuted }}>Meta-analysis FDR</span>
              <span style={{ fontFamily: FONT_MONO, fontSize: 11, color: t.textPrimary, marginLeft: "auto" }}>{card.metaFDR}</span>
            </div>
          )}
          {card.heterogeneity && (
            <div style={ladderRowStyle(t)}>
              <span style={{ fontSize: 10.5, color: t.textMuted }}>Heterogeneity</span>
              <span style={{ fontFamily: FONT_MONO, fontSize: 11, marginLeft: "auto", color: heteroFlag ? t.warning : t.textPrimary }}>{card.heterogeneity}</span>
            </div>
          )}
        </div>
      </div>

      {/* translational — demoted, annotation only */}
      {card.translational && (
        <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
          <div style={{ ...evTitleStyle(t), color: t.textFaint }}>Translational links</div>
          <div style={{ fontSize: 10, color: t.textFaint, fontStyle: "italic", marginBottom: 7 }}>Annotation only — not evidence for the finding.</div>
          <TransGroup label="Drug targets" items={card.translational.targets} mono t={t} />
          {card.translational.drugs && <TransGroup label="Drugs" items={card.translational.drugs} t={t} />}
          {card.translational.trials && <TransGroup label="Clinical trials" items={card.translational.trials} mono link t={t} />}
        </div>
      )}
    </div>
  );
}

const evTitleStyle = (t) => ({ fontSize: 9.5, fontWeight: 700, letterSpacing: "0.07em", textTransform: "uppercase", color: t.textMuted, display: "flex", alignItems: "center", gap: 6 });

function TransGroup({ label, items, mono, link, t }) {
  if (!items || !items.length) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5, marginBottom: 7 }}>
      <span style={{ fontSize: 9.5, color: t.textMuted, letterSpacing: "0.04em", textTransform: "uppercase" }}>{label}</span>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {items.map((it) => (
          <span key={it} style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, color: t.textSecondary, border: `1px solid ${t.border}`, borderRadius: RADII.sm, padding: "2px 7px", background: t.sidebarBg }}>
            {link && <span style={{ color: t.textFaint, display: "inline-flex" }}>{Ic.link()}</span>}
            <span style={mono ? { fontFamily: FONT_MONO, fontSize: 10 } : undefined}>{it}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function HypCard({ card, expanded, onToggle, t }) {
  const isPending = card.state === "pending";
  const isTesting = card.state === "testing";
  const canExpand = !isPending && (card.replication.length > 0 || card.methodFamilies.length > 0 || card.directions.length > 0);
  return (
    <div style={{
      border: `1px solid ${t.border}`, borderRadius: RADII.lg, background: isPending ? "transparent" : t.cardBg,
      overflow: "hidden", borderStyle: isPending ? "dashed" : "solid",
      borderLeft: railColor(card.state, t) !== "transparent" ? `3px solid ${railColor(card.state, t)}` : `1px solid ${t.border}`,
      boxShadow: expanded ? "var(--shadow-md)" : undefined,
    }}>
      <div style={{ padding: "11px 12px", display: "flex", flexDirection: "column", gap: 9, cursor: canExpand ? "pointer" : "default" }} onClick={() => canExpand && onToggle(card.id)}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
          <span style={{ fontFamily: FONT_MONO, fontSize: 10.5, fontWeight: 600, color: t.textMuted, paddingTop: 2 }}>{card.id}</span>
          <span style={{ fontSize: 12.5, fontWeight: 500, lineHeight: 1.4, letterSpacing: "-0.005em", flex: 1, color: t.textPrimary }}>{card.statement}</span>
          <VerdictBadge state={card.state} t={t} />
        </div>
        {isTesting ? (
          <div style={{ height: 3, borderRadius: 99, background: t.surface3, overflow: "hidden", marginTop: 2 }}>
            <div className="testing-bar-fill" style={{ height: "100%", width: "40%", background: t.accent, borderRadius: 99 }} />
          </div>
        ) : isPending ? null : (
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {card.directions.map((d, i) => <Direction key={i} d={d} t={t} />)}
            </div>
            <ReplMini replication={card.replication} t={t} />
          </div>
        )}
      </div>

      {expanded && canExpand && <Evidence card={card} t={t} />}

      {canExpand && (
        <div onClick={() => onToggle(card.id)} style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 5, fontSize: 10, color: t.textFaint, padding: 5, borderTop: `1px solid ${t.border}`, cursor: "pointer" }}>
          <span style={{ display: "inline-flex", transition: "transform .18s", transform: expanded ? "rotate(180deg)" : "none" }}>{Ic.chevDown()}</span>
          {expanded ? "Hide evidence" : "Show evidence"}
        </div>
      )}
    </div>
  );
}

/* Standing engine-validation facts (structural guarantees of the gate, not
   per-run output). Numbers reflect the evidence gate in backend/agent/engine.py
   and the Tier-1 validation suite (permutation null + limma/fgsea benchmark). */
const RIGOR = [
  { v: "≥2", k: "Cohorts required to confirm" },
  { v: "≥2", k: "Orthogonal method families" },
  { v: "null", k: "Permutation-calibrated gate" },
];

export default function HypothesesPanel({ hypotheses, maxHypotheses, theme: t }) {
  const [expanded, setExpanded] = useState(null);
  const onToggle = (id) => setExpanded((cur) => (cur === id ? null : id));
  const cards = hypotheses.map(buildCard);
  const settled = cards.filter((c) => ["confirmed", "uncertain", "rejected"].includes(c.state)).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}>
      <div style={{ flex: "none", height: 44, display: "flex", alignItems: "center", gap: 8, padding: "0 16px", borderBottom: `1px solid ${t.border}` }}>
        <h2 style={{ margin: 0, fontSize: 12, fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase", color: t.textSecondary }}>Hypotheses</h2>
        <span style={{ marginLeft: "auto", fontFamily: FONT_MONO, fontSize: 11, color: t.textMuted, whiteSpace: "nowrap", background: t.surface2, border: `1px solid ${t.border}`, padding: "1px 6px", borderRadius: 99 }}>
          {settled}/{cards.length || maxHypotheses} adjudicated
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 10 }}>
        {cards.length === 0 && <div style={{ fontSize: 13, color: t.textMuted }}>Formulating hypotheses…</div>}
        {cards.map((card) => (
          <HypCard key={card.id} card={card} expanded={expanded === card.id} onToggle={onToggle} t={t} />
        ))}
      </div>

      <div style={{ flex: "none", borderTop: `1px solid ${t.border}`, background: t.sidebarBg, padding: "11px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase", color: t.textMuted, marginBottom: 9 }}>
          <span style={{ display: "inline-flex", color: t.textMuted }}>{Ic.shield()}</span> Engine validation
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          {RIGOR.map((r, i) => (
            <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", gap: 1 }}>
              <span style={{ fontFamily: FONT_MONO, fontSize: 14, fontWeight: 500, color: t.textPrimary }}>{r.v}</span>
              <span style={{ fontSize: 9, color: t.textMuted, letterSpacing: "0.03em", textTransform: "uppercase", lineHeight: 1.3 }}>{r.k}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
