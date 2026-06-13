import itertools
from collections import Counter, defaultdict, deque

import numpy as np
import pandas as pd

from .cross import resolve_group


def deg_voting(datasets: list, deg_datasets: dict = None,
               groupA: str = None, groupB: str = None,
               mappings: dict = None,
               adj_p_threshold: float = 0.05,
               logfc_threshold: float = 0.5,
               topN: int = 20, **_) -> dict:
    """
    For each gene, count how many DEG tables show it as significant
    (adj_p < threshold, |logFC| > threshold) with consistent direction.

    If groupA/groupB provided, only include comparisons matching those groups.
    Otherwise use all available comparisons.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}

    comparisons = []
    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            a = resolve_group(comp["groupA"], mappings)
            b = resolve_group(comp["groupB"], mappings)
            if groupA and groupB:
                if a == groupA and b == groupB:
                    comparisons.append((ds_name, comp, 1))
                elif a == groupB and b == groupA:
                    comparisons.append((ds_name, comp, -1))
            else:
                comparisons.append((ds_name, comp, 1))

    if not comparisons:
        return {"error": "No matching DEG comparisons found"}

    n_datasets = len(comparisons)
    gene_votes: dict = {}

    for ds_name, comp, direction in comparisons:
        df = comp["df"]
        sig = df[(df["adj_p"] < adj_p_threshold) & (df["logFC"].abs() > logfc_threshold)]
        for gene, row in sig.iterrows():
            if gene not in gene_votes:
                gene_votes[gene] = {"up": 0, "down": 0, "datasets": [], "logfcs": []}
            effective_logfc = float(row["logFC"]) * direction
            if effective_logfc > 0:
                gene_votes[gene]["up"] += 1
            else:
                gene_votes[gene]["down"] += 1
            gene_votes[gene]["datasets"].append(ds_name)
            gene_votes[gene]["logfcs"].append(round(effective_logfc, 3))

    if not gene_votes:
        return {"error": "No significant genes found across DEG tables"}

    results = []
    for gene, v in gene_votes.items():
        total = v["up"] + v["down"]
        consistent = v["up"] == total or v["down"] == total
        direction_label = "UP" if v["up"] >= v["down"] else "DOWN"
        consistency_score = max(v["up"], v["down"]) / total
        results.append({
            "gene": gene,
            "n_datasets": total,
            "freq": round(total / n_datasets, 3),
            "direction": direction_label,
            "consistent": consistent,
            "consistency_score": round(consistency_score, 3),
            "mean_logFC": round(sum(v["logfcs"]) / len(v["logfcs"]), 3),
            "datasets": v["datasets"],
        })

    results.sort(key=lambda x: (-x["n_datasets"], -x["consistency_score"], -abs(x["mean_logFC"])))
    top = results[:topN]
    fully_consistent = [r for r in results if r["consistent"]]

    orient_note = (
        f"[orientation: {groupA} vs {groupB}; logFC>0 = higher in {groupA}] "
        if groupA and groupB else ""
    )
    return {
        "n_comparisons": n_datasets,
        "n_genes_any": len(results),
        "n_genes_fully_consistent": len(fully_consistent),
        "top_genes": top,
        "orientation": f"{groupA} vs {groupB}; logFC>0 = higher in {groupA}" if groupA and groupB else "",
        "interpretation": (
            orient_note +
            f"Top: {top[0]['gene']} ({top[0]['n_datasets']}/{n_datasets} datasets, "
            f"{top[0]['direction']}, mean logFC={top[0]['mean_logFC']})"
            if top else orient_note + "No consistent genes found"
        ),
    }


def deg_cooccurrence_network(datasets: list, deg_datasets: dict = None,
                              groupA: str = None, groupB: str = None,
                              mappings: dict = None,
                              adj_p_threshold: float = 0.05,
                              logfc_threshold: float = 0.5,
                              min_cooccurrence: int = 2,
                              topN_genes: int = 50, **_) -> dict:
    """
    Build co-occurrence network from DEG tables.
    Edge between gene A and gene B if both are DE in the same comparison,
    with weight = number of comparisons where they co-occur.
    Only edges with weight >= min_cooccurrence are included.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}

    comparisons_genes = []
    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            a = resolve_group(comp["groupA"], mappings)
            b = resolve_group(comp["groupB"], mappings)
            if groupA and groupB:
                if not ((a == groupA and b == groupB) or (a == groupB and b == groupA)):
                    continue
            df = comp["df"]
            sig_genes = set(
                df[(df["adj_p"] < adj_p_threshold) & (df["logFC"].abs() > logfc_threshold)].index
            )
            if sig_genes:
                comparisons_genes.append((ds_name, sig_genes))

    if not comparisons_genes:
        return {"error": "No significant genes found in any comparison"}

    low_comparisons_warning = None
    if len(comparisons_genes) < 3:
        low_comparisons_warning = (
            f"Co-occurrence network requires >= 3 comparisons for meaningful results. "
            f"Only {len(comparisons_genes)} found. Results will show trivially connected graph."
        )

    edge_weights: dict = defaultdict(int)
    gene_freq: dict = defaultdict(int)

    for ds_name, genes in comparisons_genes:
        gene_list = sorted(genes)
        for g in gene_list:
            gene_freq[g] += 1
        for i in range(len(gene_list)):
            for j in range(i + 1, len(gene_list)):
                edge_weights[(gene_list[i], gene_list[j])] += 1

    filtered_edges = {pair: w for pair, w in edge_weights.items() if w >= min_cooccurrence}

    degree: Counter = Counter()
    for (g1, g2), w in filtered_edges.items():
        degree[g1] += w
        degree[g2] += w

    top_hubs = degree.most_common(topN_genes)
    top_edges = sorted(filtered_edges.items(), key=lambda x: -x[1])[: topN_genes * 2]

    result = {
        "n_comparisons": len(comparisons_genes),
        "n_edges_total": len(filtered_edges),
        "n_hub_genes": len(degree),
        "top_hubs": [{"gene": g, "weighted_degree": d} for g, d in top_hubs[:20]],
        "top_edges": [{"gene1": e[0][0], "gene2": e[0][1], "weight": e[1]} for e in top_edges[:30]],
        "interpretation": (
            f"Top hub: {top_hubs[0][0]} (weighted degree={top_hubs[0][1]}) "
            f"| {len(filtered_edges)} edges with co-occurrence >= {min_cooccurrence}"
            if top_hubs else "No co-occurrence network found"
        ),
    }
    if low_comparisons_warning:
        result["warning"] = low_comparisons_warning
    return result


def deg_biomarker_ranking(datasets: list, deg_datasets: dict = None,
                           groupA: str = None, groupB: str = None,
                           mappings: dict = None,
                           adj_p_threshold: float = 0.05,
                           logfc_threshold: float = 0.5,
                           topN: int = 15, **_) -> dict:
    """
    Composite biomarker score per gene:
      score = freq * consistency * mean_abs_logFC * mean_(-log10_adj_p)

    Higher score = more consistently DE with larger effect across datasets.
    Only genes significant in >= 2 datasets are ranked.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}

    gene_stats: dict = {}
    n_comparisons = 0

    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            a = resolve_group(comp["groupA"], mappings)
            b = resolve_group(comp["groupB"], mappings)
            if groupA and groupB:
                if a == groupA and b == groupB:
                    direction = 1
                elif a == groupB and b == groupA:
                    direction = -1
                else:
                    continue
            else:
                direction = 1
            n_comparisons += 1
            df = comp["df"]
            sig = df[(df["adj_p"] < adj_p_threshold) & (df["logFC"].abs() > logfc_threshold)]
            for gene, row in sig.iterrows():
                if gene not in gene_stats:
                    gene_stats[gene] = []
                gene_stats[gene].append({
                    "logFC": float(row["logFC"]) * direction,
                    "adj_p": max(float(row["adj_p"]), 1e-300),
                })

    if not gene_stats:
        return {"error": "No significant genes found"}

    results = []
    for gene, stats in gene_stats.items():
        if len(stats) < 1:
            continue
        logfcs = [s["logFC"] for s in stats]
        adj_ps = [s["adj_p"] for s in stats]
        n = len(stats)
        freq = n / n_comparisons
        mean_abs_logfc = float(np.mean([abs(l) for l in logfcs]))
        mean_neg_log_p = float(np.mean([-np.log10(p) for p in adj_ps]))
        up = sum(1 for l in logfcs if l > 0)
        consistency = max(up, n - up) / n
        direction = "UP" if up >= n - up else "DOWN"
        score = freq * consistency * mean_abs_logfc * mean_neg_log_p
        results.append({
            "gene": gene,
            "score": round(score, 4),
            "n_datasets": n,
            "freq": round(freq, 3),
            "direction": direction,
            "consistency": round(consistency, 3),
            "mean_abs_logFC": round(mean_abs_logfc, 3),
            "mean_neg_log10_adj_p": round(mean_neg_log_p, 3),
        })

    results.sort(key=lambda x: -x["score"])
    top = results[:topN]

    return {
        "n_comparisons": n_comparisons,
        "n_genes_ranked": len(results),
        "top_biomarkers": top,
        "interpretation": (
            f"Top biomarker: {top[0]['gene']} "
            f"(score={top[0]['score']}, {top[0]['n_datasets']} datasets, "
            f"{top[0]['direction']}, consistency={top[0]['consistency']})"
            if top else "No biomarkers found"
        ),
    }


def deg_direction_comparison(datasets: list, deg_datasets: dict = None,
                              mappings: dict = None,
                              comparisonA_groupA: str = None,
                              comparisonA_groupB: str = None,
                              comparisonB_groupA: str = None,
                              comparisonB_groupB: str = None,
                              adj_p_threshold: float = 0.05,
                              logfc_threshold: float = 0.5,
                              topN: int = 20, **_) -> dict:
    """
    Compare DE signatures between two biological comparisons.
    Finds concordant (same direction), discordant (opposite), and
    comparison-specific genes.

    Example: comparisonA = endometriosis vs normal
             comparisonB = adenomyosis vs normal
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}

    def collect_genes(gA: str, gB: str) -> dict:
        gene_logfcs: dict = {}
        for ds_name, ds in deg_datasets.items():
            for comp in ds["comparisons"]:
                a = resolve_group(comp["groupA"], mappings)
                b = resolve_group(comp["groupB"], mappings)
                if a == gA and b == gB:
                    direction = 1
                elif a == gB and b == gA:
                    direction = -1
                else:
                    continue
                df = comp["df"]
                sig = df[(df["adj_p"] < adj_p_threshold) & (df["logFC"].abs() > logfc_threshold)]
                for gene, row in sig.iterrows():
                    if gene not in gene_logfcs:
                        gene_logfcs[gene] = []
                    gene_logfcs[gene].append(float(row["logFC"]) * direction)
        return {gene: sum(lfc) / len(lfc) for gene, lfc in gene_logfcs.items()}

    genesA = collect_genes(comparisonA_groupA, comparisonA_groupB)
    genesB = collect_genes(comparisonB_groupA, comparisonB_groupB)

    if not genesA:
        return {"error": f"No genes found for {comparisonA_groupA} vs {comparisonA_groupB}"}
    if not genesB:
        return {"error": f"No genes found for {comparisonB_groupA} vs {comparisonB_groupB}"}

    shared = set(genesA) & set(genesB)
    only_A = set(genesA) - shared
    only_B = set(genesB) - shared
    n_union_significant = len(shared) + len(only_A) + len(only_B)
    coverage = round(len(shared) / n_union_significant, 3) if n_union_significant > 0 else 0.0

    concordant, discordant = [], []
    for gene in shared:
        lfc_a, lfc_b = genesA[gene], genesB[gene]
        entry = {
            "gene": gene,
            "logFC_A": round(lfc_a, 3),
            "logFC_B": round(lfc_b, 3),
            "direction_A": "UP" if lfc_a > 0 else "DOWN",
            "direction_B": "UP" if lfc_b > 0 else "DOWN",
        }
        (concordant if (lfc_a > 0) == (lfc_b > 0) else discordant).append(entry)

    concordant.sort(key=lambda x: -(abs(x["logFC_A"]) + abs(x["logFC_B"])) / 2)
    discordant.sort(key=lambda x: -(abs(x["logFC_A"]) + abs(x["logFC_B"])) / 2)

    only_A_top = sorted(
        [{"gene": g, "logFC_A": round(genesA[g], 3)} for g in only_A],
        key=lambda x: -abs(x["logFC_A"]),
    )[:topN]
    only_B_top = sorted(
        [{"gene": g, "logFC_B": round(genesB[g], 3)} for g in only_B],
        key=lambda x: -abs(x["logFC_B"]),
    )[:topN]

    label_A = f"{comparisonA_groupA} vs {comparisonA_groupB}"
    label_B = f"{comparisonB_groupA} vs {comparisonB_groupB}"

    coverage_warn = (
        " LOW COVERAGE: concordance stats are unreliable — most DE genes are comparison-specific;"
        " do NOT conclude similarity or identity between these groups."
        if coverage < 0.5 else ""
    )
    return {
        "comparison_A": label_A,
        "comparison_B": label_B,
        "n_genes_A": len(genesA),
        "n_genes_B": len(genesB),
        "n_shared": len(shared),
        "n_union_significant": n_union_significant,
        "coverage": coverage,
        "n_concordant": len(concordant),
        "n_discordant": len(discordant),
        "n_specific_A": len(only_A),
        "n_specific_B": len(only_B),
        "top_concordant": concordant[:topN],
        "top_discordant": discordant[:topN],
        "specific_to_A": only_A_top,
        "specific_to_B": only_B_top,
        "interpretation": (
            f"{len(concordant)} concordant, {len(discordant)} discordant genes; "
            f"coverage={coverage} ({len(shared)}/{n_union_significant} shared/union significant)."
            + coverage_warn
            + (f" Top concordant: {concordant[0]['gene']} "
               f"(logFC_A={concordant[0]['logFC_A']}, logFC_B={concordant[0]['logFC_B']})"
               if concordant else " No shared genes between comparisons.")
        ),
    }


def network_meta_analysis(datasets: list, deg_datasets: dict = None,
                          groupA: str = None, groupB: str = None,
                          mappings: dict = None, topN: int = 20, **_) -> dict:
    """
    Network meta-analysis using DEG tables as edges in a comparison network.
    Uses the Bucher indirect comparison method: logFC(A vs C) via B =
    logFC(A vs B) + logFC(B vs C), summing logFCs along all simple paths
    through the network (max 3 hops). Each DEG comparison is one edge.

    If groupA/groupB are specified, analyses that specific pair.
    Otherwise analyses all pairs not covered by direct comparisons.
    """
    _deg = deg_datasets or {}
    _mappings = mappings or {}

    if not _deg:
        return {"error": "No DEG tables available for network meta-analysis"}

    # Build edge list: (gA, gB, df, label)
    # df indexed by gene; logFC = mean(gA) - mean(gB)
    edges = []
    for ds_name, ds in _deg.items():
        for comp in ds["comparisons"]:
            gA = resolve_group(comp["groupA"], _mappings)
            gB = resolve_group(comp["groupB"], _mappings)
            edges.append((gA, gB, comp["df"], f"{ds_name}:{gA}v{gB}"))

    if not edges:
        return {"error": "No valid comparisons found in DEG tables"}

    all_groups = sorted({g for gA, gB, _, _ in edges for g in (gA, gB)})

    # Adjacency: node → [(neighbor, df, label, direction)]
    # direction +1: logFC in df is (node vs neighbor); -1: negate for reverse traversal
    adj: dict = defaultdict(list)
    for gA, gB, df, label in edges:
        adj[gA].append((gB, df, label, +1))
        adj[gB].append((gA, df, label, -1))

    # Determine which pairs to analyze
    direct_pairs = {(gA, gB) for gA, gB, _, _ in edges} | {(gB, gA) for gA, gB, _, _ in edges}
    if groupA and groupB:
        gA_r = resolve_group(groupA, _mappings)
        gB_r = resolve_group(groupB, _mappings)
        if gA_r not in adj or gB_r not in adj:
            return {"error": f"Group {groupA!r} or {groupB!r} not found in DEG network"}
        pairs = [(gA_r, gB_r)]
    else:
        # Prefer indirect pairs; fall back to all pairs if everything is direct
        indirect = [(a, b) for a, b in itertools.combinations(all_groups, 2)
                    if (a, b) not in direct_pairs and (b, a) not in direct_pairs]
        pairs = indirect if indirect else list(itertools.combinations(all_groups, 2))

    if not pairs:
        return {"error": "No pairs to analyze", "network_groups": all_groups}

    comparison_results = []

    for src, dst in pairs:
        # BFS: find all simple paths src → dst up to 3 hops
        all_paths = []
        queue: deque = deque([(src, [], {src})])
        while queue:
            node, steps, visited = queue.popleft()
            if node == dst:
                all_paths.append(steps)
                continue
            if len(steps) >= 3:
                continue
            for neighbor, df, label, direction in adj[node]:
                if neighbor not in visited:
                    queue.append((neighbor, steps + [(df, label, direction)], visited | {neighbor}))

        if not all_paths:
            continue

        # Per-path: compute indirect logFC as sum of edge logFCs × direction
        path_estimates: list[pd.Series] = []
        for steps in all_paths:
            common = set(steps[0][0].index)
            for df, _, _ in steps[1:]:
                common &= set(df.index)
            if not common:
                continue
            common_list = sorted(common)
            lfc = pd.Series(0.0, index=common_list)
            for df, _, direction in steps:
                lfc += df.loc[common_list, "logFC"].values * direction
            path_estimates.append(lfc)

        if not path_estimates:
            continue

        # Combine: per-gene mean logFC and consistency across paths
        all_gene_idx = sorted(set().union(*[set(s.index) for s in path_estimates]))
        records = []
        for gene in all_gene_idx:
            vals = [float(s[gene]) for s in path_estimates if gene in s.index]
            mean_lfc = float(np.mean(vals))
            if abs(mean_lfc) < 0.3:
                continue
            consistency = float(max(0.0, 1.0 - np.std(vals) / (abs(mean_lfc) + 1e-6))) if len(vals) > 1 else 0.5
            records.append({
                "gene": gene,
                "indirect_logFC": round(mean_lfc, 3),
                "n_paths": len(vals),
                "consistency": round(consistency, 3),
                "score": abs(mean_lfc) * consistency * len(vals),
            })

        records.sort(key=lambda x: -x["score"])
        top_up   = [r for r in records if r["indirect_logFC"] > 0][:5]
        top_down = [r for r in records if r["indirect_logFC"] < 0][:5]

        n_direct   = sum(1 for s in all_paths if len(s) == 1)
        n_indirect = sum(1 for s in all_paths if len(s) > 1)

        comparison_results.append({
            "groupA": src,
            "groupB": dst,
            "n_direct_paths": n_direct,
            "n_indirect_paths": n_indirect,
            "top_up": top_up,
            "top_down": top_down,
        })

    if not comparison_results:
        return {
            "error": "No paths found between requested groups",
            "network_groups": all_groups,
            "direct_comparisons": [(gA, gB) for gA, gB, _, _ in edges],
        }

    parts = []
    for cr in comparison_results:
        up_genes   = [r["gene"] for r in cr["top_up"][:3]]
        down_genes = [r["gene"] for r in cr["top_down"][:3]]
        parts.append(
            f"{cr['groupA']} vs {cr['groupB']} "
            f"({cr['n_indirect_paths']} indirect path(s)): "
            + (f"UP {', '.join(up_genes)}" if up_genes else "no UP genes")
            + " | "
            + (f"DOWN {', '.join(down_genes)}" if down_genes else "no DOWN genes")
        )

    return {
        "network_groups": all_groups,
        "n_direct_edges": len(edges),
        "comparisons": comparison_results,
        "interpretation": (
            f"Network meta-analysis: {len(all_groups)} groups, {len(edges)} direct DEG comparisons, "
            f"{len(comparison_results)} pair(s) analyzed. " + "; ".join(parts)
        ),
    }
