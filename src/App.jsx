import { useState, useRef, useEffect, useCallback } from "react";
import { flushSync } from "react-dom";
import DatasetSlot from "./components/DatasetSlot";
import LogEntry from "./components/LogEntry";
import { setGroupMappings, uploadDegDataset } from "./api";

const THEMES = {
  dark: {
    appBg:         "#010816",
    sidebarBg:     "#06101c",
    cardBg:        "#0b1524",
    elevatedBg:    "#0f1b2d",
    accent:        "#5538e8",
    accentHover:   "#6b52f0",
    textPrimary:   "#e2e8f0",
    textSecondary: "#94a3b8",
    textMuted:     "#4e5d7a",
    border:        "#152030",
    startHoverBg:  "#1e1b4b",
    dangerHoverBg: "#2d0c0c",
    codeText:      "#c4b5fd",
  },
  light: {
    appBg:         "#f8fafc",
    sidebarBg:     "#f1f5f9",
    cardBg:        "#ffffff",
    elevatedBg:    "#f8fafc",
    accent:        "#5538e8",
    accentHover:   "#4527d0",
    textPrimary:   "#0f172a",
    textSecondary: "#334155",
    textMuted:     "#64748b",
    border:        "#e2e8f0",
    startHoverBg:  "#eef2ff",
    dangerHoverBg: "#fef2f2",
    codeText:      "#4f46e5",
  },
};

function makeStyles(t) {
  return `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
  *{box-sizing:border-box;margin:0;padding:0}
  html,body,#root{background:${t.appBg};width:100%;height:100%;overflow:hidden}
  ::-webkit-scrollbar{width:5px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:${t.border};border-radius:3px}
  ::-webkit-scrollbar-thumb:hover{background:${t.accent}55}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
  @keyframes si{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:translateY(0)}}
  @keyframes dots{0%,100%{content:''}33%{content:'.'}66%{content:'..'}99%{content:'...'}}
  .thinking-indicator::after{content:'';animation:dots 1.2s steps(1) infinite}
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  .spinner{width:14px;height:14px;border:2px solid ${t.border};border-top-color:${t.accent};border-radius:50%;animation:spin 0.75s linear infinite;flex-shrink:0}
  .ent{animation:si .18s ease}
  .blink{animation:pulse 1.4s infinite}
  .btn{
    background:${t.cardBg};border:1px solid ${t.border};color:${t.textPrimary};
    font-family:inherit;font-size:13px;padding:7px 14px;cursor:pointer;
    transition:background .15s,border-color .15s,color .15s;
    width:100%;border-radius:6px;font-weight:500;
  }
  .btn:hover{background:${t.elevatedBg};border-color:${t.textMuted}40}
  .btn:disabled{opacity:.35;cursor:not-allowed}
  .bsm{padding:4px 10px;width:auto;font-size:12px}
  .bdng{border-color:#be2a2a55;color:#f87171;background:transparent}
  .bdng:hover{background:${t.dangerHoverBg};border-color:#f87171}
  .slot{
    border:1px solid ${t.border};padding:12px;margin-bottom:8px;
    background:${t.cardBg};border-radius:8px;transition:border-color .2s;
  }
  .slot.ok{border-color:${t.accent}30}
  .uz{
    border:1px dashed ${t.border};padding:9px 12px;text-align:center;cursor:pointer;
    transition:all .15s;background:${t.appBg};display:flex;align-items:center;
    justify-content:center;gap:6px;margin-bottom:6px;font-size:12px;
    color:${t.textMuted};border-radius:6px;
  }
  .uz:hover{border-color:${t.accent}66;background:${t.elevatedBg};color:${t.accent}}
  .uz.ok{border-color:${t.accent}35;color:${t.accent}}
  .tag{display:inline-block;padding:2px 7px;border-radius:4px;font-size:11px;font-weight:600}
  input[type=text],input[type=number],select{
    background:${t.appBg};border:1px solid ${t.border};color:${t.textPrimary};
    padding:7px 10px;font-size:13px;font-family:inherit;width:100%;
    border-radius:6px;transition:border-color .15s;
  }
  input[type=text]:focus,input[type=number]:focus,select:focus{outline:none;border-color:${t.accent}55}
  .sec{
    font-size:10px;color:${t.accent};letter-spacing:1.5px;
    margin:20px 0 10px;font-weight:700;text-transform:uppercase;
    display:flex;align-items:center;gap:8px;
  }
  .sec:first-child{margin-top:4px}
  .sec::after{content:'';flex:1;height:1px;background:${t.border}}
  `;
}

const VERDICT_STYLE = {
  confirmed: { color: "#4ade80", icon: "✓" },
  rejected:  { color: "#f87171", icon: "✗" },
  uncertain: { color: "#fbbf24", icon: "?" },
  pending:   { color: "#94a3b8", icon: "○" },
};

export default function App() {
  const [colorMode, setColorMode] = useState("dark");
  const t = THEMES[colorMode];

  const [slots, setSlots] = useState([
    { id: 0, exprFile: null, metaFile: null, name: "Dataset 1" },
  ]);
  const [loaded,        setLoaded]        = useState([]);
  const [groupMap,      setGroupMap]      = useState({});
  const [phase,         setPhase]         = useState("upload");
  const [log,           setLog]           = useState([]);
  const [hypotheses,    setHypotheses]    = useState([]);
  const [step,          setStep]          = useState(0);
  const [maxHypotheses, setMaxHypotheses] = useState(3);
  const [agentMode,     setAgentMode]     = useState("reproduce");
  const [currentStatus, setCurrentStatus] = useState("");
  const [streamingText, setStreamingText] = useState("");
  const [mappingGroups, setMappingGroups] = useState([]);
  const [mappingsOpen,  setMappingsOpen]  = useState(false);
  const [degDatasets,   setDegDatasets]   = useState([]);
  const [degFile,       setDegFile]       = useState(null);
  const [degGroupA,     setDegGroupA]     = useState("");
  const [degGroupB,     setDegGroupB]     = useState("");
  const [degUploading,  setDegUploading]  = useState(false);
  const [degStatus,     setDegStatus]     = useState("");
  const [runCost,       setRunCost]       = useState(null);
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
      if (errMsg) { setDegStatus(`Error: ${errMsg}`); return; }
      setDegDatasets(prev => [...prev.filter(d => d.name !== res.name), res]);
      setDegStatus(`Uploaded: ${res.n_genes} genes (${res.groupA} vs ${res.groupB})`);
      setMappingsOpen(true);
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
    setPhase("running"); setLog([]); setStep(0); setHypotheses([]); setCurrentStatus("Running pre-analysis..."); setStreamingText(""); setRunCost(0);

    const controller = new AbortController();
    abortRef.current = controller;
    let currentStep = 0;

    try {
      const res = await fetch("http://localhost:8000/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_ids: loaded.map(d => d.id), group_cols: groupMap, max_hypotheses: maxHypotheses, mode: agentMode }),
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
            if (entry.type === "thinking")       { setStep(++currentStep); setCurrentStatus(entry.text); setStreamingText(""); addLog(entry); continue; }
            if (entry.type === "thought_stream") { flushSync(() => setStreamingText(prev => prev + entry.delta)); continue; }
            if (entry.type === "thought")        { flushSync(() => setStreamingText("")); }
            if (entry.type === "usage")          { setRunCost(entry.total_cost_usd); continue; }
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

  const hasData = loaded.length > 0 || degDatasets.length > 0;

  return (
    <div style={{ minHeight: "100vh", background: t.appBg, fontFamily: "'Inter',system-ui,-apple-system,sans-serif", color: t.textPrimary }}>
      <style>{makeStyles(t)}</style>

      {/* Header */}
      <div style={{ height: 62, padding: "0 24px", display: "flex", alignItems: "center", gap: 14, background: t.sidebarBg, flexShrink: 0, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, background: `linear-gradient(90deg, ${t.accent}0a 0%, transparent 55%)`, pointerEvents: "none" }} />
        <div style={{ position: "absolute", bottom: 0, left: 0, right: 0, height: 1, background: t.border, pointerEvents: "none" }} />

        <div style={{ display: "flex", alignItems: "center", gap: 12, zIndex: 1 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: `linear-gradient(135deg, ${t.accent}28, ${t.accent}0e)`, border: `1px solid ${t.accent}40`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 19, color: t.accent, flexShrink: 0, boxShadow: `0 0 16px ${t.accent}20` }}>
            ◈
          </div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: t.textPrimary, letterSpacing: -0.3, lineHeight: 1.25 }}>Transcriptomic Agent</div>
            <div style={{ fontSize: 11, color: t.textMuted, lineHeight: 1.25, marginTop: 2, letterSpacing: 0.1 }}>AI-powered multi-dataset transcriptomic analysis</div>
          </div>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, zIndex: 1 }}>
          {phase === "running" && (
            <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "4px 10px", background: `${t.accent}10`, border: `1px solid ${t.accent}28`, borderRadius: 5 }}>
              <div className="blink" style={{ width: 6, height: 6, borderRadius: "50%", background: t.accent, boxShadow: `0 0 6px ${t.accent}`, flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: t.accent, fontWeight: 500 }}>
                {hypotheses.filter(h => h.status !== "pending").length}/{maxHypotheses} hypotheses
              </span>
            </div>
          )}
          {runCost !== null && (
            <div title="Estimated API cost (claude-sonnet-4-6)" style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px", background: `${t.accent}08`, border: `1px solid ${t.accent}22`, borderRadius: 5 }}>
              <span style={{ fontSize: 11, color: t.textMuted, fontFamily: "'JetBrains Mono',monospace" }}>$</span>
              <span style={{ fontSize: 12, color: t.textSecondary, fontFamily: "'JetBrains Mono',monospace", fontWeight: 500 }}>
                {runCost < 0.01 ? runCost.toFixed(4) : runCost.toFixed(3)}
              </span>
            </div>
          )}
          <button
            onClick={() => setColorMode(m => m === "dark" ? "light" : "dark")}
            style={{ background: "none", border: `1px solid ${t.border}`, color: t.textMuted, fontSize: 11, padding: "4px 10px", borderRadius: 5, cursor: "pointer", fontFamily: "inherit", letterSpacing: 0.3, transition: "all .15s" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = t.accent; e.currentTarget.style.color = t.accent; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = t.border; e.currentTarget.style.color = t.textMuted; }}
          >
            {colorMode === "dark" ? "Light" : "Dark"}
          </button>
        </div>
      </div>

      <div style={{ display: "flex", height: "calc(100vh - 62px)" }}>

        {/* LEFT PANEL */}
        <div style={{ width: 288, borderRight: `1px solid ${t.border}`, padding: "8px 14px 14px", overflowY: "auto", flexShrink: 0, background: t.sidebarBg }}>

          <div className="sec">Datasets</div>

          {slots.map(slot => (
            <DatasetSlot key={slot.id} slot={slot} canRemove={slots.length > 1} theme={t}
              onUpdate={(k, v) => updSlot(slot.id, k, v)} onRemove={() => removeSlot(slot.id)} />
          ))}

          <button className="btn bsm" style={{ marginBottom: 6, width: "100%" }} onClick={addSlot}>+ Add dataset</button>
          <button className="btn" style={{ marginBottom: 4, borderColor: `${t.accent}30`, color: t.accent }} onClick={loadAll} disabled={!slots.some(s => s.exprFile && s.metaFile)}>
            Load datasets
          </button>

          {/* DEG TABLE UPLOAD */}
          <div className="sec">DEG Datasets</div>
          <div style={{ marginBottom: 4 }}>
            <label className="uz" style={{ marginBottom: 6 }}>
              {degFile ? degFile.name : "Upload DEG table (.csv)"}
              <input type="file" accept=".csv" style={{ display: "none" }} onChange={e => setDegFile(e.target.files[0] || null)} />
            </label>
            <input type="text" value={degGroupA} onChange={e => setDegGroupA(e.target.value)} placeholder="Group A" style={{ marginBottom: 5 }} />
            <input type="text" value={degGroupB} onChange={e => setDegGroupB(e.target.value)} placeholder="Group B" style={{ marginBottom: 6 }} />
            <button className="btn bsm" style={{ width: "100%", marginBottom: 6 }}
              onClick={uploadDeg} disabled={!degFile || !degGroupA.trim() || !degGroupB.trim() || degUploading}>
              {degUploading ? "Uploading..." : "Upload DEG table"}
            </button>
            {degStatus && (
              <div style={{ fontSize: 12, marginBottom: 8, padding: "5px 9px", borderRadius: 5,
                color: degStatus.startsWith("Error") ? "#f87171" : "#4ade80",
                background: degStatus.startsWith("Error") ? (colorMode === "dark" ? "#2d0c0c" : "#fef2f2") : (colorMode === "dark" ? "#0a1f12" : "#f0fdf4"),
                border: `1px solid ${degStatus.startsWith("Error") ? "#6e202044" : "#4ade8030"}` }}>
                {degStatus}
              </div>
            )}
            {degDatasets.map(d => (
              <div key={d.name} className="slot ok" style={{ marginBottom: 8 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <span style={{ fontSize: 13, color: t.accent, fontWeight: 600 }}>{d.name}</span>
                  <button className="btn bsm bdng" style={{ padding: "2px 8px", fontSize: 11 }}
                    onClick={() => setDegDatasets(prev => prev.filter(x => x.name !== d.name))}>✕</button>
                </div>
                {(d.comparisons || []).map((c, i) => (
                  <div key={i} style={{ fontSize: 12, color: t.textSecondary, lineHeight: 1.8, fontFamily: "'JetBrains Mono',monospace" }}>
                    {c.groupA} <span style={{ color: t.textMuted }}>vs</span> {c.groupB}
                    <span style={{ color: t.textMuted, marginLeft: 6 }}>{c.n_genes} genes</span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          {hasData && <>
            <div className="sec">Group Columns</div>
            {loaded.map(ds => (
              <div key={ds.id} style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 12, color: t.textSecondary, marginBottom: 5, fontWeight: 600 }}>{ds.name}</div>
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
                <div style={{ fontSize: 11, color: t.textMuted, marginTop: 5, lineHeight: 1.9, fontFamily: "'JetBrains Mono',monospace" }}>
                  {ds.groups.map(g => <div key={g} style={{ paddingLeft: 2 }}>{g}</div>)}
                </div>
                <div style={{ fontSize: 11, color: t.textMuted, marginTop: 4, opacity: 0.7 }}>
                  {ds.gene_count} genes · {ds.sample_count} samples
                </div>
              </div>
            ))}

            {/* GROUP MAPPINGS */}
            {(() => {
              const degGroups = degDatasets.flatMap(d => {
                const fromComparisons = (d.comparisons || []).flatMap(c => [c.groupA, c.groupB]);
                const topLevel = [d.groupA, d.groupB].filter(Boolean);
                return [...fromComparisons, ...topLevel];
              });
              const allGroups = [...new Set([...loaded.flatMap(ds => ds.groups), ...degGroups])];
              return (
                <>
                  <div className="sec" style={{ cursor: "pointer", userSelect: "none" }}
                    onClick={() => setMappingsOpen(p => !p)}>
                    <span>Group Mappings</span>
                    <span style={{ color: t.accent, fontSize: 11, marginLeft: -4 }}>{mappingsOpen ? "▾" : "▸"}</span>
                  </div>
                  {mappingsOpen && (
                    <div style={{ marginBottom: 10 }}>
                      {mappingGroups.map((mg, idx) => (
                        <div key={idx} style={{ marginBottom: 8, padding: "9px 10px", border: `1px solid ${t.border}`, background: t.cardBg, borderRadius: 7 }}>
                          <div style={{ display: "flex", gap: 5, marginBottom: 7 }}>
                            <input type="text" value={mg.canonical} placeholder="Canonical name"
                              onChange={e => updateMappingCanonical(idx, e.target.value)} style={{ flex: 1 }} />
                            <button className="btn bsm bdng" onClick={() => removeMappingGroup(idx)}>✕</button>
                          </div>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 5 }}>
                            {allGroups.map(g => (
                              <label key={g} style={{ fontSize: 12, color: mg.aliases.has(g) ? t.accent : t.textMuted, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                                <input type="checkbox" checked={mg.aliases.has(g)} onChange={e => toggleAlias(idx, g, e.target.checked)} />
                                {g}
                              </label>
                            ))}
                          </div>
                          {mg.canonical && (
                            <div style={{ fontSize: 11, color: t.textMuted, lineHeight: 1.6, fontFamily: "'JetBrains Mono',monospace" }}>
                              "{mg.canonical}" ← {allGroups.map(g => (
                                <span key={g} style={{ marginRight: 6, color: mg.aliases.has(g) ? t.accent : t.textMuted }}>
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
            <div style={{ display: "flex", background: t.appBg, borderRadius: 7, border: `1px solid ${t.border}`, padding: 3, marginBottom: 12, gap: 2 }}>
              {[
                { key: "reproduce", label: "Reproduce", sub: "deterministic" },
                { key: "explore",   label: "Explore",   sub: "creative"       },
              ].map(({ key, label, sub }) => (
                <button key={key} onClick={() => setAgentMode(key)}
                  style={{
                    flex: 1,
                    background: agentMode === key ? t.cardBg : "transparent",
                    border: agentMode === key ? `1px solid ${t.accent}30` : "1px solid transparent",
                    color: agentMode === key ? t.accent : t.textMuted,
                    padding: "6px 8px", cursor: "pointer", borderRadius: 5, transition: "all .15s",
                    fontFamily: "inherit", fontSize: 12, fontWeight: agentMode === key ? 600 : 400,
                  }}>
                  {label}
                  <div style={{ fontSize: 10, color: agentMode === key ? t.accent : t.textMuted, marginTop: 1, opacity: agentMode === key ? 0.7 : 0.5 }}>{sub}</div>
                </button>
              ))}
            </div>

            <div className="sec">Hypotheses to test</div>
            <input type="number" value={maxHypotheses} min={1} max={30}
              onChange={e => setMaxHypotheses(parseInt(e.target.value))}
              style={{ marginBottom: 14 }} />

            <button
              style={{
                width: "100%", padding: "10px 14px", border: "1px solid transparent", borderRadius: 7,
                background: phase === "running" ? t.cardBg : t.elevatedBg,
                borderColor: phase === "running" ? t.border : `${t.accent}40`,
                color: phase === "running" ? t.textSecondary : t.accent,
                fontFamily: "inherit", fontSize: 13, fontWeight: 600,
                cursor: "pointer", transition: "all .15s", letterSpacing: 0.2,
              }}
              onMouseEnter={e => { if (phase !== "running") { e.currentTarget.style.background = t.startHoverBg; e.currentTarget.style.borderColor = `${t.accentHover}60`; e.currentTarget.style.color = t.accentHover; } }}
              onMouseLeave={e => { if (phase !== "running") { e.currentTarget.style.background = t.elevatedBg; e.currentTarget.style.borderColor = `${t.accent}40`; e.currentTarget.style.color = t.accent; } }}
              onClick={phase === "running" ? () => abortRef.current?.abort() : runAgent}>
              {phase === "running" ? "Stop" : "Start Agent"}
            </button>
          </>}
        </div>

        {/* LOG PANEL */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {currentStatus && (
            <div style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 10, padding: "9px 24px", borderBottom: `1px solid ${t.border}`, background: t.sidebarBg }}>
              <div className="spinner" />
              <span className="thinking-indicator" style={{ fontSize: 13, color: t.accent }}>{currentStatus}</span>
              {hypotheses.length > 0 && <span style={{ marginLeft: "auto", fontSize: 12, color: t.textMuted }}>{hypotheses.filter(h => h.status !== "pending").length}/{maxHypotheses} evaluated</span>}
            </div>
          )}

          <div style={{ flex: 1, overflowY: "auto", padding: "24px 28px" }}>
            {log.length === 0 && !currentStatus && (
              <div style={{ textAlign: "center", marginTop: "26vh" }}>
                <div style={{ width: 52, height: 52, margin: "0 auto 20px", background: `${t.accent}10`, border: `1px solid ${t.accent}20`, borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24, color: `${t.accent}50` }}>◈</div>
                <div style={{ fontSize: 15, color: t.textSecondary, fontWeight: 600, marginBottom: 8 }}>Ready to analyze</div>
                <div style={{ fontSize: 13, color: t.textMuted }}>Load datasets from the left panel, then start the agent!</div>
              </div>
            )}
            {log.length === 0 && currentStatus && (
              <div style={{ textAlign: "center", marginTop: "30vh" }}>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 20 }}>
                  <div style={{ width: 32, height: 32, border: `2px solid ${t.border}`, borderTopColor: t.accent, borderRadius: "50%", animation: "spin 0.75s linear infinite" }} />
                </div>
                <div style={{ fontSize: 14, color: t.accent, marginBottom: 6 }}>{currentStatus}</div>
                <div style={{ fontSize: 12, color: t.textMuted }}>This may take a few seconds...</div>
              </div>
            )}
            {log.map(e => <LogEntry key={e.id} entry={e} theme={t} />)}
            {streamingText && (
              <div className="ent" style={{ marginBottom: 12, paddingLeft: 16, borderLeft: `2px solid ${t.border}` }}>
                <div style={{ fontSize: 14, color: t.textPrimary, lineHeight: 1.75 }}>
                  {streamingText}<span className="blink" style={{ color: t.accent }}>▋</span>
                </div>
              </div>
            )}
            <div ref={logEnd} />
          </div>
        </div>

        {/* HYPOTHESIS PANEL */}
        {(phase === "running" || hypotheses.length > 0) && (
          <div style={{ width: 276, borderLeft: `1px solid ${t.border}`, padding: "8px 14px 14px", overflowY: "auto", flexShrink: 0, background: t.sidebarBg }}>
            <div className="sec">Hypotheses</div>
            {hypotheses.length === 0 && (
              <div style={{ fontSize: 13, color: t.textMuted }}>Formulating hypotheses...</div>
            )}
            {hypotheses.map(h => {
              const vs = VERDICT_STYLE[h.status] || VERDICT_STYLE.pending;
              return (
                <div key={h.id} style={{ marginBottom: 10, padding: "10px 12px", background: t.cardBg, border: `1px solid ${t.border}`, borderRadius: 7, borderLeft: `3px solid ${vs.color}55` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 7 }}>
                    <span className="tag" style={{ background: `${vs.color}15`, color: vs.color, fontSize: 11, border: `1px solid ${vs.color}30` }}>{h.id}</span>
                    <span style={{ fontSize: 11, color: vs.color, fontWeight: 600, letterSpacing: 0.5, textTransform: "uppercase" }}>{vs.icon} {h.status}</span>
                  </div>
                  <div style={{ fontSize: 13, color: t.textPrimary, lineHeight: 1.65 }}>{h.text}</div>
                  {h.evidence.length > 0 && (
                    <div style={{ marginTop: 9, borderTop: `1px solid ${t.border}`, paddingTop: 9 }}>
                      {h.evidence.map((ev, i) => (
                        <div key={i} style={{ fontSize: 12, color: t.textMuted, lineHeight: 1.6, marginBottom: 5 }}>
                          <span style={{ color: t.textSecondary }}>step {ev.step} [{ev.action}]</span> {ev.reasoning}
                          {ev.key_stats && Object.keys(ev.key_stats).length > 0 && (
                            <div style={{ marginTop: 3, paddingLeft: 8, borderLeft: `2px solid ${t.border}`, fontFamily: "'JetBrains Mono',monospace" }}>
                              {Object.entries(ev.key_stats).map(([gene, s]) => (
                                <span key={gene} style={{ display: "inline-block", marginRight: 10, color: t.textMuted, fontSize: 11 }}>
                                  <b style={{ color: t.textSecondary }}>{gene}</b>{": "}
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
