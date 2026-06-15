"""
Methodological benchmark — engine vs single-cohort limma + fgsea.

For each canonical contrast (OE/PE/DIE vs EH), compare:
  - per-cohort limma DE (the fixture itself — limma topTable output)
  - per-cohort pre-ranked fgsea via gseapy.prerank on the fixture's logFC
  - the engine's pooled equivalents — cross_dataset_de + meta_gsea

Concordance metrics, all written to a Markdown table:

  - **DE Jaccard@K** — overlap of top-K DE genes (by adj_p, then |logFC|).
    Reported for K = 100 and K = 500.
  - **DE Spearman ρ** — rank correlation of signed logFC between cohort and
    pooled (on common gene set).
  - **Pathway Jaccard@K** — overlap of top-K significant Hallmark pathways.
  - **Pathway direction agreement** — fraction of shared significant pathways
    where the NES sign matches between cohort and pooled.
  - **Power gain** — pathways significant (FDR<0.05) in the pooled meta but
    in zero single cohorts. Demonstrates where meta-analysis adds power.

ExpressAnalyst / metaVolcanoR are R-side tools; this script does not call out
to R. The fgsea/limma equivalents implemented here in Python are
methodologically the same as their R counterparts on the same input.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

os.environ.setdefault("GMT_FILE", os.path.join(_ROOT, "backend", "combined.gmt"))

from eval.conftest import FIXTURE_DIR, _ensure_gmt, _load_one, _parse_comparison  # noqa: E402

from backend.tools.cross import cross_dataset_de, meta_gsea  # noqa: E402
from backend.tools.single import _load_gene_sets  # noqa: E402

OE = "Ovarian endometriosis"
PE = "Peritoneal endometriosis"
DIE = "Deep infiltrating endometriosis"
EH = "Healthy endometrium"

PAIRS: List[Tuple[str, str, str]] = [
    ("OE",  OE,  EH),
    ("PE",  PE,  EH),
    ("DIE", DIE, EH),
]


def load_store() -> dict:
    import glob
    files = sorted(glob.glob(os.path.join(FIXTURE_DIR, "wynik_*.csv.gz")))
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


def cohorts_for(store: dict, gA: str, gB: str) -> List[Tuple[str, str, pd.DataFrame, int]]:
    """Yield (cohort_name, source_file, oriented_df, direction).
    Direction = +1 if the fixture's groupA==gA, else -1 (so logFC always means gA-up)."""
    out: List[Tuple[str, str, pd.DataFrame, int]] = []
    for name, ds in store.items():
        for comp in ds["comparisons"]:
            if {comp["groupA"], comp["groupB"]} != {gA, gB}:
                continue
            direction = 1 if comp["groupA"] == gA else -1
            df = comp["df"].copy()
            df["logFC"] = df["logFC"] * direction
            out.append((name, ds.get("source_file", ""), df, direction))
    return out


def top_de_genes(df: pd.DataFrame, k: int) -> List[str]:
    """Return top-K DE genes ranked by adj_p ascending, then |logFC| descending."""
    return (
        df.assign(_abs=df["logFC"].abs())
          .sort_values(["adj_p", "_abs"], ascending=[True, False])
          .head(k)
          .index.tolist()
    )


def fgsea_one_cohort(df: pd.DataFrame, gene_sets: dict, n_perm: int = 100,
                     min_size: int = 15, max_size: int = 500) -> pd.DataFrame:
    """gseapy.prerank on a single cohort's signed logFC. Returns a per-pathway
    DataFrame with columns: pathway, nes, fdr — same fields meta_gsea returns
    so concordance can be computed apples-to-apples."""
    import gseapy
    rnk = df["logFC"].copy()
    rnk.index = rnk.index.astype(str)
    rnk = rnk[~rnk.index.duplicated(keep="first")]
    rnk = rnk.sort_values(ascending=False)
    try:
        res = gseapy.prerank(
            rnk=rnk, gene_sets=gene_sets, outdir=None,
            min_size=min_size, max_size=max_size,
            permutation_num=n_perm, ascending=False,
            no_plot=True, verbose=False, seed=42, threads=1,
        )
    except Exception as e:
        return pd.DataFrame(columns=["pathway", "nes", "fdr", "_err"]).assign(_err=str(e))
    r = res.res2d.copy()
    return pd.DataFrame({
        "pathway": r["Term"].astype(str).tolist(),
        "nes": pd.to_numeric(r["NES"], errors="coerce").fillna(0.0).tolist(),
        "fdr": pd.to_numeric(r["FDR q-val"], errors="coerce").fillna(1.0).tolist(),
    })


def jaccard(a: List[str], b: List[str]) -> float:
    s1, s2 = set(a), set(b)
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    return len(s1 & s2) / len(s1 | s2)


def spearman(a: pd.Series, b: pd.Series) -> float:
    common = a.index.intersection(b.index)
    if len(common) < 5:
        return float("nan")
    return float(a.loc[common].corr(b.loc[common], method="spearman"))


def benchmark_one_pair(store: dict, label: str, gA: str, gB: str,
                       hallmark_only: bool = True,
                       de_k_list: Tuple[int, ...] = (100, 500),
                       pathway_k: int = 20,
                       gsea_perm: int = 100) -> Dict[str, Any]:
    cohorts = cohorts_for(store, gA, gB)
    if not cohorts:
        return {"error": f"no fixtures for {label}"}

    gene_sets = _load_gene_sets()
    if hallmark_only:
        gene_sets = {k: v for k, v in gene_sets.items() if k.startswith("HALLMARK_")}

    # Engine pooled outputs
    pooled_de = cross_dataset_de(
        datasets=[], deg_datasets=store, groupA=gA, groupB=gB, mappings={}, topN=2000,
    )
    pooled_gsea = meta_gsea(
        datasets=[], deg_datasets=store, groupA=gA, groupB=gB, mappings={},
        permutation_num=gsea_perm, topN=200,
        collection_prefix="HALLMARK_" if hallmark_only else None,
    )
    pooled_de_top: Dict[int, List[str]] = {}
    pooled_de_genes = (
        [g["gene"] for g in pooled_de.get("top_consistent_up", [])]
        + [g["gene"] for g in pooled_de.get("top_consistent_down", [])]
    )
    for k in de_k_list:
        pooled_de_top[k] = pooled_de_genes[:k]

    pooled_paths_all = (pooled_gsea.get("top_enriched_up", [])
                       + pooled_gsea.get("top_enriched_down", []))
    pooled_paths_sig = [p["pathway"] for p in pooled_paths_all if p["fdr"] < 0.05]
    pooled_paths_sig_with_sign = {p["pathway"]: (1 if p["nes"] >= 0 else -1)
                                  for p in pooled_paths_all if p["fdr"] < 0.05}

    # Pooled gene logFC for Spearman rank correlation: build from RE pooled
    # logFC where available, else avg |logFC| × direction.
    pooled_logfc: Dict[str, float] = {}
    for g in pooled_de.get("top_consistent_up", []):
        v = g.get("re_pooled_logFC")
        pooled_logfc[g["gene"]] = float(v) if v is not None else float(g.get("avg_abs_logFC", 0.0))
    for g in pooled_de.get("top_consistent_down", []):
        v = g.get("re_pooled_logFC")
        pooled_logfc[g["gene"]] = float(v) if v is not None else -float(g.get("avg_abs_logFC", 0.0))
    pooled_logfc_s = pd.Series(pooled_logfc, dtype=float)

    cohort_results: List[Dict[str, Any]] = []
    cohort_sig_paths: List[set] = []
    for cohort_name, src, cohort_df, _direction in cohorts:
        # limma side: top DE
        cohort_de_top = {k: top_de_genes(cohort_df, k) for k in de_k_list}
        # fgsea side: per-cohort GSEA
        cohort_gsea = fgsea_one_cohort(cohort_df, gene_sets, n_perm=gsea_perm)
        cohort_sig = cohort_gsea[cohort_gsea["fdr"] < 0.05]
        cohort_sig_paths.append(set(cohort_sig["pathway"].tolist()))

        # Direction agreement on shared significant pathways
        shared = set(cohort_sig["pathway"]) & set(pooled_paths_sig_with_sign.keys())
        if shared:
            agree = 0
            for path in shared:
                csign = 1 if cohort_sig.set_index("pathway").loc[path, "nes"] >= 0 else -1
                if csign == pooled_paths_sig_with_sign[path]:
                    agree += 1
            dir_agree = agree / len(shared)
        else:
            dir_agree = float("nan")

        cohort_top_paths = (
            cohort_gsea.sort_values("nes", key=lambda s: s.abs(), ascending=False)
                       .head(pathway_k)["pathway"].tolist()
        )

        cohort_results.append({
            "cohort": cohort_name,
            "source_file": src,
            "n_genes": len(cohort_df),
            "de_jaccard": {
                str(k): jaccard(cohort_de_top[k], pooled_de_top[k]) for k in de_k_list
            },
            "de_spearman": spearman(cohort_df["logFC"], pooled_logfc_s),
            "pathway_jaccard_top": jaccard(cohort_top_paths, [
                p["pathway"] for p in pooled_paths_all[:pathway_k]
            ]),
            "n_sig_pathways_cohort": int(len(cohort_sig)),
            "shared_sig_pathways": int(len(shared)) if shared else 0,
            "direction_agreement_on_shared": dir_agree,
        })

    # Power gain — pathways significant in pooled but in zero single cohorts
    sig_in_any_cohort = set().union(*cohort_sig_paths) if cohort_sig_paths else set()
    pooled_only_sig = [p for p in pooled_paths_sig if p not in sig_in_any_cohort]

    return {
        "label": label,
        "groupA": gA,
        "groupB": gB,
        "n_cohorts": len(cohorts),
        "n_sig_pathways_pooled": int(len(pooled_paths_sig)),
        "n_sig_pathways_pooled_only": int(len(pooled_only_sig)),
        "pooled_only_sig_pathways": pooled_only_sig[:25],
        "cohort": cohort_results,
    }


def render_markdown(results: List[Dict[str, Any]]) -> str:
    lines = [
        "# Engine vs limma + fgsea benchmark",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "Methodology: per-cohort limma is the fixture itself (limma topTable). "
        "Per-cohort fgsea is `gseapy.prerank` on each fixture's signed logFC "
        "against MSigDB Hallmarks. Engine pooled = `cross_dataset_de` + "
        "`meta_gsea`. R-only tools (ExpressAnalyst, metaVolcanoR) are noted in "
        "the methodology but not invoked.",
        "",
        "## Headline — power gain from pooling",
        "",
        "| Contrast | sig pathways (pooled) | sig in zero cohorts |",
        "|----------|-----------------------|---------------------|",
    ]
    for r in results:
        if "error" in r:
            continue
        lines.append(
            f"| {r['label']} vs EH | {r['n_sig_pathways_pooled']} | "
            f"{r['n_sig_pathways_pooled_only']} |"
        )
    lines.append("")

    for r in results:
        if "error" in r:
            lines.append(f"## {r.get('label', '?')}: error — {r['error']}\n")
            continue
        lines += [
            f"## {r['label']} vs EH",
            "",
            f"- contributing cohorts: {r['n_cohorts']}",
            f"- pooled significant pathways (FDR<0.05): {r['n_sig_pathways_pooled']}",
            f"- of which significant in zero single cohorts: "
            f"**{r['n_sig_pathways_pooled_only']}** (power gain from pooling)",
            "",
            "### Per-cohort concordance vs pooled",
            "",
            "| cohort | DE J@100 | DE J@500 | DE Spearman ρ | path J@20 | sig (cohort) | shared sig | dir agree |",
            "|--------|----------|----------|---------------|-----------|--------------|------------|-----------|",
        ]
        for c in r["cohort"]:
            j100 = c["de_jaccard"].get("100", 0.0)
            j500 = c["de_jaccard"].get("500", 0.0)
            sp = c["de_spearman"]
            sp_s = f"{sp:.2f}" if sp == sp else "—"
            agree = c["direction_agreement_on_shared"]
            agree_s = f"{agree:.0%}" if agree == agree else "—"
            lines.append(
                f"| `{c['cohort']}` | {j100:.2f} | {j500:.2f} | {sp_s} | "
                f"{c['pathway_jaccard_top']:.2f} | {c['n_sig_pathways_cohort']} | "
                f"{c['shared_sig_pathways']} | {agree_s} |"
            )
        if r["pooled_only_sig_pathways"]:
            lines += [
                "",
                f"_Pathways significant only after pooling (first {len(r['pooled_only_sig_pathways'])}):_",
                "",
            ]
            for p in r["pooled_only_sig_pathways"]:
                lines.append(f"- `{p}`")
        lines.append("")

    lines += [
        "## Interpretation",
        "",
        "- High DE Jaccard / Spearman ρ between a cohort and the pooled result "
        "indicates that cohort is in agreement with the consensus. A low value "
        "flags a cohort that disagrees with the others.",
        "- Direction agreement >90% across cohorts confirms the engine does not "
        "flip pathway directions during pooling.",
        "- Power gain — pathways significant only after pooling — is the "
        "quantitative case for meta-analysis over single-tool DE/fgsea.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=str,
        default=os.path.join(_ROOT, "validation", "benchmark_report.md"),
    )
    parser.add_argument("--all-collections", action="store_true",
                        help="Use the full GMT (not just Hallmarks). Much slower.")
    parser.add_argument("--gsea-perms", type=int, default=100,
                        help="GSEA permutations per call (default 100).")
    args = parser.parse_args()

    _ensure_gmt()
    store = load_store()

    results = []
    for label, gA, gB in PAIRS:
        print(f"Benchmarking {label} vs EH…", flush=True)
        t = time.perf_counter()
        r = benchmark_one_pair(
            store, label, gA, gB,
            hallmark_only=not args.all_collections,
            gsea_perm=args.gsea_perms,
        )
        results.append(r)
        print(f"  done in {time.perf_counter() - t:.1f}s", flush=True)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        f.write(render_markdown(results))
    with open(args.output.replace(".md", ".json"), "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nReport: {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
