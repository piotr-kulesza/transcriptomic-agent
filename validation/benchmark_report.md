# Engine vs limma + fgsea benchmark

Generated: 2026-06-15 23:19:33

Methodology: per-cohort limma is the fixture itself (limma topTable). Per-cohort fgsea is `gseapy.prerank` on each fixture's signed logFC against MSigDB Hallmarks. Engine pooled = `cross_dataset_de` + `meta_gsea`. R-only tools (ExpressAnalyst, metaVolcanoR) are noted in the methodology but not invoked.

## Headline — power gain from pooling

| Contrast | sig pathways (pooled) | sig in zero cohorts |
|----------|-----------------------|---------------------|
| OE vs EH | 40 | 1 |
| PE vs EH | 31 | 1 |
| DIE vs EH | 29 | 5 |

## OE vs EH

- contributing cohorts: 5
- pooled significant pathways (FDR<0.05): 40
- of which significant in zero single cohorts: **1** (power gain from pooling)

### Per-cohort concordance vs pooled

| cohort | DE J@100 | DE J@500 | DE Spearman ρ | path J@20 | sig (cohort) | shared sig | dir agree |
|--------|----------|----------|---------------|-----------|--------------|------------|-----------|
| `DEG 8` | 0.23 | 0.25 | 0.91 | 0.33 | 20 | 19 | 100% |
| `DEG 10` | 0.16 | 0.17 | 0.87 | 0.60 | 42 | 36 | 97% |
| `DEG 12` | 0.19 | 0.19 | 0.92 | 0.21 | 24 | 23 | 100% |
| `DEG 13` | 0.04 | 0.06 | 0.77 | 0.43 | 28 | 24 | 54% |
| `DEG 14` | 0.19 | 0.19 | 0.94 | 0.43 | 33 | 31 | 100% |

_Pathways significant only after pooling (first 1):_

- `HALLMARK_BILE_ACID_METABOLISM`

## PE vs EH

- contributing cohorts: 2
- pooled significant pathways (FDR<0.05): 31
- of which significant in zero single cohorts: **1** (power gain from pooling)

### Per-cohort concordance vs pooled

| cohort | DE J@100 | DE J@500 | DE Spearman ρ | path J@20 | sig (cohort) | shared sig | dir agree |
|--------|----------|----------|---------------|-----------|--------------|------------|-----------|
| `DEG 3` | 0.02 | 0.05 | 0.76 | 0.33 | 28 | 23 | 83% |
| `DEG 7` | 0.32 | 0.35 | 0.96 | 0.48 | 30 | 26 | 100% |

_Pathways significant only after pooling (first 1):_

- `HALLMARK_WNT_BETA_CATENIN_SIGNALING`

## DIE vs EH

- contributing cohorts: 3
- pooled significant pathways (FDR<0.05): 29
- of which significant in zero single cohorts: **5** (power gain from pooling)

### Per-cohort concordance vs pooled

| cohort | DE J@100 | DE J@500 | DE Spearman ρ | path J@20 | sig (cohort) | shared sig | dir agree |
|--------|----------|----------|---------------|-----------|--------------|------------|-----------|
| `DEG 1` | 0.06 | 0.12 | 0.75 | 0.33 | 22 | 15 | 100% |
| `DEG 4` | 0.32 | 0.28 | 0.95 | 0.48 | 23 | 22 | 100% |
| `DEG 11` | 0.01 | 0.02 | 0.58 | 0.21 | 0 | 0 | — |

_Pathways significant only after pooling (first 5):_

- `HALLMARK_ANGIOGENESIS`
- `HALLMARK_NOTCH_SIGNALING`
- `HALLMARK_HEME_METABOLISM`
- `HALLMARK_WNT_BETA_CATENIN_SIGNALING`
- `HALLMARK_OXIDATIVE_PHOSPHORYLATION`

## Interpretation

- High DE Jaccard / Spearman ρ between a cohort and the pooled result indicates that cohort is in agreement with the consensus. A low value flags a cohort that disagrees with the others.
- Direction agreement >90% across cohorts confirms the engine does not flip pathway directions during pooling.
- Power gain — pathways significant only after pooling — is the quantitative case for meta-analysis over single-tool DE/fgsea.
