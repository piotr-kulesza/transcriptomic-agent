/* ============================================================
   App — top chrome, stream playback engine, hypothesis state
   derivation, Tweaks, and findings-report drawer.
   ============================================================ */

const ACCENTS = [
  { key: "graphite", label: "Graphite", h: 250, c: 0.022, sw: "oklch(0.46 0.022 250)" },
  { key: "slate",    label: "Slate",    h: 256, c: 0.055, sw: "oklch(0.5 0.07 256)" },
  { key: "teal",     label: "Teal",     h: 200, c: 0.06,  sw: "oklch(0.55 0.07 200)" },
  { key: "indigo",   label: "Indigo",   h: 278, c: 0.06,  sw: "oklch(0.5 0.08 278)" },
];

const SPEEDS = { slow: 2600, normal: 1500, fast: 750 };

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "graphite",
  "theme": "light",
  "density": "comfortable",
  "speed": "normal"
}/*EDITMODE-END*/;

// derive live hypothesis verdicts from however much of the stream is visible
function deriveStates(run, visible) {
  const states = {};
  run.hypotheses.forEach((h) => { states[h.id] = "pending"; });
  run.stream.slice(0, visible).forEach((s) => {
    if (!s.hyp) return;
    if (s.kind === "gate") states[s.hyp] = s.verdict;
    else if (states[s.hyp] === "pending") states[s.hyp] = "testing";
  });
  return states;
}

const WORKING_MSG = {
  Ingest: "Reading matrices and harmonizing identifiers",
  Setup: "Inspecting metadata columns",
  Plan: "Reasoning about the hypothesis space",
  Test: "Selecting a statistical test and fitting",
  Replicate: "Re-running across independent cohorts",
  Gate: "Adjudicating against the evidence gate",
};

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const run = window.RUN;

  // playback ---------------------------------------------------
  const STORE = "tde_visible_v1";
  const total = run.stream.length;
  const [visible, setVisible] = React.useState(() => {
    const v = parseInt(localStorage.getItem(STORE) || "1", 10);
    return isNaN(v) ? 1 : Math.min(Math.max(v, 1), total);
  });
  const [running, setRunning] = React.useState(visible < total);
  const [working, setWorking] = React.useState(null);
  const [expanded, setExpanded] = React.useState(null);
  const [report, setReport] = React.useState(false);

  React.useEffect(() => { localStorage.setItem(STORE, String(visible)); }, [visible]);

  // step engine: when running, after a beat show "working", then reveal next step
  React.useEffect(() => {
    if (!running || visible >= total) { setWorking(null); if (visible >= total) setRunning(false); return; }
    const next = run.stream[visible];
    const delay = SPEEDS[t.speed] || SPEEDS.normal;
    const think = setTimeout(() => setWorking(WORKING_MSG[next.phase] || "Working"), delay * 0.18);
    const reveal = setTimeout(() => { setWorking(null); setVisible((v) => v + 1); }, delay);
    return () => { clearTimeout(think); clearTimeout(reveal); };
  }, [running, visible, total, t.speed]);

  const states = deriveStates(run, visible);

  const toggleRun = () => {
    if (visible >= total) {        // completed → restart
      setVisible(1); setRunning(true); return;
    }
    setRunning((r) => !r);
  };
  const toggleCard = (id) => setExpanded((e) => (e === id ? null : id));

  // apply theme + accent on root
  const acc = ACCENTS.find((a) => a.key === t.accent) || ACCENTS[0];
  React.useEffect(() => {
    const r = document.documentElement;
    r.setAttribute("data-theme", t.theme === "dark" ? "dark" : "light");
    r.style.setProperty("--accent-h", acc.h);
    r.style.setProperty("--accent-c", acc.c);
    document.body.style.fontSize = t.density === "compact" ? "12.5px" : "13.5px";
  }, [t.theme, t.accent, t.density]);

  const settled = Object.values(states).filter((s) => ["confirmed", "uncertain", "rejected"].includes(s)).length;

  return (
    <div className="app">
      {/* ---- top chrome ---- */}
      <div className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <svg viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="8.7" r="6.05" fill="currentColor" fillOpacity="0.5" />
              <circle cx="8.4" cy="15" r="6.05" fill="currentColor" fillOpacity="0.5" />
              <circle cx="15.6" cy="15" r="6.05" fill="currentColor" fillOpacity="0.5" />
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-name">Quorum</span>
            <span className="brand-tag">Discovery engine</span>
          </div>
        </div>
        <div className="topbar-sep" />
        <button className="proj-switch">
          {run.project.name}
          <span className="proj-meta">· {run.project.org}</span>
          {Ic.chevDown({ className: "chev" })}
        </button>
        <div className={"run-status" + (running ? " is-running" : "")}>
          <span className="dot" />
          {running ? <>Running · step {visible}/{total}</> : (visible >= total ? <>Completed · {settled} adjudicated</> : <>Paused · step {visible}/{total}</>)}
        </div>

        <div className="spacer" />

        <div className="memory-banner">
          {Ic.history()}
          <span>Remembers <b>14</b> confirmed findings from prior runs</span>
        </div>
        <button className="icon-btn" title="Settings">{Ic.settings()}</button>
        <div className="avatar">RK</div>
      </div>

      {/* ---- three columns ---- */}
      <div className="cols">
        <SetupPanel
          run={run.project ? { ...run.project, datasets: run.datasets, groups: run.groups } : run}
          mode={run.project.mode} setMode={() => {}}
          budget={run.project.budget} setBudget={() => {}}
          model={run.project.model} setModel={() => {}}
          running={running}
          onStart={toggleRun}
        />
        <Stream
          run={{ ...run, model: run.project.model }}
          visible={visible}
          running={running}
          working={working}
          onToggle={toggleRun}
          onReport={() => setReport(true)}
        />
        <HypothesesPanel run={run} states={states} expanded={expanded} onToggle={toggleCard} />
      </div>

      {report && <ReportDrawer run={run} states={states} onClose={() => setReport(false)} />}

      {/* ---- Tweaks ---- */}
      <TweaksPanel>
        <TweakSection label="Accent" />
        <div style={{ display: "flex", gap: 8, padding: "2px 0 8px" }}>
          {ACCENTS.map((a) => (
            <button key={a.key} onClick={() => setTweak("accent", a.key)} title={a.label}
              style={{
                width: 34, height: 34, borderRadius: 9, background: a.sw, cursor: "pointer",
                border: t.accent === a.key ? "2px solid var(--text)" : "2px solid transparent",
                boxShadow: t.accent === a.key ? "0 0 0 2px var(--surface) inset" : "none",
              }} />
          ))}
        </div>
        <TweakSection label="Appearance" />
        <TweakRadio label="Theme" value={t.theme} options={["light", "dark"]} onChange={(v) => setTweak("theme", v)} />
        <TweakRadio label="Density" value={t.density} options={["compact", "comfortable"]} onChange={(v) => setTweak("density", v)} />
        <TweakSection label="Stream" />
        <TweakRadio label="Speed" value={t.speed} options={["slow", "normal", "fast"]} onChange={(v) => setTweak("speed", v)} />
      </TweaksPanel>
    </div>
  );
}

window.App = App;
