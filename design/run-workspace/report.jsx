/* Findings report drawer — clean, citable results document (slide-over). */

function ReportDrawer({ run, states, onClose }) {
  const hyps = run.hypotheses.map((h) => ({ ...h, state: states[h.id] || h.state }));
  const confirmed = hyps.filter((h) => h.state === "confirmed");
  const uncertain = hyps.filter((h) => h.state === "uncertain");
  const rejected = hyps.filter((h) => h.state === "rejected");
  const incomplete = hyps.some((h) => ["testing", "pending"].includes(h.state));

  return (
    <div className="report-scrim" onClick={onClose}>
      <div className="report" onClick={(e) => e.stopPropagation()}>
        <div className="report-bar">
          <div className="report-bar-l">
            {Ic.doc()} <span>Findings report</span>
            {incomplete && <span className="incomplete-tag">{Ic.alert()} Incomplete · resumable</span>}
          </div>
          <div className="report-bar-r">
            <button className="ctrl-btn">{Ic.doc()} Export</button>
            <button className="icon-btn" onClick={onClose}>{Ic.x()}</button>
          </div>
        </div>

        <div className="report-body">
          <div className="report-doc">
            <header className="rep-head">
              <div className="rep-eyebrow mono">{run.project.runId} · {run.project.mode}</div>
              <h1>Determinants of immune-checkpoint-blockade response in cutaneous melanoma</h1>
              <div className="rep-byline">
                Autonomous PI agent · {run.project.model} · {run.datasets.length} cohorts ·{" "}
                {run.datasets.reduce((a, d) => a + d.samples, 0)} samples · group column{" "}
                <span className="mono">{run.project.groupColumn}</span>
              </div>
            </header>

            {/* per-comparison characterization */}
            <section className="rep-sec">
              <h2>Characterization · Responder vs Non-responder</h2>
              <p>
                Across all three cohorts, response is consistently associated with a coordinated
                cytotoxic-immune program: elevated interferon-γ signaling and cytolytic effector
                activity in responders, against a backdrop of comparable tumor purity. Two candidate
                resistance axes — Wnt/β-catenin exclusion and an <span className="gene">MITF</span>-high
                differentiation state — did not survive cross-cohort replication at the same standard.
              </p>
            </section>

            {/* confirmed axes */}
            <section className="rep-sec">
              <h2>Confirmed axes <span className="rep-count ok">{confirmed.length}</span></h2>
              {confirmed.map((h) => (
                <div className="rep-finding" key={h.id}>
                  <div className="rep-finding-top">
                    <span className="hyp-id">{h.id}</span>
                    <span className="rep-finding-stmt">{h.statement}</span>
                    <span className="verdict confirmed">{Ic.checkCircle()} Confirmed</span>
                  </div>
                  <div className="rep-finding-ev">
                    <span>method families <b className="mono">{h.methodFamilies.filter((m) => m.on === true).length}/4</b></span>
                    <span>replicated <b className="mono">{h.replication.filter((r) => r.status === "ok").length}/{h.replication.length}</b></span>
                    <span>meta-FDR <b className="mono">{h.metaFDR}</b></span>
                    <span>effect <b className="mono">{h.effect}</b></span>
                  </div>
                </div>
              ))}
            </section>

            {/* uncertain / rejected, compact */}
            <section className="rep-sec rep-two">
              <div>
                <h2>Held uncertain <span className="rep-count warn">{uncertain.length}</span></h2>
                {uncertain.map((h) => (
                  <div className="rep-mini" key={h.id}>
                    <span className="hyp-id">{h.id}</span> {h.statement}
                    <div className="rep-mini-note">{Ic.alert()} {h.heterogeneity} between cohorts</div>
                  </div>
                ))}
              </div>
              <div>
                <h2>Rejected <span className="rep-count rej">{rejected.length}</span></h2>
                {rejected.map((h) => (
                  <div className="rep-mini" key={h.id}>
                    <span className="hyp-id">{h.id}</span> {h.statement}
                    <div className="rep-mini-note">fails replication · {h.replication.filter((r) => r.status === "ok").length}/{h.replication.length} cohorts</div>
                  </div>
                ))}
              </div>
            </section>

            {/* translational */}
            <section className="rep-sec">
              <h2>Translational annotation</h2>
              <p className="rep-demote">Linked for orientation only. These associations are not part of the evidence that confirmed the findings above.</p>
              <div className="rep-trans">
                {confirmed.filter((h) => h.translational).map((h) => (
                  <div className="rep-trans-row" key={h.id}>
                    <span className="hyp-id">{h.id}</span>
                    <div className="trans-chips">
                      {h.translational.targets.map((x) => <span className="trans-chip" key={x}><span className="mono">{x}</span></span>)}
                      {h.translational.trials.map((x) => <span className="trans-chip" key={x}>{Ic.link()}<span className="mono">{x}</span></span>)}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* provenance */}
            <section className="rep-sec">
              <h2>Provenance</h2>
              <div className="rep-prov">
                {run.datasets.map((d) => (
                  <div className="rep-prov-row" key={d.acc}>
                    <span className="mono">{d.acc}</span>
                    <span>{d.name}</span>
                    <span className="rep-prov-n mono">{d.samples} samples · {d.genes} genes · {d.platform}</span>
                  </div>
                ))}
                <div className="rep-prov-row">
                  <span className="mono">methods</span>
                  <span>DESeq2 · fgsea · ssGSEA · random-effects meta-analysis · BH-FDR &lt; 0.05 · evidence gate ≥ 3 cohorts</span>
                </div>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}

window.ReportDrawer = ReportDrawer;
