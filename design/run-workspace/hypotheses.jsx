/* Right column — hypotheses panel + expandable evidence + rigor footer. */

const VERDICT = {
  confirmed: { label: "Confirmed", icon: Ic.checkCircle },
  uncertain: { label: "Uncertain", icon: Ic.alert },
  rejected:  { label: "Rejected", icon: Ic.minus },
  testing:   { label: "Testing", icon: null },
  pending:   { label: "Pending", icon: null },
};

function VerdictBadge({ state }) {
  const v = VERDICT[state];
  return (
    <span className={"verdict " + state}>
      {v.icon ? v.icon() : null}
      {v.label}
    </span>
  );
}

function Direction({ d }) {
  if (d.reg === "flat") {
    return <span className="dir"><span className="grp">{d.grp}</span><span className="reg" style={{ color: "var(--text-faint)" }}>{Ic.minus()} n.s.</span></span>;
  }
  return (
    <span className={"dir " + d.reg}>
      <span className="grp">{d.grp}</span>
      <span className="reg">{d.reg === "up" ? Ic.arrowUp() : Ic.arrowDown()}</span>
    </span>
  );
}

function ReplMini({ replication }) {
  if (!replication.length) return null;
  const ok = replication.filter((r) => r.status === "ok").length;
  return (
    <span className="repl-mini">
      <span className="label">{ok}/{replication.length} cohorts</span>
      <span className="repl-dots">
        {replication.map((r, i) => <i key={i} className={r.status === "ok" ? "on" : r.status === "warn" ? "warn" : ""} />)}
      </span>
    </span>
  );
}

function MethodChip({ mf }) {
  const cls = mf.on === true ? "" : mf.on === "dis" ? "dis" : "off";
  return <span className={"mf-chip " + cls}>{mf.name}</span>;
}

function Evidence({ h }) {
  const heteroFlag = h.heterogeneity && (h.state === "uncertain" || h.state === "rejected");
  return (
    <div className="hyp-evidence">
      {/* direction per group */}
      <div className="ev-block">
        <div className="ev-title">Effect direction</div>
        <div className="dir-arrows" style={{ gap: 14 }}>
          {h.directions.map((d, i) => <Direction key={i} d={d} />)}
          {h.effect && <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-2)" }}>{h.effect}</span>}
        </div>
      </div>

      {/* evidence ladder */}
      <div className="ev-block">
        <div className="ev-title">
          Evidence ladder
          {heteroFlag && <span className="warn-flag">{Ic.alert()} cohorts disagree</span>}
        </div>
        <div className="ladder">
          <div className="ladder-row">
            <span className="ev-k">Method families</span>
            <div className="mf-chips" style={{ marginLeft: "auto" }}>
              {h.methodFamilies.map((mf, i) => <MethodChip key={i} mf={mf} />)}
            </div>
          </div>
          <div className="repl-full">
            {h.replication.map((r, i) => (
              <div className={"repl-ds " + r.status} key={i}>
                <span className="mark">{r.status === "ok" ? Ic.check() : r.status === "warn" ? Ic.alert() : Ic.x()}</span>
                <span className="acc">{r.acc}</span>
                <span className="n">n={r.n}</span>
                <span className="stat">{r.stat}</span>
              </div>
            ))}
          </div>
          <div className="ladder-row">
            <span className="ev-k">Meta-analysis FDR</span>
            <span className="ev-v">{h.metaFDR}</span>
          </div>
          {h.heterogeneity && (
            <div className="ladder-row">
              <span className="ev-k">Heterogeneity</span>
              <span className="ev-v" style={{ color: heteroFlag ? "var(--warning)" : "var(--text)" }}>{h.heterogeneity}</span>
            </div>
          )}
        </div>
      </div>

      {/* translational — demoted */}
      {h.translational && (
        <div className="translational">
          <div className="ev-title">Translational links</div>
          <div className="trans-note">Annotation only — not evidence for the finding.</div>
          <div className="trans-group">
            <span className="trans-k">Drug targets</span>
            <div className="trans-chips">
              {h.translational.targets.map((t) => <a className="trans-chip" key={t}><span className="mono">{t}</span></a>)}
            </div>
          </div>
          {h.translational.drugs && (
            <div className="trans-group">
              <span className="trans-k">Drugs</span>
              <div className="trans-chips">
                {h.translational.drugs.map((d) => <a className="trans-chip" key={d}>{d}</a>)}
              </div>
            </div>
          )}
          {h.translational.trials && (
            <div className="trans-group">
              <span className="trans-k">Clinical trials</span>
              <div className="trans-chips">
                {h.translational.trials.map((t) => <a className="trans-chip" key={t}>{Ic.link()}<span className="mono">{t}</span></a>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function HypCard({ h, expanded, onToggle, settled }) {
  const isTesting = h.state === "testing";
  const isPending = h.state === "pending";
  const canExpand = !isPending && h.replication.length > 0;
  return (
    <div className={"hyp-card " + h.state + (expanded ? " expanded" : "") + (isPending ? " pending" : "")}>
      <div className="hyp-top" onClick={() => canExpand && onToggle(h.id)}>
        <div className="hyp-top-row">
          <span className="hyp-id">{h.id}</span>
          <span className="hyp-statement">{h.statement}</span>
          <VerdictBadge state={h.state} />
        </div>

        {isTesting ? (
          <div>
            <div className="testing-bar"><i /></div>
          </div>
        ) : isPending ? null : (
          <div className="hyp-summary">
            <div className="dir-arrows">
              {h.directions.map((d, i) => <Direction key={i} d={d} />)}
            </div>
            <ReplMini replication={h.replication} />
          </div>
        )}
      </div>

      {expanded && canExpand && <Evidence h={h} />}

      {canExpand && (
        <div className="hyp-expand-cue" onClick={() => onToggle(h.id)} style={{ cursor: "pointer" }}>
          <span className={"chev-rotate" + (expanded ? " open" : "")} style={{ display: "inline-flex" }}>{Ic.chevDown()}</span>
          {expanded ? "Hide evidence" : "Show evidence"}
        </div>
      )}
    </div>
  );
}

function HypothesesPanel({ run, states, expanded, onToggle }) {
  // states: live map of id -> current state (may differ from data as run progresses)
  const hyps = run.hypotheses.map((h) => ({ ...h, state: states[h.id] || h.state }));
  const settled = hyps.filter((h) => ["confirmed", "uncertain", "rejected"].includes(h.state)).length;

  return (
    <div className="col col-right">
      <div className="col-head">
        <h2>Hypotheses</h2>
        <span className="count">{settled}/{run.hypotheses.length} adjudicated</span>
      </div>

      <div className="col-body">
        <div className="hyp-list">
          {hyps.map((h) => (
            <HypCard key={h.id} h={h} expanded={expanded === h.id} onToggle={onToggle} settled={settled} />
          ))}
        </div>
      </div>

      <div className="rigor">
        <div className="rigor-head">{Ic.shield()} Engine validation</div>
        <div className="rigor-stats">
          {run.rigor.map((r, i) => (
            <div className="rigor-stat" key={i}>
              <span className="v">{r.v}{r.suffix ? <small>{r.suffix}</small> : null}</span>
              <span className="k">{r.k}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

window.HypothesesPanel = HypothesesPanel;
