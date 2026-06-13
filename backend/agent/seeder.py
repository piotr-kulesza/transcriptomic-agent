"""
Pre-analysis seeder: proper statistical pre-analysis run before the agent loop to
generate data-driven seed hypotheses and provide structured evidence extraction.
IDs are S1, S2, ... (distinct from agent-proposed H1, H2, ...).
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu as mwu
from statsmodels.stats.multitest import multipletests

from ..tools.cross import cross_dataset_de, resolve_group, meta_rank
from ..tools.single import _gsea_compute_es, _load_gene_sets
from ..agent.orient import canonical_order


def _top_gsea_hit(df_genes: pd.DataFrame, n_perm: int = 100,
                  min_size: int = 15, max_size: int = 500) -> dict | None:
    """
    Run pre-ranked GSEA (signed logFC ranking) on a gene-indexed DataFrame.
    Returns the top gene set by |NES| as {pathway, nes, adj_p, direction, leading_edge},
    or None when GMT_FILE is not configured, genes are too few, or no set passes the size filter.
    Failures are swallowed silently so seeding always completes.
    """
    try:
        gene_sets = _load_gene_sets()
    except RuntimeError:
        return None

    df = df_genes.copy().dropna(subset=["logFC"])
    if "adj_p" not in df.columns:
        df["adj_p"] = 1.0
    df["adj_p"] = df["adj_p"].clip(lower=1e-300).fillna(1.0)
    df = df.sort_values("logFC", ascending=False)
    genes_upper = [g.upper() for g in df.index.tolist()]
    rank_scores = df["logFC"].values.astype(float)
    gene_to_pos = {g: i for i, g in enumerate(genes_upper)}
    N = len(genes_upper)
    if N < 20:
        return None

    filtered: dict = {}
    for gs_name, members in gene_sets.items():
        idx = np.array([gene_to_pos[g.upper()] for g in members if g.upper() in gene_to_pos])
        if min_size <= len(idx) <= max_size:
            filtered[gs_name] = idx
    if not filtered:
        return None

    obs_es: dict = {}
    size_groups: dict = {}
    for name, idx in filtered.items():
        obs_es[name] = _gsea_compute_es(rank_scores, idx)
        size_groups.setdefault(len(idx), []).append(name)

    rng = np.random.default_rng(0)
    null_per_size: dict = {}
    for sz in size_groups:
        null_per_size[sz] = np.array([
            _gsea_compute_es(rank_scores, rng.choice(N, size=sz, replace=False))
            for _ in range(n_perm)
        ])

    records = []
    for name, es in obs_es.items():
        sz = len(filtered[name])
        null_arr = null_per_size[sz]
        pos_null = null_arr[null_arr > 0]
        neg_null = null_arr[null_arr < 0]
        if es >= 0:
            mean_pos = pos_null.mean() if pos_null.size > 0 else 1.0
            nes = es / mean_pos if mean_pos > 0 else float(es)
            raw_p = float((pos_null >= es).sum() + 1) / (pos_null.size + 1) if pos_null.size else 1.0
        else:
            mean_neg = abs(neg_null.mean()) if neg_null.size > 0 else 1.0
            nes = es / mean_neg if mean_neg > 0 else float(es)
            raw_p = float((neg_null <= es).sum() + 1) / (neg_null.size + 1) if neg_null.size else 1.0
        records.append({"pathway": name, "nes": nes, "p": raw_p})

    if not records:
        return None

    df_r = pd.DataFrame(records)
    _, adj_p_arr, _, _ = multipletests(df_r["p"].values, method="fdr_bh")
    df_r["adj_p"] = adj_p_arr
    df_r["abs_nes"] = df_r["nes"].abs()
    sig = df_r[df_r["adj_p"] < 0.25].sort_values("abs_nes", ascending=False)
    top = sig.iloc[0] if not sig.empty else df_r.sort_values("abs_nes", ascending=False).iloc[0]

    top_name = str(top["pathway"])
    top_idx = filtered[top_name]
    top_es = obs_es[top_name]
    mask = np.zeros(N, dtype=bool)
    mask[top_idx] = True
    abs_r = np.abs(rank_scores)
    nr = abs_r[mask].sum() or float(len(top_idx))
    rs = np.cumsum(np.where(mask, abs_r / nr, -1.0 / (N - len(top_idx))))
    if top_es >= 0:
        peak = int(np.argmax(rs))
        le_pos = sorted(top_idx[top_idx <= peak].tolist())[:5]
    else:
        trough = int(np.argmin(rs))
        le_pos = sorted(top_idx[top_idx >= trough].tolist())[:5]
    leading_edge = [genes_upper[i] for i in le_pos]

    return {
        "pathway": top_name,
        "nes": round(float(top["nes"]), 3),
        "adj_p": round(float(top["adj_p"]), 4),
        "direction": "UP" if float(top["nes"]) >= 0 else "DOWN",
        "leading_edge": leading_edge,
    }


def generate_seeds(datasets: list, mappings: dict = None, deg_datasets: dict = None, reference: str = None) -> tuple[list[dict], str, dict]:
    """
    Run genome-wide MWU + BH pre-analysis per dataset/group-pair and return
    (seed_hypotheses, seed_summary_text, seed_data).

    seed_hypotheses: list of hypothesis dicts with status="pending", seeded_by="auto".
    seed_summary_text: compact multi-line string injected into the system prompt.
    seed_data: full result tables for the report.
    """
    seeds: list[dict] = []
    summary_lines: list[str] = []
    seed_id = 1
    seed_data: dict = {"per_dataset_de": [], "cross_de": []}
    _deg = deg_datasets or {}

    # Convert list → dict keyed by dataset name for iteration
    ds_dict = {ds["name"]: ds for ds in datasets}

    # ── 1. Per-dataset differential expression (MWU + BH) ────────────────
    for ds_name, ds in ds_dict.items():
        try:
            expr = ds["expr"]
            meta = ds["meta"]
            gc = ds["group_col"]
            if not gc or gc not in meta.columns:
                summary_lines.append(f"  {ds_name}: skipped — no valid group column (gc={gc!r})")
                continue
            groups = meta[gc].dropna().unique().tolist()

            for group_a, group_b in itertools.combinations(groups, 2):
                sA = meta[meta[gc] == group_a].index.intersection(expr.columns)
                sB = meta[meta[gc] == group_b].index.intersection(expr.columns)
                if len(sA) < 3 or len(sB) < 3:
                    summary_lines.append(
                        f"  {ds_name} — {group_a} vs {group_b}: skipped (n<3)"
                    )
                    continue

                if expr.values.max() >= 25:
                    summary_lines.append(
                        f"  {ds_name}: skipped — data may not be log-transformed (max={expr.values.max():.1f})"
                    )
                    break

                # MWU per gene
                results = []
                for gene in expr.index:
                    a_vals = expr.loc[gene, sA].values.astype(float)
                    b_vals = expr.loc[gene, sB].values.astype(float)
                    if np.std(a_vals) == 0 and np.std(b_vals) == 0:
                        continue
                    try:
                        _, p = mwu(a_vals, b_vals)
                    except Exception:
                        continue
                    # Data is already log-transformed, so mean difference IS logFC directly
                    logfc = float(a_vals.mean() - b_vals.mean())
                    results.append({"gene": gene, "logFC": logfc, "p": p})

                if not results:
                    continue

                df = pd.DataFrame(results)
                _, adj_p, _, _ = multipletests(df["p"].values, method="fdr_bh")
                df["adj_p"] = adj_p
                sig = df[(df["adj_p"] < 0.05) & (df["logFC"].abs() > 0.5)].sort_values("adj_p")

                n_sig = len(sig)
                top_up   = sig[sig["logFC"] > 0].head(5)["gene"].tolist()
                top_down = sig[sig["logFC"] < 0].head(5)["gene"].tolist()
                top_genes = top_up + top_down

                summary_lines.append(
                    f"  {ds_name} — {group_a} vs {group_b}: "
                    f"{n_sig} DE genes (adj_p<0.05, |logFC|>0.5)"
                    + (f", top UP: {', '.join(top_up)}" if top_up else "")
                    + (f", top DOWN: {', '.join(top_down)}" if top_down else "")
                )

                # Store full table for report
                seed_data["per_dataset_de"].append({
                    "dataset": ds_name,
                    "groupA": group_a,
                    "groupB": group_b,
                    "n_sig": n_sig,
                    "top_up": sig[sig["logFC"] > 0].head(10)[["gene", "logFC", "adj_p"]].to_dict("records"),
                    "top_down": sig[sig["logFC"] < 0].head(10)[["gene", "logFC", "adj_p"]].to_dict("records"),
                })

                if top_genes:
                    description = (
                        f"{n_sig} genes DE between {group_a} and {group_b} "
                        f"in {ds_name} (MWU + BH, adj_p<0.05, |logFC|>0.5). "
                        f"Top UP: {', '.join(top_up) or 'none'}. "
                        f"Top DOWN: {', '.join(top_down) or 'none'}."
                    )
                    seeds.append({
                        "id": f"S{seed_id}",
                        "text": description,
                        "status": "pending",
                        "evidence": [],
                        "proposed_at": 0,
                        "seeded_by": "auto",
                        "genes": top_genes,
                    })
                    seed_id += 1
                else:
                    # No DE — seed a "no signal" hypothesis worth investigating
                    top_var = expr.var(axis=1).sort_values(ascending=False).head(5).index.tolist()
                    summary_lines.append(
                        f"  {ds_name} — {group_a} vs {group_b}: "
                        f"no DE found, top variable: {', '.join(top_var)}"
                    )
                    description = (
                        f"No significant DE between {group_a} and {group_b} in {ds_name} "
                        f"despite top variable genes: {', '.join(top_var)}. "
                        f"Investigate heterogeneity, subgroups, or effect sizes."
                    )
                    seeds.append({
                        "id": f"S{seed_id}",
                        "text": description,
                        "status": "pending",
                        "evidence": [],
                        "proposed_at": 0,
                        "seeded_by": "auto",
                        "genes": top_var,
                    })
                    seed_id += 1

                # For every comparison, also run ranked enrichment and seed the top hit
                df_indexed = df.set_index("gene")[["logFC", "adj_p"]]
                gsea_hit = _top_gsea_hit(df_indexed)
                if gsea_hit:
                    seeds.append({
                        "id": f"S{seed_id}",
                        "text": (
                            f"{ds_name} — {group_a} vs {group_b}: "
                            f"top ranked-enrichment signal is {gsea_hit['pathway']} "
                            f"({gsea_hit['direction']}, NES={gsea_hit['nes']}, adj_p={gsea_hit['adj_p']}). "
                            f"Investigate the full pathway landscape with pathway_enrichment or gsea_enrichment."
                        ),
                        "status": "pending",
                        "evidence": [],
                        "proposed_at": 0,
                        "seeded_by": "auto_gsea",
                        "genes": gsea_hit["leading_edge"],
                    })
                    seed_id += 1
                    summary_lines.append(
                        f"  → GSEA seed (S{seed_id - 1}): "
                        f"{gsea_hit['direction']} {gsea_hit['pathway']} NES={gsea_hit['nes']}"
                    )

        except Exception as e:
            summary_lines.append(f"  {ds_name}: seeder error — {e}")

    # ── 2. DEG table summary + one meta-GSEA seed per unique comparison ──
    #
    # Collect summary stats per file for the report, then iterate UNIQUE canonical
    # comparison pairs (not per-file) so 14 DEG files → ~6 seeds, not 14.
    _mappings_here = mappings or {}
    for ds_name, ds in _deg.items():
        try:
            for comp in ds["comparisons"]:
                df = comp["df"]
                sig = df[(df["adj_p"] < 0.05) & (df["logFC"].abs() > 0.5)]
                n_sig = len(sig)
                top_up   = sig[sig["logFC"] > 0].sort_values("adj_p").head(3).index.tolist()
                top_down = sig[sig["logFC"] < 0].sort_values("adj_p").head(3).index.tolist()
                summary_lines.append(
                    f"  {ds_name} — {comp['groupA']} vs {comp['groupB']}: {n_sig} DE genes"
                    + (f", top UP: {', '.join(top_up)}" if top_up else "")
                    + (f", top DOWN: {', '.join(top_down)}" if top_down else "")
                )
                seed_data["per_dataset_de"].append({
                    "dataset": ds_name,
                    "groupA": comp["groupA"],
                    "groupB": comp["groupB"],
                    "n_sig": n_sig,
                    "top_up": [{"gene": g, "logFC": float(df.loc[g, "logFC"]), "adj_p": float(df.loc[g, "adj_p"])} for g in top_up],
                    "top_down": [{"gene": g, "logFC": float(df.loc[g, "logFC"]), "adj_p": float(df.loc[g, "adj_p"])} for g in top_down],
                })
        except Exception as e:
            summary_lines.append(f"  {ds_name}: DEG summary error — {e}")

    # One meta-GSEA seed per unique canonical comparison pair
    seen_pairs: dict = {}  # canonical_key → (gA, gB) in CANONICAL orientation
    for ds in _deg.values():
        for comp in ds["comparisons"]:
            gA = resolve_group(comp["groupA"], _mappings_here)
            gB = resolve_group(comp["groupB"], _mappings_here)
            key = tuple(sorted([gA, gB]))
            if key not in seen_pairs:
                seen_pairs[key] = canonical_order(gA, gB, reference)

    for key, (gA, gB) in seen_pairs.items():
        try:
            rnk = meta_rank(datasets, _deg, gA, gB, mappings=_mappings_here)
            if rnk.empty:
                continue
            # Use _top_gsea_hit via a synthetic DataFrame (Z as logFC for ranking)
            df_rnk = rnk.rename("logFC").to_frame()
            gsea_hit = _top_gsea_hit(df_rnk)
            if not gsea_hit:
                continue

            n_sources = sum(
                1 for ds in _deg.values()
                for comp in ds["comparisons"]
                if {resolve_group(comp["groupA"], _mappings_here),
                    resolve_group(comp["groupB"], _mappings_here)} == {gA, gB}
            )
            seeds.append({
                "id": f"S{seed_id}",
                "text": (
                    f"{gA} vs {gB} meta-GSEA ({n_sources} source(s)): "
                    f"top signal is {gsea_hit['pathway']} "
                    f"({gsea_hit['direction']}, NES={gsea_hit['nes']}, adj_p={gsea_hit['adj_p']}). "
                    f"Verify and characterise both axes with "
                    f"meta_gsea(groupA='{gA}', groupB='{gB}')."
                ),
                "status": "pending",
                "evidence": [],
                "proposed_at": 0,
                "seeded_by": "auto_gsea",
                "genes": gsea_hit["leading_edge"],
                "_comparison": (gA, gB),
            })
            seed_id += 1
            summary_lines.append(
                f"  → meta-GSEA seed S{seed_id - 1} ({gA} vs {gB}, {n_sources} src): "
                f"{gsea_hit['direction']} {gsea_hit['pathway']} NES={gsea_hit['nes']}"
            )
        except Exception as e:
            summary_lines.append(f"  meta-GSEA {gA} vs {gB}: error — {e}")

    # ── 3. Cross-dataset DE (raw datasets + DEG tables combined) ─────────
    try:
        _mappings = mappings or {}
        all_groups: set[str] = set()

        for ds in datasets:
            gc = ds.get("group_col", "")
            if gc and gc in ds["meta"].columns:
                for raw_g in ds["meta"][gc].dropna().unique():
                    all_groups.add(resolve_group(str(raw_g), _mappings))

        for ds_name, ds in _deg.items():
            for comp in ds["comparisons"]:
                all_groups.add(resolve_group(comp["groupA"], _mappings))
                all_groups.add(resolve_group(comp["groupB"], _mappings))

        for group_a, group_b in itertools.combinations(all_groups, 2):
            n_raw = sum(
                1 for ds in datasets
                if (gc := ds.get("group_col", "")) and gc in ds["meta"].columns
                and group_a in {resolve_group(str(g), _mappings) for g in ds["meta"][gc].dropna().unique()}
                and group_b in {resolve_group(str(g), _mappings) for g in ds["meta"][gc].dropna().unique()}
            )
            n_deg = sum(
                1 for ds in _deg.values()
                if any(
                    {resolve_group(c["groupA"], _mappings), resolve_group(c["groupB"], _mappings)} == {group_a, group_b}
                    for c in ds["comparisons"]
                )
            )
            if n_raw + n_deg < 2:
                continue
            try:
                result = cross_dataset_de(
                    datasets, groupA=group_a, groupB=group_b,
                    topN=10, mappings=_mappings, deg_datasets=_deg,
                )
                if "error" in result:
                    continue
                top_up_cross   = [g["gene"] for g in result.get("top_consistent_up", [])[:3]]
                top_down_cross = [g["gene"] for g in result.get("top_consistent_down", [])[:3]]
                top_consistent = top_up_cross + top_down_cross
                n_sources      = n_raw + n_deg

                seed_data["cross_de"].append({
                    "groupA": group_a,
                    "groupB": group_b,
                    "top_up": result.get("top_consistent_up", [])[:5],
                    "top_down": result.get("top_consistent_down", [])[:5],
                    "n_tested": result.get("n_genes_tested"),
                    "interpretation": result.get("interpretation", ""),
                })

                summary_lines.append(
                    f"  CROSS — {group_a} vs {group_b}: "
                    f"{n_sources} sources, consistent genes: "
                    + (f"UP {', '.join(top_up_cross)}" if top_up_cross else "")
                    + (f" DOWN {', '.join(top_down_cross)}" if top_down_cross else "")
                )
                if top_consistent:
                    seeds.append({
                        "id": f"S{seed_id}",
                        "text": (
                            f"{len(top_consistent)} genes consistently DE across "
                            f"{n_sources} sources ({group_a} vs {group_b}). "
                            f"Top: {', '.join(top_consistent)}. "
                            f"Investigate replicability and biological significance."
                        ),
                        "status": "pending",
                        "evidence": [],
                        "proposed_at": 0,
                        "seeded_by": "auto_cross",
                        "genes": top_consistent,
                    })
                    seed_id += 1
            except Exception as e:
                summary_lines.append(f"  CROSS — {group_a} vs {group_b}: error — {e}")
    except Exception as e:
        summary_lines.append(f"  Cross-dataset seeder error — {e}")

    seed_summary = (
        "Pre-analysis statistical results:\n" + "\n".join(summary_lines)
        if summary_lines else ""
    )
    return seeds, seed_summary, seed_data


def extract_evidence_stats(action: str, result: dict, genes: list[str]) -> dict:
    """
    Extract key statistics from a tool result that are relevant to the given genes.
    Returns {} if genes is empty or if result contains an error.
    Pure function — no API calls, fully deterministic.
    """
    if not genes or not isinstance(result, dict) or "error" in result:
        return {}

    gene_set = {g.upper() for g in genes}
    stats: dict[str, dict] = {}

    if action == "differential_expression":
        for dir_key, dir_label in [("top_upregulated", "UP"), ("top_downregulated", "DOWN")]:
            for entry in result.get(dir_key, []):
                if entry.get("gene", "").upper() in gene_set:
                    stats[entry["gene"]] = {
                        "logFC": entry.get("logFC"),
                        "rbc":   entry.get("rbc"),
                        "adj_p": entry.get("adj_p"),
                        "direction": dir_label,
                    }

    elif action == "cross_dataset_de":
        for dir_key, dir_label in [("top_consistent_up", "UP"), ("top_consistent_down", "DOWN")]:
            for entry in result.get(dir_key, []):
                if entry.get("gene", "").upper() in gene_set:
                    stats[entry["gene"]] = {
                        "avg_abs_logFC":  entry.get("avg_abs_logFC"),
                        "fisher_adj_p":   entry.get("fisher_adj_p"),
                        "n_sig_datasets": entry.get("n_sig_datasets"),
                        "direction":      dir_label,
                    }

    elif action == "invariant_axis":
        for entry in result.get("top_invariant_genes", []):
            if entry.get("gene", "").upper() in gene_set:
                stats[entry["gene"]] = {
                    "invariance_score":      entry.get("invariance_score"),
                    "mean_abs_effect":       entry.get("mean_abs_effect"),
                    "p_bootstrap":           entry.get("p_bootstrap"),
                    "bootstrap_significant": entry.get("bootstrap_significant"),
                }

    elif action == "gene_expression_by_group":
        for gene, grp_data in result.get("result", {}).items():
            if gene.upper() in gene_set and isinstance(grp_data, dict):
                stats[gene] = {
                    grp: {"mean": v.get("mean"), "std": v.get("std")}
                    for grp, v in grp_data.items()
                    if isinstance(v, dict)
                }

    elif action == "gsea_enrichment":
        for dir_key in ("top_enriched_up", "top_enriched_down"):
            direction = "UP" if dir_key == "top_enriched_up" else "DOWN"
            for entry in result.get(dir_key, []):
                if any(g.upper() in gene_set for g in entry.get("leading_edge", [])):
                    stats[entry["pathway"]] = {
                        "nes": entry.get("nes"),
                        "adj_p": entry.get("adj_p"),
                        "direction": direction,
                        "leading_edge": entry.get("leading_edge", [])[:3],
                    }

    elif action == "pathway_enrichment":
        for entry in result.get("top_enriched", []):
            overlap = [g for g in entry.get("overlap_genes", []) if g.upper() in gene_set]
            if overlap:
                stats[entry["pathway"]] = {
                    "enrichment_fold": entry.get("enrichment_fold"),
                    "adj_p":           entry.get("adj_p"),
                    "overlap":         overlap,
                }

    elif action == "gene_network_hub":
        for hub in result.get("top_hubs", []):
            if hub.get("gene", "").upper() in gene_set:
                stats[hub["gene"]] = {"hub_degree": hub.get("degree")}
        for edge in result.get("top_edges", []):
            g1, g2 = edge.get("g1", ""), edge.get("g2", "")
            if g1.upper() in gene_set or g2.upper() in gene_set:
                stats[f"{g1}–{g2}"] = {"spearman_r": edge.get("r")}

    elif action == "subgroup_discovery":
        for dir_key in ("top_markers_sub1", "top_markers_sub2"):
            for entry in result.get(dir_key, []):
                if entry.get("gene", "").upper() in gene_set:
                    stats[entry["gene"]] = {
                        "logFC": entry.get("logFC"),
                        "adj_p": entry.get("adj_p"),
                    }

    elif action == "cross_dataset_rewiring":
        pair = result.get("gene_pair", "")
        if any(g.upper() in gene_set for g in pair.replace("—", " ").replace("–", " ").split()):
            stats["rewiring"] = {
                "max_r":              result.get("max_r"),
                "min_r":              result.get("min_r"),
                "rewiring_magnitude": result.get("rewiring_magnitude"),
            }

    # Strip None values from leaf dicts for cleanliness
    return {
        gene: {k: v for k, v in s.items() if v is not None}
        for gene, s in stats.items()
        if isinstance(s, dict)
    }
