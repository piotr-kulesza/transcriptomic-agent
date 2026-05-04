export default function DatasetSlot({ slot, onUpdate, onRemove, canRemove, theme: t }) {
  return (
    <div className={`slot ${slot.exprFile && slot.metaFile ? "ok" : ""}`}>
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <input
          type="text"
          value={slot.name}
          onChange={e => onUpdate("name", e.target.value)}
          style={{ flex: 1 }}
        />
        {canRemove && (
          <button className="btn bsm bdng" onClick={onRemove}>✕</button>
        )}
      </div>
      <label className={`uz ${slot.exprFile ? "ok" : ""}`}>
        <input type="file" accept=".csv" style={{ display: "none" }} onChange={e => onUpdate("exprFile", e.target.files[0])} />
        {slot.exprFile
          ? <span style={{ color: t.accent, fontSize: 12, fontWeight: 500 }}>✓ {slot.exprFile.name.slice(0, 26)}</span>
          : <span>+ Expression matrix</span>
        }
      </label>
      <label className={`uz ${slot.metaFile ? "ok" : ""}`}>
        <input type="file" accept=".csv" style={{ display: "none" }} onChange={e => onUpdate("metaFile", e.target.files[0])} />
        {slot.metaFile
          ? <span style={{ color: t.accent, fontSize: 12, fontWeight: 500 }}>✓ {slot.metaFile.name.slice(0, 26)}</span>
          : <span>+ Metadata</span>
        }
      </label>
    </div>
  );
}
