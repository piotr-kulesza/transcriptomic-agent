"""
Layer 1 Characterization Engine: deterministic, no LLM.

Walks all auto_gsea floor seeds and grid cells, runs primary + orthogonal
methods, applies the evidence gate as threshold logic, and returns a results
dict that the runner applies before starting the LLM loop.

Disease-agnostic: enumeration and gate are driven by group-configs, question
types, dataset/FDR thresholds — no biology hardcoded.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ..tools.cross import resolve_group, meta_gsea
from ..tools.deg import (
    deg_voting,
    deg_biomarker_ranking,
    deg_direction_comparison,
    deg_cooccurrence_network,
    network_meta_analysis,
)
from .coverage import _canonical_pair
from .orient import canonical_order, orientation_note

logger = logging.getLogger(__name__)

# --- Evidence-gate constants (mirror runner.py) ----------------------------
_ORTHOGONAL_FAMILIES = frozenset({
    "deg_replication", "fisher_meta", "network", "direction", "subgroup", "custom",
})
_VIRTUAL_DS = frozenset({"_ora_gene_list", "_gsea_unnamed", "_unknown"})
_METHOD_FAMILY: dict[str, str] = {
    "meta_gsea":              "enrichment",
    "deg_voting":             "deg_replication",
    "deg_biomarker_ranking":  "deg_replication",
    "network_meta_analysis":  "network",
    "deg_cooccurrence_network": "network",
    "deg_direction_comparison": "direction",
    "gene_network_hub":       "network",
}


# ---------------------------------------------------------------------------
# Gate helpers
# ---------------------------------------------------------------------------

def _gate(
    families: set[str],
    dataset_ids: set[str],
    best_fdr: Optional[float],
) -> tuple[str, list[str]]:
    """Apply the evidence gate. Returns (verdict, issues)."""
    issues: list[str] = []
    if len(families) < 2:
        issues.append(f"only {len(families)} method family ({', '.join(sorted(families)) or 'none'})")
    elif not (families & _ORTHOGONAL_FAMILIES):
        issues.append("no orthogonal family among present methods")
    real_ds = dataset_ids - _VIRTUAL_DS
    if len(real_ds) < 2:
        issues.append(f"only {len(real_ds)} distinct dataset(s) ({', '.join(sorted(real_ds)) or 'none'})")
    if best_fdr is None or best_fdr >= 0.05:
        fdr_str = f"{best_fdr:.4f}" if best_fdr is not None else "none"
        issues.append(f"FDR={fdr_str} (need <0.05 from at least one method)")
    return ("confirmed" if not issues else "uncertain"), issues


def _gsea_fdr(result: dict) -> Optional[float]:
    fdrs = [
        r.get("fdr", 1.0)
        for r in result.get("top_enriched_up", []) + result.get("top_enriched_down", [])
    ]
    return float(min(fdrs)) if fdrs else None


def _deg_ds_ids(deg_datasets: dict, gA: str, gB: str, mappings: dict) -> set[str]:
    target = _canonical_pair(gA, gB)
    ds_ids: set[str] = set()
    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            a = resolve_group(comp["groupA"], mappings)
            b = resolve_group(comp["groupB"], mappings)
            if _canonical_pair(a, b) == target:
                ds_ids.add(ds_name)
    return ds_ids


def _ev_item(
    action: str,
    result: dict,
    ds_ids: set,
    fdr: Optional[float],
    reasoning: str,
    orientation: str = "",
    enriched_up: list = None,
    enriched_down: list = None,
    genes_up: list = None,
    genes_down: list = None,
) -> dict:
    item: dict = {
        "step": 0,
        "action": action,
        "method_family": _METHOD_FAMILY.get(action, "other"),
        "dataset_ids": sorted(ds_ids),
        "n_datasets": len(ds_ids),
        "best_fdr": fdr,
        "reasoning": reasoning,
        "key_stats": {},
        "orientation": orientation,
    }
    if enriched_up is not None:
        item["enriched_up"] = enriched_up
    if enriched_down is not None:
        item["enriched_down"] = enriched_down
    if genes_up is not None:
        item["genes_up"] = genes_up
    if genes_down is not None:
        item["genes_down"] = genes_down
    return item


# ---------------------------------------------------------------------------
# Primary+orthogonal evaluators per question type
# ---------------------------------------------------------------------------

def _run_gsea(datasets, deg_datasets, mappings, gA, gB):
    """Safe meta_gsea call; returns (result, fdr, ds_ids)."""
    try:
        r = meta_gsea(datasets, groupA=gA, groupB=gB, mappings=mappings, deg_datasets=deg_datasets)
        if r.get("error"):
            return r, None, set()
        fdr = _gsea_fdr(r)
        ds_ids = set(r.get("contributing_datasets", [])) or _deg_ds_ids(deg_datasets, gA, gB, mappings)
        return r, fdr, ds_ids
    except Exception as e:
        logger.debug("meta_gsea(%s vs %s): %s", gA, gB, e)
        return {"error": str(e)}, None, set()


def _eval_floor(datasets, deg_datasets, mappings, gA, gB):
    """Pairwise floor: meta_gsea (enrichment) + deg_voting (deg_replication)."""
    r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, gA, gB)
    try:
        r_vote = deg_voting(datasets, groupA=gA, groupB=gB, mappings=mappings, deg_datasets=deg_datasets)
        ds_vote = _deg_ds_ids(deg_datasets, gA, gB, mappings)
    except Exception as e:
        r_vote, ds_vote = {"error": str(e)}, set()

    all_ds = ds_gsea | ds_vote
    families: set[str] = set()
    if not r_gsea.get("error"):
        families.add("enrichment")
    if not r_vote.get("error"):
        families.add("deg_replication")

    verdict, issues = _gate(families, all_ds, fdr_gsea)
    orient = f"{gA} vs {gB}"
    ev = []
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, f"meta-GSEA {gA} vs {gB}",
            orientation=orient,
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    if not r_vote.get("error"):
        ev.append(_ev_item(
            "deg_voting", r_vote, ds_vote, None, f"voting {gA} vs {gB}",
            orientation=orient,
            genes_up=[g.get("gene", "") for g in r_vote.get("top_genes", []) if g.get("direction") == "UP"],
            genes_down=[g.get("gene", "") for g in r_vote.get("top_genes", []) if g.get("direction") == "DOWN"],
        ))
    return verdict, ev, issues


def _eval_gradient(datasets, deg_datasets, mappings, groups_sorted, reference=None):
    """Gradient: network_meta_analysis + Spearman monotonic test + meta_gsea for top pair."""
    try:
        r_nma = network_meta_analysis(datasets, mappings=mappings, deg_datasets=deg_datasets)
    except Exception as e:
        return "uncertain", [], [f"network_meta_analysis failed: {e}"]
    if r_nma.get("error"):
        return "uncertain", [], [r_nma["error"]]

    # Collect dataset IDs (all DEG sources)
    nma_ds: set[str] = set(deg_datasets.keys())

    # Score groups by mean outgoing indirect logFC
    comparisons_out = r_nma.get("comparisons", [])
    scores: dict[str, list[float]] = {g: [] for g in groups_sorted}
    for cr in comparisons_out:
        top_up = cr.get("top_up", [])
        top_down = cr.get("top_down", [])
        all_genes = top_up + top_down
        if not all_genes:
            continue
        mean_lfc = float(np.mean([g.get("indirect_logFC", 0.0) for g in all_genes[:10]]))
        if cr["groupA"] in scores:
            scores[cr["groupA"]].append(mean_lfc)
        if cr["groupB"] in scores:
            scores[cr["groupB"]].append(-mean_lfc)

    scored = sorted(
        [(g, float(np.mean(v)) if v else 0.0) for g, v in scores.items()],
        key=lambda x: -x[1],
    )

    # Spearman rank correlation: if monotonic, groups are linearly ordered
    n = len(scored)
    rho, p_val, gradient_fdr = 0.0, 1.0, 1.0
    if n >= 3 and scored:
        from scipy.stats import spearmanr
        ranks_pos = list(range(n))
        vals = [s for _, s in scored]
        if max(vals) - min(vals) > 1e-6:
            rho, p_val = spearmanr(ranks_pos, vals)
            gradient_fdr = float(p_val)  # single test, no correction
        else:
            gradient_fdr = 1.0

    ordered_groups = [g for g, _ in scored]
    reasoning = (
        f"Gradient order: {' > '.join(ordered_groups[:6])} "
        f"(Spearman rho={rho:.2f}, p={p_val:.3f})"
    )

    # Orthogonal: meta_gsea for the pair with largest estimated contrast
    r_gsea, fdr_gsea, ds_gsea = {"error": "no top pair"}, None, set()
    if len(scored) >= 2:
        gA_top, gB_top = canonical_order(scored[0][0], scored[-1][0], reference)
        r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, gA_top, gB_top)
        nma_ds |= ds_gsea

    families: set[str] = {"network"}
    best_fdr: Optional[float] = gradient_fdr if gradient_fdr < 0.05 else None
    if not r_gsea.get("error"):
        families.add("enrichment")
        best_fdr = min(best_fdr or 1.0, fdr_gsea or 1.0) or None

    verdict, issues = _gate(families, nma_ds, best_fdr)
    top_orient = f"{gA_top} vs {gB_top}" if len(scored) >= 2 else ""
    ev = [_ev_item("network_meta_analysis", r_nma, nma_ds, gradient_fdr if gradient_fdr < 1.0 else None, reasoning)]
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, "enrichment for top gradient pair",
            orientation=top_orient,
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    return verdict, ev, issues


def _eval_shared_vs_unique(datasets, deg_datasets, mappings, a1, b1, a2, b2):
    """deg_direction_comparison (direction) + meta_gsea for compA (enrichment)."""
    try:
        r_dir = deg_direction_comparison(
            datasets, deg_datasets=deg_datasets, mappings=mappings,
            comparisonA_groupA=a1, comparisonA_groupB=b1,
            comparisonB_groupA=a2, comparisonB_groupB=b2,
        )
    except Exception as e:
        r_dir = {"error": str(e)}

    ds_dir = _deg_ds_ids(deg_datasets, a1, b1, mappings) | _deg_ds_ids(deg_datasets, a2, b2, mappings)
    r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, a1, b1)

    all_ds = ds_dir | ds_gsea
    families: set[str] = set()
    if not r_dir.get("error"):
        families.add("direction")
    if not r_gsea.get("error"):
        families.add("enrichment")

    verdict, issues = _gate(families, all_ds, fdr_gsea)
    ev = []
    if not r_dir.get("error"):
        ev.append(_ev_item("deg_direction_comparison", r_dir, ds_dir, None,
                           f"concordant/unique DE: {a1}v{b1} and {a2}v{b2}",
                           orientation=f"{a1} vs {b1} / {a2} vs {b2}"))
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, f"enrichment {a1} vs {b1}",
            orientation=f"{a1} vs {b1}",
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    return verdict, ev, issues


def _eval_biomarker(datasets, deg_datasets, mappings, gA, gB):
    """deg_biomarker_ranking (deg_replication) + meta_gsea (enrichment)."""
    try:
        r_bio = deg_biomarker_ranking(datasets, groupA=gA, groupB=gB, mappings=mappings, deg_datasets=deg_datasets)
    except Exception as e:
        r_bio = {"error": str(e)}

    ds_bio = _deg_ds_ids(deg_datasets, gA, gB, mappings)
    r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, gA, gB)

    all_ds = ds_bio | ds_gsea
    families: set[str] = set()
    if not r_bio.get("error"):
        families.add("deg_replication")
    if not r_gsea.get("error"):
        families.add("enrichment")

    orient = f"{gA} vs {gB}"
    verdict, issues = _gate(families, all_ds, fdr_gsea)
    ev = []
    if not r_bio.get("error"):
        ev.append(_ev_item(
            "deg_biomarker_ranking", r_bio, ds_bio, None, f"biomarker ranking {gA} vs {gB}",
            orientation=orient,
            genes_up=[g.get("gene", "") for g in r_bio.get("top_biomarkers", []) if g.get("direction") == "UP"],
            genes_down=[g.get("gene", "") for g in r_bio.get("top_biomarkers", []) if g.get("direction") == "DOWN"],
        ))
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, f"enrichment {gA} vs {gB}",
            orientation=orient,
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    return verdict, ev, issues


def _eval_hub(datasets, deg_datasets, mappings, gA, gB, deg_only, tool_params):
    """deg_cooccurrence_network (network) + meta_gsea (enrichment)."""
    if deg_only:
        try:
            r_hub = deg_cooccurrence_network(datasets, groupA=gA, groupB=gB, mappings=mappings, deg_datasets=deg_datasets)
        except Exception as e:
            r_hub = {"error": str(e)}
        hub_action = "deg_cooccurrence_network"
        ds_hub = _deg_ds_ids(deg_datasets, gA, gB, mappings) if gA and gB else set(deg_datasets.keys())
    else:
        from ..tools.single import gene_network_hub
        ds_name = tool_params.get("datasetName", "")
        try:
            r_hub = gene_network_hub(datasets, datasetName=ds_name, topN=20, mappings=mappings, deg_datasets=deg_datasets)
        except Exception as e:
            r_hub = {"error": str(e)}
        hub_action = "gene_network_hub"
        ds_hub = {ds_name} if ds_name else set()

    r_gsea, fdr_gsea, ds_gsea = ({"error": "no comparison"}, None, set())
    if gA and gB:
        r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, gA, gB)

    all_ds = ds_hub | ds_gsea
    families: set[str] = set()
    if not r_hub.get("error") and not r_hub.get("warning"):
        families.add(_METHOD_FAMILY.get(hub_action, "network"))
    if not r_gsea.get("error"):
        families.add("enrichment")

    orient = f"{gA} vs {gB}" if gA and gB else ""
    verdict, issues = _gate(families, all_ds, fdr_gsea)
    ev = []
    if not r_hub.get("error"):
        ev.append(_ev_item(hub_action, r_hub, ds_hub, None, f"hub genes {gA} vs {gB}", orientation=orient))
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, f"enrichment {gA} vs {gB}",
            orientation=orient,
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    return verdict, ev, issues


def _one_vs_rest_de(
    deg_datasets: dict, group: str, mappings: dict,
    adj_p_thr: float = 0.05, logfc_thr: float = 0.5,
) -> dict:
    """Genes consistently DE in `group` vs all other groups combined."""
    gene_votes: dict[str, dict] = {}
    n_comparisons = 0
    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            gA = resolve_group(comp["groupA"], mappings)
            gB = resolve_group(comp["groupB"], mappings)
            if group not in (gA, gB):
                continue
            direction_factor = 1 if gA == group else -1
            n_comparisons += 1
            df = comp["df"]
            sig = df[(df["adj_p"] < adj_p_thr) & (df["logFC"].abs() > logfc_thr)]
            for gene, row in sig.iterrows():
                if gene not in gene_votes:
                    gene_votes[gene] = {"up": 0, "down": 0, "datasets": []}
                eff = float(row["logFC"]) * direction_factor
                if eff > 0:
                    gene_votes[gene]["up"] += 1
                else:
                    gene_votes[gene]["down"] += 1
                gene_votes[gene]["datasets"].append(ds_name)

    if n_comparisons == 0:
        return {"error": f"No comparisons involving group '{group}'"}

    results = []
    for gene, v in gene_votes.items():
        total = v["up"] + v["down"]
        if total < 2:
            continue
        consistency = max(v["up"], v["down"]) / total
        results.append({
            "gene": gene,
            "n_datasets": total,
            "freq": round(total / n_comparisons, 3),
            "direction": "UP" if v["up"] >= v["down"] else "DOWN",
            "consistent": v["up"] == total or v["down"] == total,
            "consistency_score": round(consistency, 3),
            "datasets": v["datasets"],
        })

    results.sort(key=lambda x: (-x["n_datasets"], -x["consistency_score"]))
    top = results[:20]
    return {
        "n_comparisons": n_comparisons,
        "n_genes_any": len(results),
        "top_genes": top,
        "interpretation": (
            f"One-vs-rest for '{group}': {len(results)} specific genes across {n_comparisons} comparisons. "
            f"Top: {top[0]['gene']} ({top[0]['direction']}, {top[0]['n_datasets']}/{n_comparisons} datasets)"
            if top else f"No consistently specific genes for '{group}'."
        ),
    }


def _eval_specificity(datasets, deg_datasets, mappings, group, reference=None):
    """one_vs_rest_de (deg_replication) + meta_gsea for the most-sourced comparison (enrichment)."""
    r_ovr = _one_vs_rest_de(deg_datasets, group, mappings)
    ds_ovr: set[str] = set()
    for ds_name, ds in deg_datasets.items():
        for comp in ds["comparisons"]:
            gA = resolve_group(comp["groupA"], mappings)
            gB = resolve_group(comp["groupB"], mappings)
            if group in (gA, gB):
                ds_ovr.add(ds_name)

    # Find the most-sourced comparison involving this group for enrichment
    best_pair: Optional[tuple[str, str]] = None
    best_n = 0
    other_groups: set[str] = set()
    for ds in deg_datasets.values():
        for comp in ds["comparisons"]:
            gA = resolve_group(comp["groupA"], mappings)
            gB = resolve_group(comp["groupB"], mappings)
            if group not in (gA, gB):
                continue
            other = gB if gA == group else gA
            other_groups.add(other)
            n = len(_deg_ds_ids(deg_datasets, group, other, mappings))
            if n > best_n:
                best_n = n
                best_pair = (group, other)

    r_gsea, fdr_gsea, ds_gsea = {"error": "no comparison"}, None, set()
    gsea_orient = ""
    if best_pair:
        bp = canonical_order(best_pair[0], best_pair[1], reference)
        r_gsea, fdr_gsea, ds_gsea = _run_gsea(datasets, deg_datasets, mappings, bp[0], bp[1])
        gsea_orient = f"{bp[0]} vs {bp[1]}"

    all_ds = ds_ovr | ds_gsea
    families: set[str] = set()
    if not r_ovr.get("error") and r_ovr.get("n_genes_any", 0) > 0:
        families.add("deg_replication")
    if not r_gsea.get("error"):
        families.add("enrichment")

    verdict, issues = _gate(families, all_ds, fdr_gsea)
    ev = []
    if not r_ovr.get("error"):
        ev.append(_ev_item("deg_voting", r_ovr, ds_ovr, None, f"one-vs-rest specificity for '{group}'",
                           genes_up=[g.get("gene", "") for g in r_ovr.get("top_genes", []) if g.get("direction") == "UP"],
                           genes_down=[g.get("gene", "") for g in r_ovr.get("top_genes", []) if g.get("direction") == "DOWN"]))
    if not r_gsea.get("error"):
        ev.append(_ev_item(
            "meta_gsea", r_gsea, ds_gsea, fdr_gsea, f"enrichment {gsea_orient}",
            orientation=gsea_orient,
            enriched_up=[r.get("pathway", "") for r in r_gsea.get("top_enriched_up", [])],
            enriched_down=[r.get("pathway", "") for r in r_gsea.get("top_enriched_down", [])],
        ))
    return verdict, ev, issues


# ---------------------------------------------------------------------------
# Main engine entry point
# ---------------------------------------------------------------------------

def characterize(
    datasets: list,
    deg_datasets: dict,
    mappings: dict,
    deg_only: bool,
    hypotheses: list[dict],
    reference: str = None,
) -> dict[str, dict]:
    """
    Deterministic engine: evaluate all auto_gsea seeds and grid cells.

    Returns {hypothesis_id: {"status": str, "evidence": list, "reasoning": str}}
    for every hypothesis it handled. The runner applies these updates before
    starting the LLM loop.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}
    results: dict[str, dict] = {}

    # Collect all canonical groups (for gradient)
    all_groups = sorted({
        resolve_group(comp[k], mappings)
        for ds in deg_datasets.values()
        for comp in ds["comparisons"]
        for k in ("groupA", "groupB")
    })

    for hyp in hypotheses:
        hid = hyp["id"]
        seeded_by = hyp.get("seeded_by", "")
        qt = hyp.get("question_type", "")
        tp = hyp.get("tool_params", {})

        verdict = "uncertain"
        evidence: list[dict] = []
        issues: list[str] = []

        try:
            if seeded_by == "auto_gsea":
                comp = hyp.get("_comparison")
                if comp:
                    verdict, evidence, issues = _eval_floor(datasets, deg_datasets, mappings, comp[0], comp[1])
                else:
                    issues = ["auto_gsea seed missing _comparison field — skip"]

            elif seeded_by == "grid":
                if qt == "gradient":
                    verdict, evidence, issues = _eval_gradient(datasets, deg_datasets, mappings, all_groups, reference=reference)
                elif qt == "specificity":
                    verdict, evidence, issues = _eval_specificity(datasets, deg_datasets, mappings, tp.get("group", ""), reference=reference)
                elif qt == "shared_vs_unique":
                    verdict, evidence, issues = _eval_shared_vs_unique(
                        datasets, deg_datasets, mappings,
                        tp["comparisonA_groupA"], tp["comparisonA_groupB"],
                        tp["comparisonB_groupA"], tp["comparisonB_groupB"],
                    )
                elif qt == "biomarker":
                    verdict, evidence, issues = _eval_biomarker(
                        datasets, deg_datasets, mappings, tp["groupA"], tp["groupB"]
                    )
                elif qt == "hub":
                    gA = tp.get("groupA", tp.get("datasetName", ""))
                    gB = tp.get("groupB", "")
                    verdict, evidence, issues = _eval_hub(datasets, deg_datasets, mappings, gA, gB, deg_only, tp)
                else:
                    issues = [f"unknown question_type: {qt!r}"]

            else:
                continue  # skip non-engine hypotheses (auto, auto_cross, llm)

        except Exception as e:
            logger.error("Engine error for %s (%s/%s): %s", hid, seeded_by, qt, e, exc_info=True)
            issues = [f"engine exception: {e}"]
            verdict = "uncertain"

        reasoning = (
            "Engine: all gate criteria met."
            if not issues else
            f"Engine: gate issues — {'; '.join(issues)}."
        )
        results[hid] = {"status": verdict, "evidence": evidence, "reasoning": reasoning}
        logger.info(
            "Engine %-6s %-20s → %-9s %s",
            hid, qt or seeded_by, verdict,
            f"[{'; '.join(issues[:2])}]" if issues else "",
        )

    return results


def build_layer1_summary(hypotheses: list[dict]) -> str:
    """
    Build a compact text summary of all engine-evaluated S and G hypotheses.
    Injected into the LLM system prompt so Layer 2 has full context.
    """
    floor_lines: list[str] = []
    grid_lines: list[str] = []

    for h in hypotheses:
        sb = h.get("seeded_by", "")
        hid = h["id"]
        status = h.get("status", "pending").upper()
        short = h["text"][:90].replace("\n", " ")
        ev = h.get("evidence", [])
        best_fdr = min((e["best_fdr"] for e in ev if e.get("best_fdr") is not None), default=None)
        fdr_str = f", FDR={best_fdr:.3f}" if best_fdr is not None else ""
        n_ds = max((e.get("n_datasets", 0) for e in ev), default=0)
        ds_str = f", {n_ds}ds" if n_ds else ""
        line = f"  {hid} [{status}{fdr_str}{ds_str}]: {short}"
        if sb == "auto_gsea":
            floor_lines.append(line)
        elif sb == "grid":
            qt = h.get("question_type", "?")
            grid_lines.append(f"  {hid} [{status}, {qt}{fdr_str}{ds_str}]: {short}")

    parts: list[str] = ["LAYER 1 PRE-CHARACTERIZED RESULTS (deterministic — all S and G already evaluated):"]
    if floor_lines:
        parts.append("Floor (pairwise comparisons):")
        parts.extend(floor_lines)
    if grid_lines:
        parts.append("Grid (cross-cutting analyses):")
        parts.extend(grid_lines)
    if not floor_lines and not grid_lines:
        parts.append("  (no pre-characterized cells)")
    return "\n".join(parts)
