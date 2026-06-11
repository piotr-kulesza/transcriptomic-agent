# Prompt for Claude Code — fix inf/NaN warnings in meta_rank GSEA ranking

During the last run the backend emitted repeated warnings that all trace to one root cause in `backend/tools/cross.py` `meta_rank`: the signed Stouffer Z ranking produces ±inf for highly significant genes, which then propagates into gseapy and into the per-file diagnostic. Fix the source; the rest are cosmetic. English only; commit + push when done. Do NOT change the methodology beyond winsorizing extreme z (that is intended).

## Root cause
In `meta_rank` (both the raw-dataset branch ~lines 207–209 and the DEG-table branch ~lines 225–227):
```python
p_c = np.clip(..., 1e-300, 1.0)
z_i = _norm.ppf(1.0 - p_c / 2.0)
```
`norm.ppf` saturates to +inf once `1 - p_c/2` rounds to exactly 1.0 in float64, i.e. for any `p < ~2e-16`. limma/DESeq tables routinely have p below that for top genes, so those genes get `z_i = +inf`. This causes:
- gseapy: "Input gene rankings contains inf values" (prerank input has inf),
- `single.py:366` `_gsea_compute_es`: "invalid value encountered in divide" (inf/inf → NaN when the inf-containing ranking is reused by the diagnostic).

## Fix 1 — bound the z-score in meta_rank (both branches)
Raise the p floor so `ppf` stays finite, and clip z as a safety net:
```python
p_c = np.clip(<p source>, 1e-12, 1.0)          # 1 - 5e-13 < 1.0 in float64 → ppf finite (~7.1)
z_i = _norm.ppf(1.0 - p_c / 2.0)
z_i = np.nan_to_num(z_i, nan=0.0, posinf=8.0, neginf=-8.0)
```
Apply identically to the raw-expression branch and the DEG-table branch. Also guard the final `stouffer` Series with `np.nan_to_num(..., posinf=8.0, neginf=-8.0)` before returning, so no inf can reach gseapy. This winsorizes extreme z (a single underflowed p no longer dominates the ranking) — methodologically desirable, keep it.

## Fix 2 — deterministic tie-break (optional, helps REPRODUCE mode)
gseapy warns "Duplicated values found in preranked stats" because genes with p≈1 collapse to z=0 (sign×0), creating many exact ties whose order gseapy breaks arbitrarily — non-deterministic in REPRODUCE mode. After computing the pooled `stouffer` Series, add a tiny deterministic tie-breaker derived from effect size, e.g. add `1e-6 * (mean signed logFC per gene)` so equal-z genes order by effect magnitude. Must be deterministic (no RNG). Keep the term small enough not to change the primary ranking.

## Do NOT touch (cosmetic, not our code)
- gseapy `FutureWarning: Series.replace method=` — internal to gseapy, resolves on upgrade.
- `NotOpenSSLWarning: LibreSSL` — interpreter/SSL env on macOS; optionally pin `urllib3<2`, otherwise ignore.
- `WatchFiles ... Reloading` — uvicorn `--reload` reacting to a mid-run edit; avoid editing backend files during a run.

## Acceptance check
Re-run a single `meta_gsea` (any comparison): no "Input gene rankings contains inf values" and no `single.py:366` divide warning; ranking Series contains no inf/NaN; NES/FDR for a known comparison (e.g. OE vs EH proliferation DOWN) stay essentially unchanged vs the last run (winsorizing should not move conclusions). With Fix 2, the duplicated-values warning drops or disappears and REPRODUCE mode gives identical leading-edge order across repeats.
