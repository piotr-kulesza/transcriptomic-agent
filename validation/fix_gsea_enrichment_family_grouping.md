# Prompt for Claude Code — close the last orthogonality hole: group gsea_enrichment with the enrichment family

The evidence-gate fixes work, but one residual hole remains. In `run_20260611_015312` hypothesis H3 was CONFIRMED using `meta_gsea` (enrichment_ranked) + `gsea_enrichment` (per-file) as its "two method families." These are NOT orthogonal — both are preranked GSEA on the same differential-expression signal — so this bypasses the Fix-2 convergence requirement. Cause: the per-file `gsea_enrichment` tool is not grouped into the enrichment family, so it counts as a distinct family.

Fix: in the method-family map used by the `confirmed` gate (`backend/agent/runner.py`), put **`gsea_enrichment` into the same enrichment group as `meta_gsea` and `pathway_enrichment`** — i.e. enrichment group = {`enrichment_ranked` (meta_gsea), `enrichment_ora` (pathway_enrichment), and gsea_enrichment}. All three test gene-set enrichment of the same DE signal and must collectively count as a SINGLE enrichment family for convergence purposes. A `confirmed` verdict must therefore still include ≥1 family from the orthogonal group {deg_replication, network, direction, fisher_meta}; any combination of meta_gsea + pathway_enrichment + gsea_enrichment alone stays `uncertain`.

Keep everything else (replication-by-distinct-dataset, the orthogonal-group requirement, anti-gaming on multiple meta_gsea collections) unchanged. Disease-agnostic: family/tool identity and FDR only. Commit + push.

## Acceptance check
Rerun DEG-only. Pass: no hypothesis is `confirmed` on enrichment-only evidence even when it mixes meta_gsea, pathway_enrichment, and gsea_enrichment; an H3-type case (TNFα via meta_gsea + per-file gsea_enrichment) now requires a genuinely orthogonal family (e.g. deg_voting or direction) to reach `confirmed`, otherwise `uncertain`. Previously-valid confirmations that already had an orthogonal family (S1, S8, H1, H2) remain `confirmed`.
