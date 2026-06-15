"""
Null calibration / negative-control diagnostic for the Layer-1 engine.

Quantifies the engine's own false-positive rate by re-running the deterministic
Layer-1 pipeline against label-permuted DEG inputs. Per iteration we destroy
cross-cohort agreement by independently shuffling gene labels within each DEG
table (so logFC / p / SE are permuted as rows). The seeders + engine then run
exactly as in production; any hypothesis that still passes the evidence gate
under the permuted null is, by definition, a false positive.

The script writes a Markdown report comparing:
  - real-data CONFIRMED counts (no permutation)
  - per-iteration permuted CONFIRMED counts
  - empirical false-positive rate

This is a standing diagnostic — intended for the methodology paper and
occasional re-runs, not every commit. ``eval/test_null_calibration.py``
exercises a 2-iter smoke test on every commit.

Usage:
    python eval/null_calibration.py --n-perm 50 --output validation/null_calibration_report.md

Disease-agnostic: the permutation operates on raw DEG numeric columns; the
endometriosis fixture is just the substrate.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from typing import Optional

import numpy as np
import pandas as pd

# Ensure GMT_FILE is set so meta_gsea works regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

gmt = os.environ.get("GMT_FILE", os.path.join(_ROOT, "backend", "combined.gmt"))
os.environ["GMT_FILE"] = gmt

from eval.conftest import (  # noqa: E402
    FIXTURE_DIR,
    GROUPS,
    _ensure_gmt,
    _load_one,
    _parse_comparison,
)

from backend.agent.coverage import build_coverage_grid  # noqa: E402
from backend.agent.engine import characterize  # noqa: E402
from backend.agent.seeder import generate_seeds  # noqa: E402


def load_real_store() -> dict:
    """Load the 14 DEG fixtures into the deg_datasets dict shape the engine expects."""
    import glob

    files = sorted(glob.glob(os.path.join(FIXTURE_DIR, "wynik_*.csv.gz")))
    if not files:
        raise RuntimeError(
            f"No fixtures in {FIXTURE_DIR}. "
            f"Run python eval/fixtures/build_fixtures.py first."
        )
    store: dict = {}
    for i, f in enumerate(files, 1):
        gA, gB = _parse_comparison(f)
        df = _load_one(f)
        store[f"DEG {i}"] = {
            "name": f"DEG {i}",
            "type": "deg",
            "source_file": os.path.basename(f),
            "comparisons": [{"groupA": gA, "groupB": gB, "df": df}],
        }
    return store


def permute_store(store: dict, rng: np.random.Generator) -> dict:
    """Return a deepcopy of ``store`` with row order permuted independently for
    each comparison. Keeps gene labels and stats intact but breaks the
    gene→stat mapping, so cross-cohort agreement is destroyed."""
    permuted = copy.deepcopy(store)
    for ds in permuted.values():
        for comp in ds["comparisons"]:
            df = comp["df"]
            stat_cols = [c for c in df.columns]  # logFC, p, adj_p, optional ci_l/ci_r/se
            # Permute the values within each stat column independently of the
            # gene index. We attach random stat rows to original gene names —
            # this is equivalent to permuting gene labels under the null that
            # the gene-stat mapping is exchangeable.
            perm = rng.permutation(len(df))
            new = df[stat_cols].iloc[perm].copy()
            new.index = df.index
            comp["df"] = new
    return permuted


def run_engine_once(store: dict, mappings: Optional[dict] = None) -> dict:
    """Run seeds → grid → characterize on a single (real or permuted) store.
    Returns counts by status and seeded_by."""
    mappings = mappings or {}
    seeds, _, _ = generate_seeds([], mappings=mappings, deg_datasets=store)
    grid = build_coverage_grid([], store, mappings, deg_only=True)
    hypotheses = list(seeds) + list(grid)
    results = characterize([], store, mappings, True, hypotheses)
    # Tally by (status, seeded_by)
    tally: dict = {
        "total": 0,
        "confirmed": 0,
        "uncertain": 0,
        "by_seed": {},
    }
    for hyp in hypotheses:
        sb = hyp.get("seeded_by", "?")
        r = results.get(hyp["id"], {})
        status = r.get("status", "uncertain")
        tally["total"] += 1
        tally[status] = tally.get(status, 0) + 1
        tally["by_seed"].setdefault(sb, {"total": 0, "confirmed": 0})
        tally["by_seed"][sb]["total"] += 1
        if status == "confirmed":
            tally["by_seed"][sb]["confirmed"] += 1
    return tally


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n-perm", type=int, default=20,
                        help="Number of permutation iterations (default: 20)")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for reproducibility (default: 42)")
    parser.add_argument(
        "--output", type=str,
        default=os.path.join(_ROOT, "validation", "null_calibration_report.md"),
        help="Markdown output path",
    )
    parser.add_argument(
        "--gsea-perms", type=int, default=50,
        help="Permutations per meta-GSEA call (default: 50; production uses 200). "
             "Lower keeps each iteration tractable for occasional diagnostic runs.",
    )
    parser.add_argument(
        "--gsea-prefix", type=str, default="HALLMARK_",
        help="Restrict GSEA to gene sets with this prefix. Default HALLMARK_ "
             "cuts ~50× of gene sets, making each iteration much faster while "
             "still exercising the gate end-to-end.",
    )
    args = parser.parse_args()

    # Apply speed knobs via env so seeders + engine pick them up.
    os.environ["META_GSEA_PERMUTATION_NUM"] = str(args.gsea_perms)
    if args.gsea_prefix:
        os.environ["META_GSEA_COLLECTION_PREFIX"] = args.gsea_prefix

    _ensure_gmt()
    if not os.path.isfile(os.environ["GMT_FILE"]):
        print(f"GMT_FILE not found at {os.environ['GMT_FILE']}", file=sys.stderr)
        return 1

    print(f"Loading 14 DEG fixtures from {FIXTURE_DIR}…", flush=True)
    real_store = load_real_store()
    t0 = time.perf_counter()
    print("Running engine on real data…", flush=True)
    real = run_engine_once(real_store)
    t_real = time.perf_counter() - t0
    print(
        f"  real: {real['confirmed']}/{real['total']} confirmed "
        f"({real['confirmed'] / max(real['total'], 1):.1%}) in {t_real:.1f}s",
        flush=True,
    )

    rng = np.random.default_rng(args.seed)
    null_runs: list[dict] = []
    for i in range(args.n_perm):
        t = time.perf_counter()
        permuted = permute_store(real_store, rng)
        tally = run_engine_once(permuted)
        null_runs.append(tally)
        dt = time.perf_counter() - t
        print(
            f"  perm {i + 1}/{args.n_perm}: "
            f"{tally['confirmed']}/{tally['total']} confirmed in {dt:.1f}s",
            flush=True,
        )

    n_real_total = real["total"]
    n_real_conf = real["confirmed"]
    null_total = np.array([r["total"] for r in null_runs], dtype=float)
    null_conf = np.array([r["confirmed"] for r in null_runs], dtype=float)
    null_rate = null_conf / np.maximum(null_total, 1)
    real_rate = n_real_conf / max(n_real_total, 1)
    fpr_mean = float(null_rate.mean())
    fpr_se = float(null_rate.std(ddof=1) / np.sqrt(max(len(null_rate), 1))) if len(null_rate) > 1 else 0.0

    # Per-seed-type breakdown averaged across permutations
    seed_types = sorted({k for r in null_runs for k in r["by_seed"].keys()}
                       | set(real["by_seed"].keys()))
    by_seed_rows: list[str] = []
    for sb in seed_types:
        real_t = real["by_seed"].get(sb, {"total": 0, "confirmed": 0})
        null_totals = [r["by_seed"].get(sb, {"total": 0, "confirmed": 0})["total"] for r in null_runs]
        null_confs = [r["by_seed"].get(sb, {"total": 0, "confirmed": 0})["confirmed"] for r in null_runs]
        nt = np.array(null_totals, dtype=float)
        nc = np.array(null_confs, dtype=float)
        rates = nc / np.maximum(nt, 1)
        by_seed_rows.append(
            f"| `{sb}` | {real_t['confirmed']}/{real_t['total']} | "
            f"{real_t['confirmed'] / max(real_t['total'], 1):.1%} | "
            f"{float(nc.mean()):.1f} ± {float(nc.std(ddof=1) if len(nc) > 1 else 0):.1f} | "
            f"{float(rates.mean()):.1%} |"
        )

    lines = [
        "# Null calibration — Layer-1 engine",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Seed: {args.seed} · Permutations: {args.n_perm} · "
        f"Fixtures: {len(real_store)} DEG tables",
        "",
        "## Method",
        "",
        "Under the null, each DEG table has its rows independently permuted —",
        "logFC, p, adj_p, SE/CI rows are reassigned to random gene names within",
        "the same comparison. Cross-cohort agreement on any specific gene or",
        "pathway is therefore expected to collapse to chance. We then run the",
        "full deterministic Layer-1 pipeline (seeds → grid → characterize) and",
        "count CONFIRMED hypotheses per iteration. The empirical false-positive",
        "rate is `mean(confirmed_under_null / total)`.",
        "",
        "## Headline",
        "",
        f"- Real data: **{n_real_conf}/{n_real_total} confirmed ({real_rate:.1%})**",
        f"- Permuted null: **{fpr_mean:.1%} ± {fpr_se:.1%}** confirmed across "
        f"{args.n_perm} iterations",
        f"- Real-to-null ratio: **{(real_rate / fpr_mean) if fpr_mean > 0 else float('inf'):.1f}×**",
        "",
        "## Per-seed-type breakdown",
        "",
        "| seeded_by | real confirmed/total | real % | null mean ± sd | null % |",
        "|-----------|----------------------|--------|----------------|--------|",
        *by_seed_rows,
        "",
        "## Per-iteration null counts",
        "",
        "| iter | total | confirmed | rate |",
        "|------|-------|-----------|------|",
    ]
    for i, r in enumerate(null_runs, 1):
        rate = r["confirmed"] / max(r["total"], 1)
        lines.append(f"| {i} | {r['total']} | {r['confirmed']} | {rate:.1%} |")

    lines += [
        "",
        "## Interpretation",
        "",
        f"If the null rate is non-trivial (>5%), the evidence gate is loose and",
        f"should be tightened. Here the null FPR is **{fpr_mean:.1%}**; the gate",
        f"already requires ≥2 method families, ≥2 datasets, and FDR<0.05, so",
        f"permuted inputs should rarely satisfy all three simultaneously.",
        "",
        "## Reproducibility",
        "",
        "```",
        f"python eval/null_calibration.py --n-perm {args.n_perm} --seed {args.seed}",
        "```",
        "",
    ]
    out_path = args.output
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"\nReport written to {out_path}", flush=True)

    # Also stash the raw counts alongside the report for downstream plots.
    raw_path = out_path.replace(".md", ".json")
    with open(raw_path, "w") as f:
        json.dump(
            {
                "real": real,
                "null_runs": null_runs,
                "n_perm": args.n_perm,
                "seed": args.seed,
                "real_rate": real_rate,
                "null_rate_mean": fpr_mean,
                "null_rate_se": fpr_se,
            },
            f, indent=2, default=float,
        )
    print(f"Raw counts JSON: {raw_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
