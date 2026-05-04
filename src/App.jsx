import { useState, useRef, useEffect, useCallback } from "react";
import { flushSync } from "react-dom";
import DatasetSlot from "./components/DatasetSlot";
import LogEntry from "./components/LogEntry";
import { setGroupMappings, uploadDegDataset } from "./api";

const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  html,body,#root{background:#0d1117;width:100%;height:100%;overflow:hidden}
  ::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:#161b22}::-webkit-scrollbar-thumb{background:#6C5CE733;border-radius:3px}
  ::-webkit-scrollbar-thumb:hover{background:#6C5CE755}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
  @keyframes si{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:translateY(0)}}
  @keyframes dots{0%,100%{content:''}33%{content:'.'}66%{content:'..'}99%{content:'...'}}
  .thinking-indicator::after{content:'';animation:dots 1.2s steps(1) infinite}
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  .spinner{width:16px;height:16px;border:2px solid #1e1a35;border-top-color:#6C5CE7;border-radius:50%;animation:spin 0.8s linear infinite}
  .ent{animation:si .15s ease}
  .blink{animation:pulse 1.2s infinite}
  .btn{background:#161b22;border:1px solid #30363d;color:#c9d1d9;font-family:inherit;font-size:13px;padding:7px 14px;cursor:pointer;transition:background .15s,border-color .15s;width:100%;border-radius:6px;font-weight:500}
  .btn:hover{background:#21262d;border-color:#8b949e}.btn:disabled{opacity:.4;cursor:not-allowed}
  .bsm{padding:4px 10px;width:auto;font-size:12px}.bdng{border-color:#6e2020;color:#f87171;background:transparent}.bdng:hover{background:#2d0c0c;border-color:#f87171}
  .slot{border:1px solid #21262d;padding:12px;margin-bottom:8px;background:#161b22;border-radius:6px;transition:border-color .15s}
  .slot.ok{border-color:#6C5CE733}
  .uz{border:1px dashed #30363d;padding:10px;text-align:center;cursor:pointer;transition:all .15s;background:#0d1117;display:block;margin-bottom:6px;font-size:13px;color:#64748b;border-radius:4px}
  .uz:hover{border-color:#6C5CE788;background:#1a1535;color:#b8b1f7}
  .uz.ok{border-color:#6C5CE744;background:#130f2a;color:#6C5CE7}
  .tag{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}
  input[type=text],select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;font-size:13px;font-family:inherit;width:100%;border-radius:4px;transition:border-color .15s}
  input[type=text]:focus,select:focus{outline:none;border-color:#6C5CE766}
  input[type=number]{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;padding:6px 10px;font-size:13px;font-family:inherit;width:100%;border-radius:4px;transition:border-color .15s}
  input[type=number]:focus{outline:none;border-color:#6C5CE766}
  .sec{font-size:10px;color:#6C5CE7;letter-spacing:1px;margin:16px 0 8px;font-weight:700;text-transform:uppercase;display:flex;align-items:center;gap:8px}
  .sec::after{content:'';flex:1;height:1px;background:#21262d}
`;

const VERDICT_STYLE = {
  confirmed: { color: "#4ade80", icon: "✓" },
  rejected:  { color: "#f87171", icon: "✗" },
  uncertain: { color: "#fbbf24", icon: "?" },
  pending:   { color: "#94a3b8", icon: "○" },
};

export default function App() {
  const [slots, setSlots] = useState([
    { id: 0, exprFile: null, metaFile: null, name: "Dataset 1" },
    { id: 1, exprFile: null, metaFile: null, name: "Dataset 2" },
  ]);
  const [loaded,     setLoaded]     = useState([]);
  const [groupMap,   setGroupMap]   = useState({});
  const [phase,      setPhase]      = useState("upload");
  const [log,        setLog]        = useState([]);
  const [hypotheses, setHypotheses] = useState([]);
  const [step,          setStep]          = useState(0);
  const [freeSteps,     setFreeSteps]     = useState(6);
  const [agentMode,     setAgentMode]     = useState("reproduce");
  const [currentStatus, setCurrentStatus] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [mappingGroups, setMappingGroups] = useState([]);
  const [mappingsOpen, setMappingsOpen] = useState(false);
  const [degDatasets,  setDegDatasets]  = useState([]);
  const [degFile,      setDegFile]      = useState(null);
  const [degGroupA,    setDegGroupA]    = useState("");
  const [degGroupB,    setDegGroupB]    = useState("");
  const [degUploading, setDegUploading] = useState(false);
  const [degStatus,    setDegStatus]    = useState("");
  const logEnd   = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => { logEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [log]);
  const addLog = useCallback(e => setLog(prev => [...prev, { ...e, id: Date.now() + Math.random() }]), []);

  const addSlot    = () => setSlots(p => [...p, { id: Date.now(), exprFile: null, metaFile: null, name: `Dataset ${p.length + 1}` }]);
  const removeSlot = id => setSlots(p => p.filter(s => s.id !== id));
  const updSlot    = (id, k, v) => setSlots(p => p.map(s => s.id === id ? { ...s, [k]: v } : s));

  const postMappings = useCallback((groups) => {
    const mappings = {};
    for (const { canonical, aliases } of groups) {
      if (canonical.trim() && aliases.size > 0) mappings[canonical.trim()] = [...aliases];
    }
    setGroupMappings(mappings).catch(() => {});
  }, []);

  const addMappingGroup = () => {
    const next = [...mappingGroups, { canonical: "", aliases: new Set() }];
    setMappingGroups(next);
    postMappings(next);
  };

  const updateMappingCanonical = (idx, value) => {
    const next = mappingGroups.map((mg, i) => i === idx ? { ...mg, canonical: value } : mg);
    setMappingGroups(next);
    postMappings(next);
  };

  const toggleAlias = (idx, alias, checked) => {
    const next = mappingGroups.map((mg, i) => {
      if (i !== idx) return mg;
      const aliases = new Set(mg.aliases);
      if (checked) aliases.add(alias); else aliases.delete(alias);
      return { ...mg, aliases };
    });
    setMappingGroups(next);
    postMappings(next);
  };

  const removeMappingGroup = (idx) => {
    const next = mappingGroups.filter((_, i) => i !== idx);
    setMappingGroups(next);
    postMappings(next);
  };

  const loadAll = async () => {
    const newLoaded = [];
    for (const slot of slots) {
      if (!slot.exprFile || !slot.metaFile) continue;
      const fd = new FormData();
      fd.append("expr_file", slot.exprFile);
      fd.append("meta_file", slot.metaFile);
      fd.append("name", slot.name);
      const existingId = loaded.find(d => d.name === slot.name)?.id;
      if (existingId) fd.append("dataset_id", existingId);
      try {
        const res = await fetch("/api/datasets", { method: "POST", body: fd });
        if (!res.ok) { addLog({ type: "error", text: `Upload ${slot.name}: ${res.statusText}` }); continue; }
        newLoaded.push(await res.json());
      } catch (e) {
        addLog({ type: "error", text: `Upload ${slot.name}: ${e.message}` });
      }
    }
    setLoaded(newLoaded);
    const m = {};
    newLoaded.forEach(d => { m[d.id] = d.group_col; });
    setGroupMap(m);
    setMappingsOpen(newLoaded.length >= 2);
  };

  const uploadDeg = async () => {
    if (!degFile || !degGroupA.trim() || !degGroupB.trim()) return;
    const degName = `DEG ${degDatasets.length + 1}`;
    setDegUploading(true);
    setDegStatus("");
    try {
      const res = await uploadDegDataset(degFile, degName, degGroupA.trim(), degGroupB.trim());
      const errMsg = res.error || res.detail;
      if (errMsg) {
        setDegStatus(`Error: ${errMsg}`);
        return;
      }
      setDegDatasets(prev => [...prev.filter(d => d.name !== res.name), res]);
      setDegStatus(`Uploaded: ${res.n_genes} genes (${res.groupA} vs ${res.groupB})`);
      setDegFile(null);
      setDegGroupA("");
      setDegGroupB("");
    } catch (e) {
      setDegStatus(`Error: ${e.message}`);
    } finally {
      setDegUploading(false);
    }
  };

  const runAgent = async () => {
    if (!loaded.length && !degDatasets.length) return;
    setPhase("running"); setLog([]); setStep(0); setHypotheses([]); setCurrentStatus("Running pre-analysis..."); setStreamingText("");

    const controller = new AbortController();
    abortRef.current = controller;
    let currentStep = 0;

    try {
      const res = await fetch("http://localhost:8000/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_ids: loaded.map(d => d.id), group_cols: groupMap, free_steps: freeSteps, mode: agentMode }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        addLog({ type: "error", text: `Start: ${err.detail || res.statusText}` });
        setPhase("done");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const entry = JSON.parse(line.slice(6));
            if (entry.type === "stream_end") { reader.cancel(); break; }
            if (entry.type === "thinking")        { setStep(++currentStep); setCurrentStatus(entry.text); setStreamingText(""); addLog(entry); continue; }
            if (entry.type === "thought_stream")  { flushSync(() => setStreamingText(prev => prev + entry.delta)); continue; }
            if (entry.type === "thought")         { flushSync(() => setStreamingText("")); }
            if (entry.type === "hypothesis_propose") setHypotheses(prev => [...prev, entry.hypothesis]);
            if (entry.type === "hypothesis_eval")    setHypotheses(prev => prev.map(h => h.id === entry.hypothesis.id ? entry.hypothesis : h));
            addLog(entry);
            await new Promise(r => setTimeout(r, 80));
          } catch { /* ignore malformed SSE lines */ }
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") addLog({ type: "error", text: `Stream: ${e.message}` });
    }
    setCurrentStatus("");
    setStreamingText("");
    setPhase("done");
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0d1117", fontFamily: "'Inter',system-ui,-apple-system,sans-serif", color: "#c9d1d9" }}>
      <style>{STYLES}</style>

      {/* Header */}
      <div style={{ borderBottom: "1px solid #21262d", padding: "11px 20px", display: "flex", alignItems: "center", gap: 12, background: "#161b22" }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: phase === "running" ? "#6C5CE7" : "#21262d", boxShadow: phase === "running" ? "0 0 8px #6C5CE788" : "none", flexShrink: 0, transition: "all .3s" }} className={phase === "running" ? "blink" : ""} />
        <span style={{ fontSize: 14, fontWeight: 600, color: "#6C5CE7", letterSpacing: 0.3 }}>Transcriptomic Agent</span>
        <span style={{ fontSize: 12, color: "#334155", paddingLeft: 4 }}>Multi-dataset · Cross-cohort</span>
        {phase === "running" && !currentStatus && (
          <span style={{ marginLeft: "auto", fontSize: 12, color: "#6C5CE7", opacity: 0.7 }}>Step {Math.min(step, freeSteps)}/{freeSteps}</span>
        )}
      </div>

      <div style={{ display: "flex", height: "calc(100vh - 46px)" }}>

        {/* LEFT PANEL */}
        <div style={{ width: 284, borderRight: "1px solid #21262d", padding: "12px", overflowY: "auto", flexShrink: 0, background: "#0d1117" }}>
          <div className="sec">Datasets</div>

          {slots.map(slot => (
            <DatasetSlot key={slot.id} slot={slot} canRemove={slots.length > 1}
              onUpdate={(k, v) => updSlot(slot.id, k, v)} onRemove={() => removeSlot(slot.id)} />
          ))}

          <button className="btn bsm" style={{ marginBottom: 6, width: "100%" }} onClick={addSlot}>+ Add dataset</button>
          <button className="btn" style={{ marginBottom: 10, borderColor: "#6C5CE733", color: "#6C5CE7" }} onClick={loadAll} disabled={!slots.some(s => s.exprFile && s.metaFile)}>
            Load data
          </button>

          {/* DEG TABLE UPLOAD */}
          <div className="sec">DEG Datasets</div>
          <div style={{ marginBottom: 10 }}>
            <label className="uz" style={{ marginBottom: 6, fontSize: 13 }}>
              {degFile ? degFile.name : "Upload DEG table (.csv)"}
              <input type="file" accept=".csv" style={{ display: "none" }} onChange={e => setDegFile(e.target.files[0] || null)} />
            </label>
            <input type="text" value={degGroupA} onChange={e => setDegGroupA(e.target.value)}
              placeholder="Group A" style={{ marginBottom: 5 }} />
            <input type="text" value={degGroupB} onChange={e => setDegGroupB(e.target.value)}
              placeholder="Group B" style={{ marginBottom: 6 }} />
            <button className="btn bsm" style={{ width: "100%", marginBottom: 4 }}
              onClick={uploadDeg}
              disabled={!degFile || !degGroupA.trim() || !degGroupB.trim() || degUploading}>
              {degUploading ? "Uploading..." : "Upload DEG table"}
            </button>
            {degStatus && (
              <div style={{ fontSize: 12, marginBottom: 8, padding: "5px 8px", borderRadius: 4,
                color: degStatus.startsWith("Error") ? "#f87171" : "#4ade80",
                background: degStatus.startsWith("Error") ? "#2d0c0c" : "#0a1f12",
                border: `1px solid ${degStatus.startsWith("Error") ? "#6e202044" : "#4ade8033"}` }}>
                {degStatus}
              </div>
            )}
            {degDatasets.map(d => (
              <div key={d.name} className="slot ok" style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontSize: 13, color: "#6C5CE7", fontWeight: 500 }}>{d.name}</span>
                  <button className="btn bsm bdng" style={{ padding: "2px 8px", fontSize: 11 }}
                    onClick={() => setDegDatasets(prev => prev.filter(x => x.name !== d.name))}>✕</button>
                </div>
                {(d.comparisons || []).map((c, i) => (
                  <div key={i} style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.8, fontFamily: "'JetBrains Mono',monospace" }}>
                    {c.groupA} <span style={{ color: "#334155" }}>vs</span> {c.groupB}
                    <span style={{ color: "#64748b", marginLeft: 6 }}>{c.n_genes} genes</span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          {(loaded.length > 0 || degDatasets.length > 0) && <>
            <div className="sec">Group Columns</div>
            {loaded.map(ds => (
              <div key={ds.id} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 13, color: "#94a3b8", marginBottom: 5, fontWeight: 500 }}>{ds.name}</div>
                <select value={groupMap[ds.id] || ds.group_col} onChange={async e => {
                    const newCol = e.target.value;
                    setGroupMap(prev => ({ ...prev, [ds.id]: newCol }));
                    try {
                      const r = await fetch(`/api/datasets/${ds.id}/group_col`, {
                        method: "PATCH",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ group_col: newCol }),
                      });
                      if (r.ok) {
                        const data = await r.json();
                        setLoaded(prev => prev.map(d => d.id === ds.id ? { ...d, group_col: newCol, groups: data.groups } : d));
                      }
                    } catch {}
                  }}>
                  {(ds.group_col_candidates || (ds.group_cols || []).map(c => ({ col: c, unique_values: [] }))).map(cand => (
                    <option key={cand.col} value={cand.col}>
                      {cand.col}: {cand.unique_values.slice(0, 3).join(", ")}
                    </option>
                  ))}
                </select>
                <div style={{ fontSize: 12, color: "#64748b", marginTop: 5, lineHeight: 1.9, fontFamily: "'JetBrains Mono',monospace" }}>
                  {ds.groups.map(g => <div key={g} style={{ paddingLeft: 2 }}>{g}</div>)}
                </div>
                <div style={{ fontSize: 12, color: "#334155", marginTop: 4 }}>{ds.gene_count} genes · {ds.sample_count} samples</div>
              </div>
            ))}

            {/* GROUP MAPPINGS */}
            {(() => {
              const allGroups = [...new Set(loaded.flatMap(ds => ds.groups))];
              return (
                <>
                  <div className="sec" style={{ cursor: "pointer", userSelect: "none" }}
                    onClick={() => setMappingsOpen(p => !p)}>
                    <span>Group Mappings</span>
                    <span style={{ color: "#6C5CE7", fontSize: 12, marginLeft: -4 }}>{mappingsOpen ? "▾" : "▸"}</span>
                  </div>
                  {mappingsOpen && (
                    <div style={{ marginBottom: 10 }}>
                      {mappingGroups.map((mg, idx) => (
                        <div key={idx} style={{ marginBottom: 8, padding: "8px 10px", border: "1px solid #21262d", background: "#161b22", borderRadius: 6 }}>
                          <div style={{ display: "flex", gap: 5, marginBottom: 6 }}>
                            <input type="text" value={mg.canonical} placeholder="Canonical name"
                              onChange={e => updateMappingCanonical(idx, e.target.value)}
                              style={{ flex: 1 }} />
                            <button className="btn bsm bdng" onClick={() => removeMappingGroup(idx)}>✕</button>
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 5 }}>
                            {allGroups.map(g => (
                              <label key={g} style={{ fontSize: 12, color: mg.aliases.has(g) ? "#6C5CE7" : "#64748b", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                                <input type="checkbox" checked={mg.aliases.has(g)}
                                  onChange={e => toggleAlias(idx, g, e.target.checked)} />
                                {g}
                              </label>
                            ))}
                          </div>
                          {mg.canonical && (
                            <div style={{ fontSize: 11, color: "#64748b", lineHeight: 1.6, fontFamily: "'JetBrains Mono',monospace" }}>
                              "{mg.canonical}" ← {allGroups.map(g => (
                                <span key={g} style={{ marginRight: 6, color: mg.aliases.has(g) ? "#6C5CE7" : "#334155" }}>
                                  {g} {mg.aliases.has(g) ? "✓" : "✗"}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                      <button className="btn bsm" style={{ width: "100%", marginBottom: 6 }} onClick={addMappingGroup}>
                        + Add mapping group
                      </button>
                    </div>
                  )}
                </>
              );
            })()}

            <div className="sec">Mode</div>
            <div style={{ display: "flex", background: "#0d1117", borderRadius: 6, border: "1px solid #21262d", padding: 3, marginBottom: 12, gap: 2 }}>
              {[
                { key: "reproduce", label: "Reproduce", sub: "deterministic" },
                { key: "explore",   label: "Explore",   sub: "creative" },
              ].map(({ key, label, sub }) => (
                <button key={key} onClick={() => setAgentMode(key)}
                  style={{
                    flex: 1,
                    background: agentMode === key ? "#1a1535" : "transparent",
                    border: agentMode === key ? "1px solid #6C5CE733" : "1px solid transparent",
                    color: agentMode === key ? "#6C5CE7" : "#64748b",
                    padding: "5px 8px", cursor: "pointer", borderRadius: 4, transition: "all .15s",
                    fontFamily: "inherit", fontSize: 12, fontWeight: agentMode === key ? 500 : 400,
                  }}>
                  {label}
                  <div style={{ fontSize: 10, color: agentMode === key ? "#b8b1f7" : "#334155", marginTop: 1 }}>{sub}</div>
                </button>
              ))}
            </div>

            <div className="sec">Steps</div>
            <input type="number" value={freeSteps} min={1} max={30}
              onChange={e => setFreeSteps(parseInt(e.target.value))}
              style={{ marginBottom: 12 }} />

            <button
              style={{
                width: "100%", padding: "9px 14px", border: "1px solid transparent", borderRadius: 6,
                background: phase === "running" ? "#161b22" : "#2d1f6e",
                borderColor: phase === "running" ? "#30363d" : "#6C5CE744",
                color: phase === "running" ? "#94a3b8" : "#6C5CE7",
                fontFamily: "inherit", fontSize: 13, fontWeight: 600,
                cursor: "pointer", transition: "all .15s",
              }}
              onMouseEnter={e => { if (phase !== "running") { e.target.style.background = "#251a5a"; e.target.style.borderColor = "#6C5CE788"; } }}
              onMouseLeave={e => { if (phase !== "running") { e.target.style.background = "#2d1f6e"; e.target.style.borderColor = "#6C5CE744"; } }}
              onClick={phase === "running" ? () => abortRef.current?.abort() : runAgent}>
              {phase === "running" ? "Stop" : "Start Agent"}
            </button>
          </>}
        </div>

        {/* LOG PANEL */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* sticky status bar */}
          {currentStatus && (
            <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 10, padding: "8px 24px", borderBottom: "1px solid #21262d", background: "#161b22" }}>
              <div className="spinner" />
              <span className="thinking-indicator" style={{ fontSize: 13, color: "#6C5CE7" }}>{currentStatus}</span>
              {step > 0 && <span style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}>Step {Math.min(step, freeSteps)}/{freeSteps}</span>}
            </div>
          )}

          <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
            {log.length === 0 && !currentStatus && (
              <div style={{ textAlign: "center", marginTop: 100 }}>
                <div style={{ fontSize: 28, opacity: .2, marginBottom: 14, color: "#6C5CE7" }}>◈</div>
                <div style={{ fontSize: 15, color: "#4b5563", fontWeight: 500 }}>Load datasets and start the agent</div>
                <div style={{ fontSize: 13, color: "#374151", marginTop: 8 }}>Backend: <code style={{ color: "#64748b", fontFamily: "'JetBrains Mono',monospace", fontSize: 12 }}>uvicorn backend.main:app --reload</code></div>
              </div>
            )}
            {log.length === 0 && currentStatus && (
              <div style={{ textAlign: "center", marginTop: 120 }}>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 24 }}>
                  <div style={{ width: 36, height: 36, border: "2px solid #1e1a35", borderTopColor: "#6C5CE7", borderRadius: "50%", animation: "spin 0.8s linear infinite" }} />
                </div>
                <div style={{ fontSize: 14, color: "#6C5CE7", opacity: 0.8 }}>{currentStatus}</div>
                <div style={{ fontSize: 12, color: "#374151", marginTop: 8 }}>This may take a few seconds...</div>
              </div>
            )}
            {log.map(e => <LogEntry key={e.id} entry={e} />)}
            {streamingText && (
              <div className="ent" style={{ marginBottom: 12, borderLeft: "2px solid #6C5CE744", paddingLeft: 14 }}>
                <div style={{ fontSize: 14, color: "#c9d1d9", lineHeight: 1.7 }}>
                  {streamingText}<span className="blink" style={{ color: "#6C5CE7" }}>▋</span>
                </div>
              </div>
            )}
            <div ref={logEnd} />
          </div>
        </div>

        {/* HYPOTHESIS PANEL */}
        {(phase === "running" || hypotheses.length > 0) && (
          <div style={{ width: 272, borderLeft: "1px solid #21262d", padding: "12px", overflowY: "auto", flexShrink: 0, background: "#0d1117" }}>
            <div className="sec">Hypotheses</div>
            {hypotheses.length === 0 && <div style={{ fontSize: 13, color: "#334155" }}>Formulating hypotheses...</div>}
            {hypotheses.map(h => {
              const vs = VERDICT_STYLE[h.status] || VERDICT_STYLE.pending;
              return (
                <div key={h.id} style={{ marginBottom: 10, padding: "10px 12px", background: "#161b22", border: "1px solid #21262d", borderRadius: 6, borderLeft: `3px solid ${vs.color}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <span className="tag" style={{ background: `${vs.color}18`, color: vs.color, fontSize: 11 }}>{h.id}</span>
                    <span style={{ fontSize: 12, color: vs.color, opacity: 0.9 }}>{vs.icon} {h.status}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "#c9d1d9", lineHeight: 1.6 }}>{h.text}</div>
                  {h.evidence.length > 0 && (
                    <div style={{ marginTop: 8, borderTop: "1px solid #21262d", paddingTop: 8 }}>
                      {h.evidence.map((ev, i) => (
                        <div key={i} style={{ fontSize: 12, color: "#64748b", lineHeight: 1.6, marginBottom: 4 }}>
                          <span style={{ color: "#8b949e" }}>step {ev.step} [{ev.action}]</span> {ev.reasoning}
                          {ev.key_stats && Object.keys(ev.key_stats).length > 0 && (
                            <div style={{ marginTop: 2, paddingLeft: 8, borderLeft: "2px solid #21262d", fontFamily: "'JetBrains Mono',monospace" }}>
                              {Object.entries(ev.key_stats).map(([gene, s]) => (
                                <span key={gene} style={{ display: "inline-block", marginRight: 10, color: "#64748b", fontSize: 11 }}>
                                  <b style={{ color: "#94a3b8" }}>{gene}</b>{": "}
                                  {Object.entries(s).filter(([, v]) => v != null).map(([k, v]) =>
                                    `${k}=${typeof v === "number" ? (Math.abs(v) < 0.001 ? v.toExponential(2) : v.toPrecision(3)) : Array.isArray(v) ? v.join(",") : v}`
                                  ).join("  ")}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
