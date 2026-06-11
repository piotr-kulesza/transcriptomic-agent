# Prompt for Claude Code — fix hypothesis ID desync AND make "confirmed" evidence-gated

A 30-hypothesis run froze at 2/30 for many minutes. Root cause in `backend/agent/runner.py`: the agent invents its own hypothesis IDs (H18, H19…) while the runner assigns IDs sequentially as `H{hypo_counter}` on `propose` (line ~383). When the agent emits `evaluate hypothesis_id="H18"`, the lookup `next((x for x in hypotheses if x["id"]==id), None)` returns None and the verdict is **silently dropped** (line ~485, `if h:` with no else). So `evaluated` never advances, DONE stays blocked (`evaluated < max_hypotheses`, line ~400), and the agent grinds to the `max_steps = max_hypotheses*5` safety cap (= 150 steps) while spraying verdicts at phantom IDs.

Fixing only the ID lookup would un-freeze the run but entrench a deeper problem: a verdict is currently just text the agent writes — nothing checks that the claimed evidence (≥2 methods, ≥2 datasets, FDR<0.05) actually exists. Auto-accepting every evaluation would make the run finish fast but with shallow, sometimes self-contradictory verdicts. So implement BOTH layers. English only; keep everything disease-agnostic (gating uses only method/dataset counts and FDR — never biology). Commit + push when done.

## Layer 1 — shared hypothesis state, real IDs, closed feedback loop
1. **Show the canonical hypothesis list to the agent every step.** In the per-step user message, include each hypothesis: `id`, short text, `status`, and evidence count (e.g. `H3 [pending, 1 evidence]: ...`). The agent must reference these exact IDs.
2. **No silent drops.** When `evaluate` targets an unknown `hypothesis_id`:
   - If the action carries `text` (and optional `genes`), auto-register it as a NEW `pending` hypothesis (assign the next `H{hypo_counter}` id), attach this step's evidence, and report the assigned id back to the agent. Do NOT mark it confirmed here.
   - If it carries no text, emit an `error` event and a corrective user message: `hypothesis_id 'X' not found. Valid IDs: [...]. Propose it first or evaluate an existing id.` Do not advance silently.
3. **System prompt contract** (`system_prompt.py`): "Only evaluate hypothesis IDs shown in the current hypothesis list. Never invent IDs. Propose a hypothesis (get its assigned id) before adding evidence to it."

## Layer 2 — verdict gated by accumulated evidence (runner-enforced, not agent-asserted)
A hypothesis accumulates `evidence` across steps; the runner — not the agent's prose — decides when it may become terminal.
1. **Record structured evidence per attach.** Reuse `extract_evidence_stats(action, result, genes)` (already called at line ~496) to store, per evidence item: the tool `action`, the dataset count (`n_datasets` / `n_datasets_pooled` where available), the best FDR/adj_p, and direction.
2. **Define a method family per tool** so convergence can't be gamed: e.g. `meta_gsea` + `gsea_enrichment` = family "enrichment_ranked"; `pathway_enrichment` = "enrichment_ora"; `deg_voting`/`deg_biomarker_ranking` = "deg_replication"; `network_meta_analysis`/`cross_dataset_rewiring`/`gene_network_hub` = "network"; `deg_direction_comparison` = "direction". **Multiple `meta_gsea` calls with different `collection_prefix` count as ONE family**, not two (this is exactly how the last run faked "2 methods").
3. **Gate the verdict.** When the agent requests `confirmed`:
   - require evidence from **≥2 distinct method families**, AND **replication** (≥2 datasets or a pooled meta with `n_datasets_pooled ≥ 2`), AND **significance** (at least one FDR/adj_p < 0.05).
   - If satisfied → set `confirmed`. If not → set `uncertain` (or keep `pending`) and return a message stating exactly what is missing (e.g. "only 1 method family; need a second orthogonal method"). Do not let a bare "confirmed" through.
   - `rejected` requires at least one contradicting significant result, not bare assertion.
4. **Counter & DONE use the gated status.** `evaluated` and the DONE gate count only hypotheses that legitimately reached `confirmed`/`rejected`/`uncertain` under these rules.

## Layer 3 — terminate sensibly (so it doesn't grind to the 150-step cap)
- Allow DONE once every comparison floor hypothesis is resolved AND the last K proposals (e.g. 3) failed to introduce a hypothesis with a gene/leading-edge set distinct (Jaccard < 0.5) from already-resolved ones — i.e. stop when novelty is exhausted, rather than forcing `evaluated == max_hypotheses`. Keep `max_hypotheses` as an upper bound, not a quota.
- Keep the existing duplicate-call guard.

## Disease-agnostic constraint
All gating uses method-family counts, dataset counts, FDR, and gene-set overlap only. No group/disease/gene-set name anywhere in the logic.

## Acceptance check
Rerun DEG-only, max_hypotheses=30. Pass: the hypothesis counter advances steadily (no multi-minute freeze at a single value); evaluating an unknown id either registers it or returns a visible error, never a silent no-op; a hypothesis marked `confirmed` always has ≥2 distinct method families + ≥2-dataset replication + FDR<0.05 attached in the report; two `meta_gsea` calls with different collections do NOT by themselves satisfy convergence; the run ends via DONE when novelty is exhausted rather than running to 150 steps.
