# Prompt for Claude Code — tighten the evidence gate (replication counting + family orthogonality)

The evidence-gated verdict logic (in `backend/agent/runner.py`, the `confirmed` gate that checks method families + replication + FDR) works but has two holes seen in `run_20260611_002730`. Fix exactly these two; do not touch the novelty/early-stop logic or anything else. English only; keep gating disease-agnostic (counts, families, FDR only — no biology). Commit + push when done.

## Fix 1 — replication must count DISTINCT datasets, not method instances
Bug: S6 (OE vs PE, a single-source comparison) was CONFIRMED even though the agent's own reasoning said "mark uncertain as n_datasets=1". Cause: the replication check treated `meta_gsea` (pooled the one OE-vs-PE table) and `pathway_enrichment` ORA (run on that SAME table, DEG 12) as two separate datasets, so it counted replication=2. They are the same underlying dataset.
- Record, per evidence item, the **set of underlying dataset identifiers** that produced it: for `meta_gsea` use the actual pooled dataset names/ids (not just the integer `n_datasets_pooled`); for `pathway_enrichment`/`deg_*` use the specific DEG table id(s) used; for cross-dataset/meta tools the set of contributing datasets.
- Replication is satisfied only when the **union of distinct dataset ids across all of a hypothesis's evidence has size ≥ 2**. A comparison backed by a single underlying dataset can never reach `confirmed`, regardless of how many tools were run on it — it stays `uncertain`.
- Compare against S5 (DIE vs OE, also single-source) which correctly stayed `uncertain`; S6 must behave identically after the fix.

## Fix 2 — convergence requires an ORTHOGONAL family, not two enrichment flavors
Bug: many `confirmed` verdicts rest on `enrichment_ranked` (meta_gsea) + `enrichment_ora` (pathway_enrichment ORA) on the same comparison/gene signal. These are counted as "2 method families" but test the same differential-expression signal on largely the same genes, so they are not independent evidence.
- Group families into: **enrichment group = {enrichment_ranked, enrichment_ora}** (correlated — both test gene-set enrichment of the same DE signal) and **orthogonal group = {deg_replication (deg_voting / deg_biomarker_ranking), network (network_meta_analysis / cross_dataset_rewiring / gene_network_hub), direction (deg_direction_comparison), fisher_meta (cross_dataset_de)}**.
- For `confirmed`, require ≥2 distinct method families AND **at least one of them from the orthogonal group**. Two families both from the enrichment group (e.g. meta_gsea + ORA) do NOT satisfy convergence on their own — downgrade to `uncertain` with a message: "convergence needs an orthogonal method (replication/network/direction/meta), not a second enrichment flavor of the same signal."
- Keep the existing anti-gaming rule that multiple `meta_gsea` calls (any `collection_prefix`) collapse to a single `enrichment_ranked` instance.

## Disease-agnostic constraint
All checks use dataset ids, tool/family identity, and FDR only. No group/disease/gene-set names in the logic.

## Acceptance check
Rerun DEG-only. Pass: (a) every single-source comparison (e.g. OE vs PE, DIE vs OE) ends `uncertain`, never `confirmed`; (b) no hypothesis is `confirmed` on enrichment_ranked + enrichment_ora alone — each `confirmed` lists ≥1 orthogonal family (deg_replication / network / direction / fisher_meta) with ≥2 distinct datasets and FDR<0.05; (c) hypotheses that genuinely had orthogonal multi-dataset support (e.g. S1 OE vs EH, S8) remain `confirmed`.
