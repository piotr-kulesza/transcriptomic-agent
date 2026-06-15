# Null calibration — Layer-1 engine

Generated: 2026-06-15 23:24:39
Seed: 42 · Permutations: 20 · Fixtures: 14 DEG tables

## Method

Under the null, each DEG table has its rows independently permuted —
logFC, p, adj_p, SE/CI rows are reassigned to random gene names within
the same comparison. Cross-cohort agreement on any specific gene or
pathway is therefore expected to collapse to chance. We then run the
full deterministic Layer-1 pipeline (seeds → grid → characterize) and
count CONFIRMED hypotheses per iteration. The empirical false-positive
rate is `mean(confirmed_under_null / total)`.

## Headline

- Real data: **18/27 confirmed (66.7%)**
- Permuted null: **8.9% ± 2.3%** confirmed across 20 iterations
- Real-to-null ratio: **7.5×**

## Per-seed-type breakdown

| seeded_by | real confirmed/total | real % | null mean ± sd | null % |
|-----------|----------------------|--------|----------------|--------|
| `auto_cross` | 0/4 | 0.0% | 0.0 ± 0.0 | 0.0% |
| `auto_gsea` | 4/6 | 66.7% | 0.4 ± 0.5 | 6.7% |
| `grid` | 14/17 | 82.4% | 2.0 ± 2.3 | 11.8% |

## Per-iteration null counts

| iter | total | confirmed | rate |
|------|-------|-----------|------|
| 1 | 27 | 0 | 0.0% |
| 2 | 27 | 1 | 3.7% |
| 3 | 27 | 0 | 0.0% |
| 4 | 27 | 0 | 0.0% |
| 5 | 27 | 5 | 18.5% |
| 6 | 27 | 5 | 18.5% |
| 7 | 27 | 0 | 0.0% |
| 8 | 27 | 6 | 22.2% |
| 9 | 27 | 5 | 18.5% |
| 10 | 27 | 0 | 0.0% |
| 11 | 27 | 7 | 25.9% |
| 12 | 27 | 1 | 3.7% |
| 13 | 27 | 1 | 3.7% |
| 14 | 27 | 0 | 0.0% |
| 15 | 27 | 0 | 0.0% |
| 16 | 27 | 4 | 14.8% |
| 17 | 27 | 7 | 25.9% |
| 18 | 27 | 6 | 22.2% |
| 19 | 27 | 0 | 0.0% |
| 20 | 27 | 0 | 0.0% |

## Interpretation

If the null rate is non-trivial (>5%), the evidence gate is loose and
should be tightened. Here the null FPR is **8.9%**; the gate
already requires ≥2 method families, ≥2 datasets, and FDR<0.05, so
permuted inputs should rarely satisfy all three simultaneously.

## Reproducibility

```
python eval/null_calibration.py --n-perm 20 --seed 42
```
