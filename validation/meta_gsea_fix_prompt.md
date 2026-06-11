# Prompt for Claude Code — meta→GSEA + method diversity + novelty/rigor dial

Context: validation against the manual fgsea ground truth (`validation/ground_truth_parsed.txt`) drove these changes. The meta→GSEA path (Fixes 1–4) is already in and works — keep it. Fixes 5–6 restore agent autonomy on top of it without turning the agent into a fixed pipeline. The ground truth is only a **recovery floor** (proof the agent isn't hallucinating); the goal is to exceed it. English only; commit + push when done. Stay disease-agnostic throughout (no group/disease/gene-set name hardcoded in `cross.py`, `seeder.py`, `runner.py`, `system_prompt.py`).

## Fixes 1–4 (already implemented — listed for reference, do not redo)
1. `cross_dataset_de` → genome-wide SIGNED meta ranking (`meta_rank`, signed Stouffer Z weighted by √n; all genes, no threshold).
2. `meta_gsea(groupA, groupB)` = `meta_rank` → `gseapy.prerank` vs `GMT_FILE`, signed NES + adj_p, top UP/DOWN. Default characterization path; per-file `gsea_enrichment` demoted to heterogeneity/QC diagnostic.
3. Seeder seeds per UNIQUE canonical comparison (direction-canonicalized), one data-driven seed each, recording the strongest opposite-direction set too.
4. Budget covers comparisons: evaluate ≥1 hypothesis per unique comparison before duplicates; effective budget ≥ n_unique_comparisons.

## Fix 5 — hypothesis budget as a novelty dial (floor, not pipeline)
The per-comparison meta-GSEA seeds are a coverage **floor**, not the whole job. Above the floor, hypotheses should get progressively more exploratory, so raising `max_hypotheses` yields more *different* hypotheses, not repetition.
- Keep the guaranteed floor: one meta-GSEA-seeded hypothesis per unique comparison (Fix 3/4).
- In `backend/agent/system_prompt.py`, add one short instruction: *"Once every comparison has been characterized, later hypotheses must go BEYOND single-comparison enrichment — propose cross-cutting questions (subtype-specificity via grouped contrasts e.g. one group vs the union of others; monotonic gradients across groups; within-group subtypes via subgroup_discovery; network rewiring; mechanistic links between two prior findings) and pick the method that fits each (preranked meta-GSEA, hypergeometric ORA, GO/KEGG over-representation, co-expression network, or execute_code if no tool fits). Never restate a seed or a previous hypothesis."*
- Existing duplicate-call / circular-reasoning guards stay; this only redirects spare budget toward novelty.

## Fix 6 — rigor scales WITH the novelty dial
The more unusual the hypothesis, the higher the false-discovery risk, so promotion to CONFIRMED must get *stricter*, not looser, as the counter grows. In `system_prompt.py`, require — for any hypothesis not in the per-comparison floor:
- **Convergence** — supported by ≥2 independent methods (e.g. meta-GSEA + ORA, or enrichment + network), not one.
- **Replication** — effect present in ≥2 datasets / pooled meta, never a single table.
- **Multiple-testing honesty** — judge significance on adj_p/FDR and explicitly acknowledge that scanning ~4000 gene sets inflates extremes; a large NES alone is not confirmation.
- **execute_code held to the same bar** — self-written analysis may not declare significance without the same FDR control + replication; it is an escape hatch for missing methods, not a way around the guards.
A novel hypothesis failing these stays UNCERTAIN, not CONFIRMED.

## Fix 7 — broaden methods/collections (optional but recommended)
- Add GO BP/MF (MSigDB C5) to the gene-set space so the agent can recover GO-level biology the Hallmark+C2 GMT cannot (the manual GT used GO separately). Either append C5 to the combined GMT or let a tool target a named collection.
- Make hypergeometric ORA (`pathway_enrichment`) a first-class alternative to meta-GSEA, and let the agent target a chosen collection (Hallmark / KEGG / Reactome / GO). Method choice is the agent's, per hypothesis — not a fixed order.
- (Optional) Allow novel hypotheses to be triaged against literature via the connected PubMed/Consensus tools, reported as separate "known vs novel" evidence. Literature absence is neither confirmation nor refutation.

## Disease-agnostic constraint (do not violate)
"Unique comparisons", "grouped contrasts", "gradients", "subtypes" are generic operations over whatever groups exist in the uploaded DEG tables (from groupA/groupB, direction-canonicalized so "X vs Y" = "Y vs X" with flipped sign). No group name, disease, tissue, or gene-set name may be hardcoded anywhere. The same code must behave identically for tumor/normal, treated/control, or any other groups. Endometriosis specifics below are an EXTERNAL validation criterion for this dataset only — they must NOT appear in code.

## Acceptance check (external validation, not code)
Rerun DEG-only. Generic pass criteria: one meta_gsea seed per unique comparison; 0 PENDING from budget; raising `max_hypotheses` produces visibly more cross-cutting (not repeated) hypotheses; novel hypotheses promoted to CONFIRMED only with convergence + replication + FDR honesty; no "groups are near-identical" verdict. Dataset-specific cross-check against `validation/ground_truth_parsed.txt`: the six per-comparison floors should reproduce GT direction at FDR<0.05 (e.g. PE vs EH immune/inflammatory UP, proliferation DOWN), and any Tier-2 finding beyond GT should carry its own convergence+replication evidence.
