/* ============================================================
   Run data — melanoma immune-checkpoint-blockade (ICB) cohort study.
   Realistic gene/pathway/stat content. Not real patient data.
   ============================================================ */

window.RUN = {
  project: {
    name: "Melanoma · ICB response",
    org: "Translational Immuno-Oncology Lab",
    runId: "run_8f31a2",
    started: "14:22:06",
    mode: "Reproduce",
    model: "Claude Sonnet 4.5",
    budget: 12,
    groupColumn: "response",
  },

  datasets: [
    {
      acc: "GSE91061", name: "Riaz — anti-PD-1 melanoma",
      samples: 109, genes: "22,483", platform: "RNA-seq", ready: true,
    },
    {
      acc: "TCGA-SKCM", name: "Cutaneous melanoma",
      samples: 472, genes: "20,531", platform: "RNA-seq", ready: true,
    },
    {
      acc: "GSE78220", name: "Hugo — anti-PD-1 melanoma",
      samples: 28, genes: "25,268", platform: "RNA-seq", ready: true,
    },
  ],

  groups: [
    { name: "Responder", n: 61, color: "var(--confirmed)" },
    { name: "Non-responder", n: 48, color: "var(--rejected)" },
  ],

  // coverage map: question-types (rows) × group comparisons (cols)
  coverage: {
    rows: ["Cytokine", "Antigen pres.", "Cytolytic", "Exhaustion", "Stromal"],
    cols: ["R/NR", "Pre/On", "Mut-hi/lo"],
    // status grid, row-major: ok | warn | rej | run | "" (untested)
    cells: [
      ["ok", "ok", "run"],
      ["ok", "ok", ""],
      ["ok", "run", ""],
      ["warn", "", ""],
      ["rej", "", ""],
    ],
  },

  // The live agent stream. Each step appears in sequence.
  // kind: plan|tool|gate ; verdict on gate steps drives hypothesis state.
  stream: [
    {
      t: "14:22:08", phase: "Ingest", kind: "tool", tool: "load_datasets",
      rationale: "Ingesting 3 cohorts. Harmonizing gene identifiers to HGNC symbols and collapsing to the shared feature space before any comparison.",
      result: { type: "info", text: "3 datasets · 18,204 shared genes" },
      meta: [{ k: "dropped", v: "4,279" }, { k: "id map", v: "HGNC v2025.1" }],
    },
    {
      t: "14:22:11", phase: "Setup", kind: "tool", tool: "detect_groups",
      rationale: "Auto-detected the <span class='gene'>response</span> column. Mapping RECIST labels → {Responder = CR/PR, Non-responder = SD/PD}.",
      result: { type: "ok", text: "2 groups · 61 R / 48 NR" },
    },
    {
      t: "14:22:14", phase: "Plan", kind: "plan", tool: "draft_hypotheses",
      rationale: "Acting as PI: drafting a structured hypothesis space across cytokine signaling, antigen presentation, cytolytic activity, T-cell exhaustion and stromal exclusion — 12 candidates, ranked by prior support.",
      result: { type: "info", text: "12 hypotheses queued" },
      meta: [{ k: "families", v: "5" }, { k: "ranked by", v: "prior + power" }],
    },
    {
      t: "14:22:19", phase: "Test", kind: "tool", tool: "differential_expression",
      rationale: "DESeq2 on GSE91061, Responder vs Non-responder, adjusting for biopsy timepoint and tumor purity.",
      result: { type: "ok", text: "412 DEGs at FDR < 0.05" },
      meta: [{ k: "model", v: "~purity+time+grp" }, { k: "shrinkage", v: "apeglm" }],
    },
    {
      t: "14:22:24", phase: "Test", kind: "tool", tool: "test_hypothesis", hyp: "H1",
      rationale: "H1 — IFN-γ response signature is elevated in responders. Scoring the <span class='gene'>HALLMARK_INTERFERON_GAMMA_RESPONSE</span> set per sample and comparing distributions.",
      result: { type: "ok", text: "ssGSEA Δ = +0.41 · p = 3.1e-7" },
      meta: [{ k: "set size", v: "200" }, { k: "test", v: "Mann–Whitney" }],
    },
    {
      t: "14:22:30", phase: "Replicate", kind: "tool", tool: "cross_validate", hyp: "H1",
      rationale: "Replicating H1 in TCGA-SKCM and GSE78220 to guard against cohort-specific artifacts. Direction and significance must hold independently.",
      result: { type: "ok", text: "3 / 3 cohorts replicated" },
    },
    {
      t: "14:22:36", phase: "Gate", kind: "gate", tool: "evidence_gate", hyp: "H1", verdict: "confirmed",
      rationale: "Evidence gate for H1: three method families agree (DE, GSEA, ssGSEA), replicated in 3/3 cohorts, consistent effect direction, low heterogeneity. Promoting to confirmed.",
      result: { type: "confirmed", text: "CONFIRMED · meta-FDR 2.1e-6" },
    },
    {
      t: "14:22:43", phase: "Test", kind: "tool", tool: "test_hypothesis", hyp: "H2",
      rationale: "H2 — cytolytic activity (geometric mean of <span class='gene'>GZMA</span> + <span class='gene'>PRF1</span>) is higher in responders, indicating active effector T-cells.",
      result: { type: "ok", text: "CYT Δ = +1.8 log2 · p = 8e-6" },
    },
    {
      t: "14:22:49", phase: "Gate", kind: "gate", tool: "evidence_gate", hyp: "H2", verdict: "confirmed",
      rationale: "Gate for H2: replicated 3/3, effect direction stable, FDR well below threshold. Confirmed.",
      result: { type: "confirmed", text: "CONFIRMED · meta-FDR 4.4e-5" },
    },
    {
      t: "14:22:56", phase: "Test", kind: "tool", tool: "test_hypothesis", hyp: "H3",
      rationale: "H3 — tumor-intrinsic Wnt/β-catenin activation excludes T-cells. Correlating <span class='gene'>CTNNB1</span> target score against CD8 infiltration across cohorts.",
      result: { type: "warn", text: "Effect present in 2/3 · cohorts disagree" },
      meta: [{ k: "I²", v: "68%" }, { k: "τ²", v: "0.31" }],
    },
    {
      t: "14:23:03", phase: "Gate", kind: "gate", tool: "evidence_gate", hyp: "H3", verdict: "uncertain",
      rationale: "Gate for H3: significant in GSE91061 and TCGA-SKCM but null in GSE78220, with high between-cohort heterogeneity (I² = 68%). Holding at uncertain — replication is not unanimous.",
      result: { type: "warn", text: "UNCERTAIN · heterogeneity ⚠" },
    },
    {
      t: "14:23:10", phase: "Test", kind: "tool", tool: "test_hypothesis", hyp: "H4",
      rationale: "H4 — an <span class='gene'>MITF</span>-high differentiation program predicts non-response. Testing program score association with outcome.",
      result: { type: "rej", text: "Replicated 1/3 · effect not robust" },
    },
    {
      t: "14:23:16", phase: "Gate", kind: "gate", tool: "evidence_gate", hyp: "H4", verdict: "rejected",
      rationale: "Gate for H4: nominal only in the discovery cohort, fails to replicate in 2/3 and effect direction flips in TCGA-SKCM. Rejected — interesting is not proven.",
      result: { type: "rej", text: "REJECTED · fails replication" },
    },
    {
      t: "14:23:23", phase: "Test", kind: "tool", tool: "test_hypothesis", hyp: "H5",
      rationale: "H5 — a TGF-β stromal signature marks immune-excluded non-responders. Scoring <span class='gene'>F-TBRS</span> and testing against outcome with cohort as a random effect.",
      result: { type: "running", text: "fitting mixed model…" },
    },
  ],

  hypotheses: [
    {
      id: "H1", state: "confirmed",
      statement: "IFN-γ response signaling is elevated in ICB responders",
      directions: [
        { grp: "Responder", reg: "up" },
        { grp: "Non-responder", reg: "down" },
      ],
      methodFamilies: [
        { name: "DE", on: true }, { name: "GSEA", on: true },
        { name: "ssGSEA", on: true }, { name: "decon", on: true },
      ],
      replication: [
        { acc: "GSE91061", n: 109, stat: "FDR 3e-7", status: "ok" },
        { acc: "TCGA-SKCM", n: 472, stat: "FDR 1e-5", status: "ok" },
        { acc: "GSE78220", n: 28, stat: "FDR 9e-4", status: "ok" },
      ],
      metaFDR: "2.1e-6", effect: "+0.41 ssGSEA", heterogeneity: null,
      translational: {
        targets: ["JAK1", "JAK2", "STAT1", "IFNGR1"],
        drugs: ["ruxolitinib", "interferon gamma-1b"],
        trials: ["NCT02646748", "NCT03711604"],
      },
    },
    {
      id: "H2", state: "confirmed",
      statement: "Cytolytic activity (GZMA·PRF1) is higher in responders",
      directions: [
        { grp: "Responder", reg: "up" },
        { grp: "Non-responder", reg: "down" },
      ],
      methodFamilies: [
        { name: "DE", on: true }, { name: "GSEA", on: true },
        { name: "ssGSEA", on: true }, { name: "decon", on: false },
      ],
      replication: [
        { acc: "GSE91061", n: 109, stat: "FDR 8e-6", status: "ok" },
        { acc: "TCGA-SKCM", n: 472, stat: "FDR 2e-4", status: "ok" },
        { acc: "GSE78220", n: 28, stat: "FDR 3e-3", status: "ok" },
      ],
      metaFDR: "4.4e-5", effect: "+1.8 log2 CYT", heterogeneity: null,
      translational: {
        targets: ["GZMB", "IL2", "PRF1"],
        drugs: ["aldesleukin", "nivolumab"],
        trials: ["NCT01621490"],
      },
    },
    {
      id: "H3", state: "uncertain",
      statement: "Wnt/β-catenin activation excludes CD8 T-cells from the tumor",
      directions: [
        { grp: "Responder", reg: "down" },
        { grp: "Non-responder", reg: "up" },
      ],
      methodFamilies: [
        { name: "DE", on: true }, { name: "GSEA", on: true },
        { name: "ssGSEA", on: false }, { name: "decon", on: "dis" },
      ],
      replication: [
        { acc: "GSE91061", n: 109, stat: "FDR 4e-3", status: "ok" },
        { acc: "TCGA-SKCM", n: 472, stat: "FDR 1e-2", status: "ok" },
        { acc: "GSE78220", n: 28, stat: "p = 0.41", status: "no" },
      ],
      metaFDR: "0.07", effect: "−0.22 corr", heterogeneity: "I² = 68%",
      translational: {
        targets: ["CTNNB1", "PORCN", "TCF7"],
        drugs: ["WNT974"],
        trials: ["NCT02649530"],
      },
    },
    {
      id: "H4", state: "rejected",
      statement: "MITF-high differentiation program predicts non-response",
      directions: [
        { grp: "Responder", reg: "flat" },
        { grp: "Non-responder", reg: "flat" },
      ],
      methodFamilies: [
        { name: "DE", on: true }, { name: "GSEA", on: false },
        { name: "ssGSEA", on: false }, { name: "decon", on: false },
      ],
      replication: [
        { acc: "GSE91061", n: 109, stat: "p = 0.03", status: "ok" },
        { acc: "TCGA-SKCM", n: 472, stat: "dir flip", status: "no" },
        { acc: "GSE78220", n: 28, stat: "p = 0.62", status: "no" },
      ],
      metaFDR: "0.41", effect: "n.s.", heterogeneity: "I² = 74%",
      translational: null,
    },
    {
      id: "H5", state: "testing",
      statement: "TGF-β stromal signature marks immune-excluded non-responders",
      directions: [
        { grp: "Responder", reg: "down" },
        { grp: "Non-responder", reg: "up" },
      ],
      methodFamilies: [],
      replication: [],
      metaFDR: null, effect: null, heterogeneity: null,
      translational: null,
    },
    {
      id: "H6", state: "pending",
      statement: "Antigen-presentation (HLA class I / B2M) loss in non-responders",
      directions: [], methodFamilies: [], replication: [],
      metaFDR: null, effect: null, heterogeneity: null, translational: null,
    },
  ],

  rigor: [
    { v: "0.4", suffix: "%", k: "Empirical FPR vs null permutations" },
    { v: "0.91", k: "Benchmark concordance (AUROC)" },
    { v: "3×", k: "Min. cohorts to confirm" },
  ],
};
