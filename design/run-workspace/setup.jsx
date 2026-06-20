/* Left column — Setup panel. Locked-summary mode while a run is in flight. */

function DatasetCard({ ds }) {
  return (
    <div className="ds-card">
      <div className="ds-card-top">
        <div className="ds-icon">{Ic.dna()}</div>
        <div style={{ minWidth: 0 }}>
          <div className="ds-name" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ds.acc}</div>
          <div className="ds-acc" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{ds.name}</div>
        </div>
        {ds.ready && (
          <span className="ds-badge">{Ic.check()} ready</span>
        )}
      </div>
      <div className="ds-stats">
        <div className="ds-stat"><span className="v">{ds.samples}</span><span className="k">samples</span></div>
        <div className="ds-stat"><span className="v">{ds.genes}</span><span className="k">genes</span></div>
        <div className="ds-stat"><span className="v">{ds.platform}</span><span className="k">assay</span></div>
      </div>
    </div>
  );
}

function SetupPanel({ run, mode, setMode, budget, setBudget, model, setModel, running, onStart }) {
  return (
    <div className="col col-left">
      <div className="col-head">
        <h2>Setup</h2>
        {running && <span className="locked-note" style={{ marginLeft: "auto" }}>{Ic.lock()} locked</span>}
      </div>

      <div className="col-body">
        <div className="setup">
          {/* datasets */}
          <div className="field-group">
            <div className="field-label">
              <span>Datasets</span>
              <span className="hint">{run.datasets.length} loaded · {run.datasets.reduce((a, d) => a + d.samples, 0)} samples</span>
            </div>
            {run.datasets.map((ds) => <DatasetCard key={ds.acc} ds={ds} />)}
            {!running && (
              <button className="add-ds">{Ic.plus()} Add expression matrix or DEG table</button>
            )}
          </div>

          {/* group detection */}
          <div className="field-group">
            <div className="field-label"><span>Group column</span></div>
            <div className="detected-col">
              {Ic.search()} {run.groupColumn}
              <span className="auto">auto-detected</span>
            </div>
            <div className="group-map">
              {run.groups.map((g) => (
                <div className="group-row" key={g.name}>
                  <span className="group-swatch" style={{ background: g.color }} />
                  <span className="group-name">{g.name}</span>
                  <span className="group-n">n = {g.n}</span>
                </div>
              ))}
            </div>
          </div>

          {/* run mode */}
          <div className="field-group">
            <div className="field-label"><span>Run mode</span></div>
            <div className="seg" role="group">
              <button aria-pressed={mode === "Reproduce"} onClick={() => !running && setMode("Reproduce")} disabled={running}>
                Reproduce <span className="sub">strict gate</span>
              </button>
              <button aria-pressed={mode === "Explore"} onClick={() => !running && setMode("Explore")} disabled={running}>
                Explore <span className="sub">wider net</span>
              </button>
            </div>
          </div>

          {/* model */}
          <div className="field-group">
            <div className="field-label"><span>PI model</span></div>
            <select className="select" value={model} onChange={(e) => setModel(e.target.value)} disabled={running}>
              <option>Claude Sonnet 4.5</option>
              <option>Claude Opus 4.5</option>
              <option>Claude Haiku 4.5</option>
            </select>
          </div>

          {/* budget */}
          <div className="field-group">
            <div className="field-label"><span>Hypothesis budget</span><span className="hint">max tested</span></div>
            <div className="budget-row">
              <span className="budget-val mono">{budget}</span>
              <div className="budget-track">
                <div className="budget-fill" style={{ width: `${(budget / 24) * 100}%` }} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="setup-footer">
        <button className={"btn-start" + (running ? " is-running" : "")} onClick={onStart}>
          {running ? <>{Ic.pause()} Pause run</> : <>{Ic.play()} Start run</>}
        </button>
        <div className="run-meta-line">
          {running
            ? <>run <b>{run.runId}</b> · started {run.started}</>
            : <>est. <b>~90s</b> · {budget} hypotheses · {run.mode}</>}
        </div>
      </div>
    </div>
  );
}

window.SetupPanel = SetupPanel;
