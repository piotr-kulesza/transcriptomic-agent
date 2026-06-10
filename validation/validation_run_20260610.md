# Agent Validation — `run_20260610_135737` vs manual fgsea/enrichR ground truth

**Date:** 2026-06-10
**Agent run:** `reports/run_20260610_135737_.md` (DEG-only mode, explore, 10 hypotheses: S1–S4 UNCERTAIN, H1–H6 CONFIRMED)
**Ground truth:** manual meta-analysis in `results_enrichment_new/` — 6 comparisons, each with fgsea Hallmarks (signed NES), KEGG, GO_BP/MF, enrichR (Reactome, MSigDB Hallmark, GO).
**Question:** does the agent recover the biology found by the manual fgsea/enrichR pipeline, and was the previous PE vs EH gap closed?

---

## 1. Headline result

| | Comparison | Agreement |
|---|---|---|
| 1 | DIE vs EH | ✅ Full |
| 2 | DIE vs OE | ✅ Full |
| 3 | OE vs EH | ✅ Full |
| 4 | OE vs PE | ◐ Partial |
| 5 | DIE vs PE | ❌ Discordant |
| 6 | PE vs EH | ❌ Missing |

**3/6 full, 1 partial, 2 problematic.** The agent reproduces the dominant biology of the three healthy-endometrium contrasts on the up-regulated, high-effect-size axis (myofibroblast/smooth-muscle, EMT, ovarian-steroidogenic identity). But the **PE immunological signature is still not covered** — the exact gap flagged in the previous run — and this run introduces a *new* over-statement: hypothesis **H4 claims DIE and PE are "transcriptionally nearly identical (>99.9% concordance)", which the ground truth directly contradicts.**

---

## 2. Per-comparison detail

### 1. DIE vs EH — ✅ Full
**Ground truth (fgsea):** UP — MYOGENESIS (NES +2.23), EMT (+2.08), TNFA/NFKB (+2.02); KEGG Cytoskeleton in muscle cells, Vascular smooth muscle contraction; GO actin-filament organization. DOWN — E2F_TARGETS, MYC, OXPHOS, G2M (proliferation/metabolism lower in lesion).
**Agent:** H1 (EMT: GREM1, MFAP5, TNC, SPOCK1; HALLMARK_EMT fold 27.8, adj_p≈0) + H3 (smooth-muscle: MYH11, ACTG2, CNN1, DES; HALLMARK_MYOGENESIS adj_p=0.001) + H6 (HMGB3 down, an E2F target).
**Verdict:** Both dominant UP gene-sets (myogenesis + EMT) recovered with the same leading genes. The coordinated proliferation/OXPHOS **down** axis is only touched via HMGB3 — see §3.

### 2. DIE vs OE — ✅ Full
**Ground truth:** KEGG Ovarian steroidogenesis + Cholesterol metabolism UP in OE side; GO reproductive-structure / gland development; fgsea COMPLEMENT, IL6/JAK/STAT, INTERFERON down in DIE (= higher in OE).
**Agent:** H2 + H5 — OE defined by gonadal/steroidogenic identity (NR5A1, GATA4, STAR, AMHR2), explicitly **discordant** in DIE vs OE (NR5A1/GATA4 DOWN in DIE). Maps cleanly onto "ovarian steroidogenesis / reproductive development".
**Verdict:** Correct discriminating axis and direction.

### 3. OE vs EH — ✅ Full
**Ground truth:** UP — EMT (+1.94), COMPLEMENT (+1.87), INTERFERON_GAMMA, COAGULATION, MYOGENESIS; KEGG complement/ECM/integrin; GO gland development (top, fold 2.0, padj 3.8e-13). DOWN — E2F/G2M/MYC/OXPHOS.
**Agent:** EMT + myofibroblast program (shared, H1/H3); C7 confirmed UP in OE (deg_voting, 4/5 datasets, logFC≈6) — i.e. the complement signal; ovarian identity (H2).
**Verdict:** EMT, complement (C7) and the ovarian axis all present. Agent's framing leans more specific (ovarian insufficiency / sexual development WikiPathways) than the GT's "gland development", but biologically concordant.

### 4. OE vs PE — ◐ Partial
**Ground truth:** KEGG Ovarian steroidogenesis UP in OE; **Wnt signaling + Phospholipase D UP in PE**; fgsea WNT_BETA_CATENIN, ANGIOGENESIS, ALLOGRAFT_REJECTION higher in PE; GO pattern specification / HOX.
**Agent:** H5 — OE vs PE discriminated by gonadal identity (NR5A1/GATA4/AMHR2) **and** iron/metal sequestration (LCN2, LTF; LCN2 UP in OE, DOWN in PE).
**Verdict:** The OE-steroidogenic side is captured; the **PE side (Wnt/angiogenesis/immune) is not.** The iron/LCN2 axis is a genuine agent contribution not prominent in the GT pathway tables (defensible, but unvalidated here).

### 5. DIE vs PE — ❌ Discordant
**Ground truth (DIEvsPE fgsea, 16 significant Hallmarks):** UP in DIE — MYC_TARGETS (+2.22), OXPHOS (+2.13), G2M, ADIPOGENESIS, FATTY_ACID_METABOLISM, MTORC1. DOWN in DIE (= UP in PE) — ALLOGRAFT_REJECTION (−2.22), INFLAMMATORY_RESPONSE, INTERFERON α/γ, IL6/JAK/STAT, KRAS. KEGG: Staph infection, complement, leukocyte transendothelial migration; GO: T-cell activation / MHC.
**Agent:** H4 — "DIE and PE are transcriptionally nearly identical vs EH (>99.9% concordance; only 2 discordant genes of 2102)."
**Verdict:** **Direct contradiction.** The manual pipeline shows DIE and PE differ along a clear proliferation/metabolism (DIE) vs immune (PE) axis. The agent's conclusion that they are near-identical is an artifact of its method — see §3.

### 6. PE vs EH — ❌ Missing (gap persists)
**Ground truth:** UP — ALLOGRAFT_REJECTION (NES +2.20, strongest), INFLAMMATORY_RESPONSE (+1.97), MYOGENESIS, KRAS, ANGIOGENESIS, EMT, INTERFERON_GAMMA; KEGG Staph infection, Hematopoietic cell lineage, **Allograft rejection, Asthma**; GO **MHC class II antigen presentation (fold 12–16×, padj 1e-11)**. The canonical PE immunological signature.
**Agent:** Only S3 (PE vs EH seed genes SFRP2/INMT/CCL14 → UNCERTAIN, 2 datasets) and H4 (folds PE into DIE). No pathway enrichment was run on PE vs EH; the allograft-rejection / MHC-II / inflammatory signature was never surfaced. CCL14 (a chemokine) appeared but was dismissed on replication grounds.
**Verdict:** **The PE immunological identity remains uncovered — same failure as the prior run, now compounded by H4 actively masking it.**

---

## 3. Why PE fails and DIE≈PE is overstated — one root cause

Both failures trace to a **methodological blind spot, not a biology error.** The agent's per-comparison reasoning in DEG-only mode rests on `deg_voting`, `deg_biomarker_ranking` and `deg_direction_comparison` — all of which operate on the **intersection of genes that individually pass the DEG threshold** in the uploaded tables.

- `deg_direction_comparison` computes concordance over *shared significant genes only*. PE's distinguishing biology is a **coordinated shift across many modest-effect immune genes** (MHC-II, interferon, allograft rejection) — exactly the regime GSEA/fgsea is built to detect and a hard per-gene FDR cut is built to miss. So the shared-gene set is dominated by the few large-effect stromal markers (SFRP2, MYH11, ACTG2…), which *are* concordant → the tool reports >99.9% concordance and the agent concludes "DIE = PE".
- The same blindness explains why the consistent **proliferation/OXPHOS down-axis** (E2F/MYC/G2M/OXPHOS, significant in 4–5 of the 6 GT contrasts) is essentially absent from the agent's narrative: high-logFC up-regulated stromal genes dominate `biomarker_ranking`, and the down-regulated housekeeping gene *sets* never reach the gene-level voting top-N.

**Implication:** the agent's confirmed hypotheses (H1–H3, H5) are trustworthy because they sit on the high-effect up-regulated axis where DEG-overlap and GSEA agree. The agent is systematically weak wherever the real signal is a distributed gene-set shift — which is precisely PE's immune identity and the proliferation down-axis.

---

## 4. Recommendations

**For the next run (close the gap):**
1. Run `pathway_enrichment` (GSEA-style, ranked) **per comparison**, not only on hand-picked biomarker gene lists. Force one enrichment call for PE vs EH and one for each healthy-endometrium contrast.
2. Seed an explicit **immunological PE hypothesis** ("PE vs EH is enriched for allograft rejection / MHC-II antigen presentation / inflammatory response") so the agent must test the immune axis directly.
3. Add a guard against over-claiming similarity: `deg_direction_comparison` should report **coverage** (shared-significant / union) alongside concordance, and the system prompt should forbid "nearly identical" verdicts when a GSEA contrast between the two groups is significant.
4. Surface **down-regulated gene sets** — current biomarker ranking is up-axis biased.

**For the manuscript:**
- This run is a clean, citable demonstration that the agent matches expert fgsea on the dominant axes (DIE myofibroblast/EMT, OE steroidogenic identity) — strong positive result for 3/6 contrasts.
- Report the PE/immune gap and the H4 over-statement honestly as a **known limitation of per-gene DEG-overlap methods vs GSEA**, and show the fix (per-comparison GSEA) closes it. Reviewers asking for the GEO2R/ExpressAnalyst benchmark will read this as methodological self-awareness.

---

## 5. Source files

- Agent run: `reports/run_20260610_135737_.md`
- Ground truth: `results_enrichment_new/{DIEvsEH,DIEvsOE,DIEvsPE,OEvsEH,OEvsPE,PEvsEH}/` — `fgsea_hallmarks.csv`, `KEGG.csv`, `GO_BP.csv`, `GO_MF.csv`, enrichR `*.csv`
- Parsed ground-truth digest: `validation/ground_truth_parsed.txt`
