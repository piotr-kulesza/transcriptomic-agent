/* ============================================================
   Hypothesis card model — derives the rich card shape consumed by
   HypothesisCard from the raw hypothesis object the backend streams
   (id, text, status, evidence[], translational). Pure: no I/O, no
   React. Everything here comes from fields already present on the
   evidence items (see backend/agent/runner.py `_ev_item` /
   ev_item construction): method_family, dataset_ids, best_fdr,
   het_i2, orientation, genes_up/down, enriched_up/down, key_stats.
   ============================================================ */

// method_family (backend) → short display label for the convergence chips.
const FAMILY_LABEL = {
  deg_replication: "DE",
  enrichment:      "GSEA",
  fisher_meta:     "meta",
  network:         "network",
  direction:       "direction",
  subgroup:        "subgroup",
  custom:          "code",
};

// Stable display order for the method-family chips.
const FAMILY_ORDER = ["deg_replication", "enrichment", "fisher_meta", "network", "direction", "subgroup", "custom"];

// Backend sentinel dataset ids (start with "_") are not real cohorts — exclude
// them from the replication ladder. Mirrors engine._VIRTUAL_DS handling.
const isRealDataset = (id) => typeof id === "string" && id.length > 0 && !id.startsWith("_");

// Format an FDR/p value compactly: scientific below 1e-3, else 2 sig figs.
function fmtP(v) {
  if (v == null || Number.isNaN(v)) return null;
  if (v === 0) return "0";
  return Math.abs(v) < 1e-3 ? v.toExponential(1).replace("e", "e") : v.toPrecision(2);
}

// Replication-row status from a per-cohort best FDR.
function fdrStatus(fdr) {
  if (fdr == null) return "warn";       // ran but no significance reported
  if (fdr < 0.05) return "ok";
  if (fdr < 0.10) return "warn";
  return "no";
}

/* Per-group effect directions. The backend stores an orientation string
   "A vs B" plus signed lists (genes_up / enriched_up = higher in A).
   We collapse the latest direction-bearing evidence into two arrows. */
function deriveDirections(evidence) {
  for (let i = evidence.length - 1; i >= 0; i--) {
    const ev = evidence[i];
    const orient = (ev.orientation || "").trim();
    if (!orient.includes(" vs ")) continue;
    const [a, b] = orient.split(" vs ").map((s) => s.trim());
    const up = (ev.genes_up?.length || 0) + (ev.enriched_up?.length || 0);
    const down = (ev.genes_down?.length || 0) + (ev.enriched_down?.length || 0);
    if (up === 0 && down === 0) {
      return [{ grp: a, reg: "flat" }, { grp: b, reg: "flat" }];
    }
    // "up" means higher in group A → A up, B down (and vice-versa).
    const aUp = up >= down;
    return [
      { grp: a, reg: aUp ? "up" : "down" },
      { grp: b, reg: aUp ? "down" : "up" },
    ];
  }
  return [];
}

/* Per-cohort replication ladder: best FDR per real dataset across all evidence. */
function deriveReplication(evidence) {
  const byDs = new Map(); // datasetId → best (min) fdr seen
  for (const ev of evidence) {
    for (const ds of ev.dataset_ids || []) {
      if (!isRealDataset(ds)) continue;
      const fdr = typeof ev.best_fdr === "number" ? ev.best_fdr : null;
      if (!byDs.has(ds)) byDs.set(ds, fdr);
      else {
        const cur = byDs.get(ds);
        if (fdr != null && (cur == null || fdr < cur)) byDs.set(ds, fdr);
      }
    }
  }
  return [...byDs.entries()].map(([acc, fdr]) => ({
    acc,
    stat: fdr != null ? `FDR ${fmtP(fdr)}` : "tested",
    status: fdrStatus(fdr),
  }));
}

/* Convergent method families present in the evidence. */
function deriveMethodFamilies(evidence) {
  const present = new Set(evidence.map((ev) => ev.method_family).filter(Boolean));
  return FAMILY_ORDER.filter((f) => present.has(f)).map((f) => ({
    name: FAMILY_LABEL[f] || f,
    on: true,
  }));
}

/* Best meta-analysis FDR (Fisher's method, from cross_dataset_de). */
function deriveMetaFDR(evidence) {
  const metas = evidence.filter((ev) => ev.method_family === "fisher_meta" && typeof ev.best_fdr === "number");
  if (!metas.length) return null;
  return fmtP(Math.min(...metas.map((ev) => ev.best_fdr)));
}

/* Worst-case cross-cohort heterogeneity (max I² across meta evidence). */
function deriveHeterogeneity(evidence) {
  const i2s = evidence.map((ev) => ev.het_i2).filter((v) => typeof v === "number");
  if (!i2s.length) return null;
  const pct = Math.round(Math.max(...i2s) * 100);
  return `I² = ${pct}%`;
}

/* Flatten the backend translational annotation (per-gene records) into the
   prototype's {targets, drugs, trials} shape. Annotation only — never evidence. */
function deriveTranslational(translational) {
  const genes = translational?.genes || [];
  if (!genes.length) return null;
  const targets = [];
  const drugs = new Set();
  const trials = new Set();
  for (const rec of genes) {
    if (rec.gene) targets.push(rec.gene);
    for (const d of rec.chembl_drugs || []) {
      const name = typeof d === "string" ? d : d?.name || d?.drug;
      if (name) drugs.add(name);
    }
    for (const t of rec.trials || []) {
      const id = typeof t === "string" ? t : t?.nct_id || t?.id;
      if (id) trials.add(id);
    }
  }
  if (!targets.length && !drugs.size && !trials.size) return null;
  return {
    targets,
    drugs: drugs.size ? [...drugs] : null,
    trials: trials.size ? [...trials] : null,
  };
}

/* Build the full card model from a streamed hypothesis object. */
export function buildCard(h) {
  const evidence = Array.isArray(h.evidence) ? h.evidence : [];
  const status = (h.status || "pending").toLowerCase();
  const state = ["confirmed", "uncertain", "rejected", "testing", "pending"].includes(status) ? status : "pending";
  return {
    id: h.id,
    statement: h.text || "",
    state,
    directions: deriveDirections(evidence),
    methodFamilies: deriveMethodFamilies(evidence),
    replication: deriveReplication(evidence),
    metaFDR: deriveMetaFDR(evidence),
    heterogeneity: deriveHeterogeneity(evidence),
    translational: state === "confirmed" ? deriveTranslational(h.translational) : null,
    evidenceCount: evidence.length,
  };
}
