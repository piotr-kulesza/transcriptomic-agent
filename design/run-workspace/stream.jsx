/* Center column — live agent stream. The hero view. */

function ResultChip({ result }) {
  const map = {
    info:      { cls: "", icon: null },
    ok:        { cls: "ok", icon: Ic.check },
    confirmed: { cls: "ok", icon: Ic.checkCircle },
    warn:      { cls: "warn", icon: Ic.alert },
    rej:       { cls: "rej", icon: Ic.minus },
    running:   { cls: "running", icon: null },
  };
  const m = map[result.type] || map.info;
  return (
    <span className={"result-chip " + m.cls}>
      {result.type === "running"
        ? <span className="dots"><i/><i/><i/></span>
        : (m.icon ? m.icon() : null)}
      <span className="mono">{result.text}</span>
    </span>
  );
}

function nodeFor(step) {
  if (step.kind === "plan") return { icon: Ic.brain, cls: "" };
  if (step.kind === "gate") {
    const v = step.verdict;
    const cls = v === "confirmed" ? "gate" : v === "uncertain" ? "gate warn" : "gate rej";
    const icon = v === "confirmed" ? Ic.check : v === "uncertain" ? Ic.alert : Ic.minus;
    return { icon, cls };
  }
  return { icon: Ic.beaker, cls: "" };
}

function StreamStep({ step, isLast, running }) {
  const node = nodeFor(step);
  const active = isLast && running && step.result.type === "running";
  const cls = "step" + (isLast ? " is-new" : "") + (active ? " is-active" : " is-done");
  return (
    <div className={cls}>
      <div className={"step-node " + node.cls}>{node.icon()}</div>
      <div className="step-head">
        <span className="tool-chip">{step.tool}{step.hyp ? `·${step.hyp}` : ""}</span>
        <span className="step-phase">{step.phase}</span>
        <span className="step-time mono">{step.t}</span>
      </div>
      <div className="step-rationale" dangerouslySetInnerHTML={{ __html: step.rationale }} />
      <ResultChip result={step.result} />
      {step.meta && (
        <div className="step-meta">
          {step.meta.map((m, i) => (
            <span className="metric" key={i}>{m.k} <span className="v">{m.v}</span></span>
          ))}
        </div>
      )}
    </div>
  );
}

function CoverageDock({ coverage }) {
  const { rows, cols, cells } = coverage;
  return (
    <div className="coverage-dock">
      <div className="coverage-dock-inner">
        <span className="cov-label">Coverage<br/>map</span>
        <div className="cov-grid" style={{ gridTemplateColumns: `repeat(${cols.length}, 14px)` }}>
          {cells.flat().map((c, i) => (
            <div className={"cov-cell " + c} key={i} title={`${rows[Math.floor(i / cols.length)]} × ${cols[i % cols.length]}`} />
          ))}
        </div>
        <div className="cov-legend">
          <span><i style={{ background: "var(--confirmed-soft)", border: "1px solid var(--confirmed-bd)" }} />confirmed</span>
          <span><i style={{ background: "var(--uncertain-soft)", border: "1px solid var(--uncertain-bd)" }} />uncertain</span>
          <span><i style={{ background: "var(--rejected-soft)", border: "1px solid var(--rejected-bd)" }} />rejected</span>
          <span><i style={{ background: "var(--accent-soft)", border: "1px solid var(--accent)" }} />in progress</span>
        </div>
      </div>
    </div>
  );
}

function Stream({ run, visible, running, working, onToggle, onReport }) {
  const scrollRef = React.useRef(null);
  const [atBottom, setAtBottom] = React.useState(true);
  const steps = run.stream.slice(0, visible);

  // auto-scroll to newest when pinned to bottom
  React.useEffect(() => {
    const el = scrollRef.current;
    if (el && atBottom) el.scrollTop = el.scrollHeight;
  }, [visible, working, atBottom]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    setAtBottom(near);
  };
  const jump = () => {
    const el = scrollRef.current;
    if (el) { el.scrollTop = el.scrollHeight; setAtBottom(true); }
  };

  const done = !running && visible >= run.stream.length;

  return (
    <div className="col col-mid">
      <div className="stream-head">
        <div>
          <div className="stream-title">Agent stream</div>
          <div className="stream-sub">Principal Investigator · <span className="mono">{run.model}</span></div>
        </div>
        <div className="stream-controls">
          {running && (
            <span className="throughput">
              <span className="bar"><i style={{ animationDelay: "0s" }}/><i style={{ animationDelay: ".15s" }}/><i style={{ animationDelay: ".3s" }}/><i style={{ animationDelay: ".45s" }}/></span>
              streaming
            </span>
          )}
          <button className="ctrl-btn" onClick={onToggle}>
            {running ? <>{Ic.pause()} Pause</> : <>{Ic.play()} Resume</>}
          </button>
          <button className="ctrl-btn primary" onClick={onReport}>{Ic.doc()} Report</button>
        </div>
      </div>

      <div className="stream-scroll" ref={scrollRef} onScroll={onScroll}>
        <div className="stream-inner">
          {steps.map((s, i) => (
            <StreamStep key={i} step={s} isLast={i === steps.length - 1} running={running} />
          ))}
          {working && running && (
            <div className="working">
              <div className="step-node is-active" style={{ borderColor: "var(--accent)", color: "var(--accent)", boxShadow: "0 0 0 4px var(--accent-soft)" }}>{Ic.brain()}</div>
              <span className="working-text">{working}</span>
              <span className="dots"><i/><i/><i/></span>
            </div>
          )}
          {done && (
            <div className="working">
              <div className="step-node gate">{Ic.check()}</div>
              <span className="working-text">Run complete · 2 confirmed, 1 uncertain, 1 rejected, 1 pending. <a onClick={onReport} style={{ color: "var(--accent)", cursor: "pointer", fontWeight: 600 }}>Open findings report →</a></span>
            </div>
          )}
        </div>
      </div>

      {!atBottom && (
        <button className="jump-latest" onClick={jump}>{Ic.chevDown()} Jump to latest</button>
      )}

      <CoverageDock coverage={run.coverage} />
    </div>
  );
}

window.Stream = Stream;
