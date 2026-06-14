import asyncio
import json
import logging
import os
import re
from datetime import datetime
from typing import AsyncGenerator

import anthropic

logger = logging.getLogger(__name__)


def _repair_json(s: str) -> str:
    """Replace literal control characters inside JSON strings with proper escape sequences."""
    result = []
    in_string = False
    escape = False
    for char in s:
        if escape:
            result.append(char)
            escape = False
        elif char == "\\" and in_string:
            result.append(char)
            escape = True
        elif char == '"':
            result.append(char)
            in_string = not in_string
        elif in_string and char == "\n":
            result.append("\\n")
        elif in_string and char == "\r":
            result.append("\\r")
        elif in_string and char == "\t":
            result.append("\\t")
        else:
            result.append(char)
    return "".join(result)


def _extract_first_json_object(s: str):
    """
    Extract the first syntactically balanced JSON object from s.
    Unlike a greedy regex, this correctly handles nested braces and strings,
    and stops at the first complete top-level closing brace.
    """
    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i, char in enumerate(s[start:], start):
        if escape:
            escape = False
            continue
        if char == "\\" and in_string:
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None

from ..agent.system_prompt import build_system_prompt
from ..agent.seeder import generate_seeds, extract_evidence_stats
from ..agent.coverage import build_coverage_grid, K_OFF_GRID, _MAX_AUTO_RAISE
from ..agent.engine import characterize, build_layer1_summary
from ..agent.orient import detect_reference_group, canonical_order
from ..tools.registry import TOOLS, CROSS_TOOL_NAMES, DEG_TOOL_NAMES, summarize_result
from ..tools.sandbox import execute_sandbox

REPORTS_DIR = "reports"


def _write_report(datasets: list, seed_summary: str, seed_data: dict, steps: list, hypotheses: list, done_text: str) -> str:
    """Write a Markdown report of the agent run. Returns the file path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ds_names = "_".join(ds["name"].replace(" ", "-") for ds in datasets)
    path = os.path.join(REPORTS_DIR, f"run_{ts}_{ds_names}.md")

    lines = []
    lines.append(f"# Transcriptomic Agent Report")
    lines.append(f"\n**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    lines.append(f"**Datasets:** {', '.join(ds['name'] for ds in datasets)}  ")
    for ds in datasets:
        lines.append(f"- {ds['name']}: {len(ds['expr'].index)} genes, {len(ds['expr'].columns)} samples, groups: {', '.join(ds['groups'])}")

    # Pre-analysis
    lines.append("\n---\n## Pre-analysis\n")

    # Per-dataset DE results (MWU + BH)
    if seed_data.get("per_dataset_de"):
        lines.append("### Per-Dataset Differential Expression (MWU + BH)\n")
        for entry in seed_data["per_dataset_de"]:
            lines.append(f"**{entry['dataset']} — {entry['groupA']} vs {entry['groupB']}** ({entry['n_sig']} DE genes)\n")
            if entry.get("top_up"):
                lines.append(f"_Top upregulated in {entry['groupA']}:_")
                lines.append("| Gene | logFC | adj_p |")
                lines.append("|------|-------|-------|")
                for g in entry["top_up"]:
                    lines.append(f"| {g.get('gene','')} | {round(g.get('logFC',0),3)} | {round(g.get('adj_p',1),4)} |")
                lines.append("")
            if entry.get("top_down"):
                lines.append(f"_Top downregulated in {entry['groupA']}:_")
                lines.append("| Gene | logFC | adj_p |")
                lines.append("|------|-------|-------|")
                for g in entry["top_down"]:
                    lines.append(f"| {g.get('gene','')} | {round(g.get('logFC',0),3)} | {round(g.get('adj_p',1),4)} |")
                lines.append("")

    # Cross-dataset DE results
    if seed_data.get("cross_de"):
        lines.append("### Cross-Dataset Differential Expression\n")
        for de in seed_data["cross_de"]:
            lines.append(f"**{de['groupA']} vs {de['groupB']}** (genes tested: {de.get('n_tested', 'n/a')})\n")
            if de.get("top_up"):
                lines.append(f"_Consistently upregulated in {de['groupA']}:_")
                lines.append("| Gene | avg|logFC| | fisher_adj_p | n_datasets |")
                lines.append("|------|-----------|-------------|------------|")
                for g in de["top_up"]:
                    lines.append(f"| {g.get('gene','')} | {g.get('avg_abs_logFC','')} | {g.get('fisher_adj_p','')} | {g.get('n_datasets','')} |")
                lines.append("")
            if de.get("top_down"):
                lines.append(f"_Consistently downregulated in {de['groupA']}:_")
                lines.append("| Gene | avg|logFC| | fisher_adj_p | n_datasets |")
                lines.append("|------|-----------|-------------|------------|")
                for g in de["top_down"]:
                    lines.append(f"| {g.get('gene','')} | {g.get('avg_abs_logFC','')} | {g.get('fisher_adj_p','')} | {g.get('n_datasets','')} |")
                lines.append("")
            if de.get("interpretation"):
                lines.append(f"_{de['interpretation']}_\n")

    # Seed hypotheses summary
    lines.append("### Seed Hypotheses Generated\n")
    if seed_summary:
        lines.append(f"```\n{seed_summary}\n```")
    else:
        lines.append("_No common groups across datasets — no seed hypotheses._")

    # Steps
    lines.append("\n---\n## Agent Steps\n")
    for s in steps:
        lines.append(f"### Step {s['step']}")
        if s.get("thought"):
            lines.append(f"\n**Thought:** {s['thought']}\n")
        if s.get("action"):
            lines.append(f"**Action:** `{s['action']}`")
            if s.get("params"):
                param_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in s["params"].items() if k != "code")
                if param_str:
                    lines.append(f"  Parameters: {param_str}")
            if s.get("code"):
                lines.append(f"\n```python\n{s['code']}\n```")
        if s.get("blocked"):
            lines.append(f"\n**Blocked:** _{s['blocked']}_\n")
        if s.get("summary"):
            lines.append(f"\n**Result:** {s['summary']}\n")
        if s.get("error"):
            lines.append(f"\n**Error:** {s['error']}\n")
        if s.get("hypo_eval"):
            h = s["hypo_eval"]
            lines.append(f"\n**Hypothesis {h['id']} → {h['verdict'].upper()}:** {h['reasoning']}\n")

    # Hypotheses
    lines.append("\n---\n## Hypotheses\n")
    if hypotheses:
        for h in hypotheses:
            status_icon = {"confirmed": "✓", "rejected": "✗", "uncertain": "?", "pending": "○"}.get(h["status"], "○")
            lines.append(f"### {h['id']} [{status_icon} {h['status'].upper()}]")
            lines.append(f"\n{h['text']}\n")
            if h.get("evidence"):
                for ev in h["evidence"]:
                    lines.append(f"- Step {ev['step']} [`{ev['action']}`]: {ev['reasoning']}")
            lines.append("")
    else:
        lines.append("_No hypotheses proposed._")

    # Conclusion
    lines.append("\n---\n## Conclusion\n")
    lines.append(done_text if done_text else "_Agent did not produce a final summary._")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Report written: %s", path)
    return path


# ── Evidence gating helpers ──────────────────────────────────────────────────

# Method family mapping — multiple calls in the same family count as ONE for convergence.
# Two meta_gsea calls with different collection_prefix = 1 family (enrichment_ranked), not 2.
_METHOD_FAMILY: dict = {
    "meta_gsea":                "enrichment",   # preranked GSEA on DE signal
    "gsea_enrichment":          "enrichment",   # per-file preranked GSEA — same family as meta_gsea
    "pathway_enrichment":       "enrichment",   # hypergeometric ORA on DE signal — same family
    "deg_voting":               "deg_replication",
    "deg_biomarker_ranking":    "deg_replication",
    "cross_dataset_de":         "fisher_meta",
    "invariant_axis":           "deg_replication",
    "differential_expression":  "deg_replication",
    "network_meta_analysis":    "network",
    "cross_dataset_rewiring":   "network",
    "gene_network_hub":         "network",
    "deg_cooccurrence_network": "network",
    "deg_direction_comparison": "direction",
    "subgroup_discovery":       "subgroup",
    "execute_code":             "custom",
}

# All three enrichment tools (meta_gsea / gsea_enrichment / pathway_enrichment) test the same
# DE signal and are collapsed into ONE family "enrichment". Any combination of them alone
# counts as a single family (len < 2) and cannot satisfy convergence.
_ENRICHMENT_FAMILIES: frozenset = frozenset({"enrichment"})
_ORTHOGONAL_FAMILIES: frozenset = frozenset({
    "deg_replication", "fisher_meta", "network", "direction", "subgroup", "custom",
})


def _extract_orientation_signed(action: str, result: dict, params: dict = None) -> dict:
    """
    Return {"orientation": "X vs Y", "enriched_up": [...], "enriched_down": [...],
            "genes_up": [...], "genes_down": [...]} for direction-consistency checks.

    Pulls signed-statistic-direction lists from supported tool results. Missing fields
    are returned as empty so the direction check simply finds nothing to compare against.
    """
    params = params or {}
    out: dict = {"orientation": "", "enriched_up": [], "enriched_down": [], "genes_up": [], "genes_down": []}
    if not isinstance(result, dict) or result.get("error"):
        return out

    orientation = result.get("orientation", "")
    if not orientation:
        gA, gB = params.get("groupA"), params.get("groupB")
        if gA and gB:
            orientation = f"{gA} vs {gB}"
    out["orientation"] = orientation

    if action in ("meta_gsea", "gsea_enrichment"):
        out["enriched_up"]   = [r.get("pathway", "") for r in result.get("top_enriched_up",   [])]
        out["enriched_down"] = [r.get("pathway", "") for r in result.get("top_enriched_down", [])]

    elif action == "pathway_enrichment":
        # ORA returns top_enriched without signed direction — skip for direction check
        pass

    elif action == "deg_voting":
        out["genes_up"]   = [g.get("gene", "") for g in result.get("top_genes", []) if g.get("direction") == "UP"]
        out["genes_down"] = [g.get("gene", "") for g in result.get("top_genes", []) if g.get("direction") == "DOWN"]

    elif action == "deg_biomarker_ranking":
        out["genes_up"]   = [g.get("gene", "") for g in result.get("top_biomarkers", []) if g.get("direction") == "UP"]
        out["genes_down"] = [g.get("gene", "") for g in result.get("top_biomarkers", []) if g.get("direction") == "DOWN"]

    elif action == "cross_dataset_de":
        out["genes_up"]   = [g.get("gene", "") for g in result.get("top_consistent_up",   [])]
        out["genes_down"] = [g.get("gene", "") for g in result.get("top_consistent_down", [])]

    elif action == "differential_expression":
        out["genes_up"]   = [g.get("gene", "") for g in result.get("top_upregulated",   [])]
        out["genes_down"] = [g.get("gene", "") for g in result.get("top_downregulated", [])]

    return out


def _extract_evidence_meta(action: str, result: dict,
                            params: dict = None, deg_datasets: dict = None) -> tuple:
    """
    Return (dataset_ids: set[str], best_fdr: float|None).

    dataset_ids is the set of underlying dataset/file identifiers that produced this result.
    The union of dataset_ids across all evidence items must have size ≥2 for replication.
    """
    params = params or {}
    deg_datasets = deg_datasets or {}
    ds_ids: set = set()
    best_fdr = None

    if not isinstance(result, dict) or result.get("error"):
        return ds_ids, best_fdr

    if action == "meta_gsea":
        # contributing_datasets is now returned by meta_gsea (list of actual dataset names)
        names = result.get("contributing_datasets", [])
        if names:
            ds_ids = set(names)
        else:
            # Fallback: use a comparison-keyed sentinel if the field is absent (old result)
            ds_ids = {f"_meta_{result.get('comparison', '?')}_{result.get('n_datasets_pooled', 1)}"}
        fdrs = [r.get("fdr", 1.0) for r in result.get("top_enriched_up", []) + result.get("top_enriched_down", [])]
        best_fdr = float(min(fdrs)) if fdrs else None

    elif action == "gsea_enrichment":
        deg_name = params.get("deg_dataset_name")
        ds_ids = {deg_name} if deg_name else {"_gsea_unnamed"}
        ps = [r.get("adj_p", 1.0) for r in result.get("top_enriched_up", []) + result.get("top_enriched_down", [])]
        best_fdr = float(min(ps)) if ps else None

    elif action == "pathway_enrichment":
        deg_name = params.get("deg_dataset_name")
        if deg_name:
            ds_ids = {deg_name}
        else:
            # ORA on a custom gene list — tie to no specific dataset (sentinel, not counted)
            ds_ids = {"_ora_gene_list"}
        ps = [r.get("adj_p", 1.0) for r in result.get("top_enriched", [])]
        best_fdr = float(min(ps)) if ps else None

    elif action == "cross_dataset_de":
        used = result.get("datasets_used", [])
        ds_ids = set(used) if used else {"_cde_unnamed"}
        fps = [r.get("fisher_adj_p", 1.0) for r in result.get("top_consistent_up", []) + result.get("top_consistent_down", [])]
        best_fdr = float(min(fps)) if fps else None

    elif action in ("deg_voting", "deg_biomarker_ranking", "deg_cooccurrence_network"):
        gA, gB = params.get("groupA"), params.get("groupB")
        if gA and gB and deg_datasets:
            matching = [
                ds_name for ds_name, ds in deg_datasets.items()
                for comp in ds["comparisons"]
                if {comp["groupA"], comp["groupB"]} == {gA, gB}
            ]
            ds_ids = set(matching) if matching else {f"_deg_{gA}_{gB}"}
        else:
            ds_ids = set(deg_datasets.keys()) or {"_deg_unknown"}

    elif action == "invariant_axis":
        n_ds = int(result.get("n_datasets", 1))
        ds_ids = {f"_inv_raw_{i}" for i in range(n_ds)}
        bps = [g.get("p_bootstrap", 1.0) for g in result.get("top_invariant_genes", [])[:5]]
        best_fdr = float(min(bps)) if bps else None

    elif action == "differential_expression":
        ds_name = result.get("dataset", "_de_unnamed")
        ds_ids = {ds_name}
        top = result.get("top_upregulated", []) + result.get("top_downregulated", [])
        ps = [g.get("adj_p") for g in top if g.get("adj_p") is not None]
        best_fdr = float(min(ps)) if ps else None

    elif action == "network_meta_analysis":
        n_edges = int(result.get("n_direct_edges", 1))
        ds_ids = {f"_nma_edge_{i}" for i in range(n_edges)}

    else:
        ds_ids = {"_unknown"}

    return ds_ids, best_fdr


def _check_confirmed_gate(hypothesis: dict) -> tuple:
    """
    Return (can_confirm, issues).
    Requires:
      1. ≥2 distinct method families with at least one from the orthogonal group
         (meta_gsea + gsea_enrichment + pathway_enrichment all map to "enrichment" — ONE family)
      2. Union of distinct underlying dataset IDs across all evidence ≥ 2
      3. best FDR < 0.05 from at least one evidence item
    """
    evidence = hypothesis.get("evidence", [])
    families = {e.get("method_family") for e in evidence if e.get("method_family")}
    # Union of all underlying dataset names across every evidence item
    all_ds: set = set()
    for e in evidence:
        all_ds.update(e.get("dataset_ids", []))
    n_distinct = len(all_ds)
    fdrs = [e["best_fdr"] for e in evidence if e.get("best_fdr") is not None]
    best = min(fdrs) if fdrs else 1.0
    issues = []

    # Convergence: ≥2 families AND at least one must be orthogonal
    if len(families) < 2:
        names = ", ".join(sorted(families)) or "none"
        issues.append(
            f"convergence: only 1 method family ({names}); need ≥2 distinct families. "
            f"Two meta_gsea calls with different collection_prefix = still ONE family."
        )
    else:
        has_orthogonal = bool(families & _ORTHOGONAL_FAMILIES)
        if not has_orthogonal:
            issues.append(
                f"convergence: families present ({', '.join(sorted(families))}) are all enrichment-group "
                f"(meta_gsea / gsea_enrichment / pathway_enrichment all test the same DE signal). "
                f"Need ≥1 orthogonal method: deg_replication, fisher_meta, network, or direction."
            )

    # Replication: union of REAL dataset IDs ≥ 2 (filter virtual sentinels that don't map to files)
    _VIRTUAL = frozenset({"_ora_gene_list", "_gsea_unnamed", "_unknown"})
    real_ds = all_ds - _VIRTUAL
    n_distinct = len(real_ds)
    if n_distinct < 2:
        ds_str = ", ".join(sorted(real_ds)) or "none"
        issues.append(
            f"replication: only {n_distinct} distinct underlying dataset(s) ({ds_str}); "
            f"need ≥2 independent datasets. Running multiple tools on the same dataset does NOT count. "
            f"pathway_enrichment on a gene list (no deg_dataset_name) does not add replication credit."
        )

    if best >= 0.05:
        fdr_str = f"{best:.4f}" if fdrs else "not recorded"
        issues.append(f"significance: best FDR={fdr_str}; need FDR<0.05 from at least one method")

    return (not issues), issues


def _check_rejected_gate(hypothesis: dict) -> tuple:
    """Return (can_reject, issues). Requires ≥1 significant result or ≥2 pieces of evidence."""
    evidence = hypothesis.get("evidence", [])
    if not evidence:
        return False, ["no evidence collected; mark uncertain or gather evidence first"]
    fdrs = [e["best_fdr"] for e in evidence if e.get("best_fdr") is not None]
    if (fdrs and min(fdrs) < 0.05) or len(evidence) >= 2:
        return True, []
    fdr_str = f"{min(fdrs):.4f}" if fdrs else "not recorded"
    return False, [
        f"insufficient evidence for rejection (best FDR={fdr_str}, n_evidence=1); "
        "need FDR<0.05 or ≥2 evidence items — mark uncertain instead"
    ]


def _check_direction_consistency(hypothesis: dict, direction_claims: list) -> list[str]:
    """
    Verify each direction_claim against the signed statistics stored in evidence items.

    Each claim: {"item": "PATHWAY_OR_GENE", "direction": "UP"|"DOWN", "in_group": "group"}
    Evidence items carry "orientation" ("X vs Y"), "enriched_up"/"enriched_down" (pathways),
    and "genes_up"/"genes_down" (genes).

    Returns a list of human-readable mismatch descriptions (empty = all consistent).
    """
    issues: list[str] = []
    for claim in direction_claims:
        item = (claim.get("item") or "").strip().upper()
        claimed_dir = (claim.get("direction") or "").strip().upper()
        in_group = (claim.get("in_group") or "").strip()
        if not item or claimed_dir not in ("UP", "DOWN") or not in_group:
            continue

        for ev in hypothesis.get("evidence", []):
            orientation = ev.get("orientation", "")
            if not orientation or " vs " not in orientation:
                continue
            parts = orientation.split(" vs ", 1)
            groupA, groupB = parts[0].strip(), parts[1].strip()

            if in_group.upper() == groupA.upper():
                in_groupA = True
            elif in_group.upper() == groupB.upper():
                in_groupA = False
            else:
                continue  # this evidence item doesn't cover the target group

            up_set   = {x.strip().upper() for x in ev.get("enriched_up",   ev.get("genes_up",   []))}
            down_set = {x.strip().upper() for x in ev.get("enriched_down", ev.get("genes_down", []))}

            if item in up_set:
                # Item UP in groupA: UP in groupA, DOWN in groupB
                actual_dir = "UP" if in_groupA else "DOWN"
                if actual_dir != claimed_dir:
                    issues.append(
                        f"Direction mismatch for '{item}': claimed {claimed_dir} in {in_group}, "
                        f"but signed statistic shows UP in {groupA} → "
                        f"{'UP' if in_groupA else 'DOWN'} in {in_group} "
                        f"(orientation: {groupA} vs {groupB}). "
                        f"Correct: '{item}' is UP in {groupA}, DOWN in {groupB}."
                    )
            elif item in down_set:
                # Item DOWN in groupA: DOWN in groupA, UP in groupB
                actual_dir = "DOWN" if in_groupA else "UP"
                if actual_dir != claimed_dir:
                    issues.append(
                        f"Direction mismatch for '{item}': claimed {claimed_dir} in {in_group}, "
                        f"but signed statistic shows DOWN in {groupA} → "
                        f"{'DOWN' if in_groupA else 'UP'} in {in_group} "
                        f"(orientation: {groupA} vs {groupB}). "
                        f"Correct: '{item}' is DOWN in {groupA}, UP in {groupB}."
                    )
    return issues


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    u = len(a | b)
    return len(a & b) / u if u > 0 else 0.0


def _is_novel(new_genes: list, resolved: list, threshold: float = 0.5) -> bool:
    """True if new_genes is sufficiently distinct from every resolved hypothesis's gene set."""
    new_set = {g.upper() for g in new_genes}
    if not new_set:
        return True
    for h in resolved:
        existing = {g.upper() for g in h.get("genes", [])}
        if existing and _jaccard(new_set, existing) >= threshold:
            return False
    return True


async def run_agent_loop(
    datasets: list,
    max_hypotheses: int,
    api_key: str,
    temperature: float = 0.0,
    mappings: dict = None,
    deg_datasets: dict = None,
) -> AsyncGenerator[dict, None]:
    """
    Async generator — yields log event dicts.
    Consumed by FastAPI StreamingResponse.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}
    client = anthropic.AsyncAnthropic(api_key=api_key)

    all_genes = [set(ds["expr"].index) for ds in datasets]
    common_genes = all_genes[0].intersection(*all_genes[1:]) if len(all_genes) > 1 else all_genes[0] if all_genes else set()

    # ── Pre-analysis seeding ──────────────────────────────────────────────────
    loop = asyncio.get_event_loop()
    _deg_only = len(datasets) == 0 and bool(deg_datasets)
    # Detect canonical reference group once (most-common groupB across DEG tables)
    _reference_group = detect_reference_group(deg_datasets, mappings)
    if _reference_group:
        logger.info("Canonical reference group detected: '%s'", _reference_group)
    seeds, seed_summary, seed_data = await loop.run_in_executor(
        None, lambda: generate_seeds(datasets, mappings=mappings, deg_datasets=deg_datasets, reference=_reference_group)
    )
    # Build deterministic coverage grid (G1, G2, ...)
    grid_hypotheses = build_coverage_grid(datasets, deg_datasets, mappings, _deg_only, reference=_reference_group)
    n_auto_gsea = sum(1 for s in seeds if s.get("seeded_by") == "auto_gsea")
    n_grid = len(grid_hypotheses)
    # Auto-raise budget: floor + grid + off-grid headroom, capped at _MAX_AUTO_RAISE
    min_budget = n_auto_gsea + n_grid + K_OFF_GRID
    orig_max = max_hypotheses
    max_hypotheses = min(max(max_hypotheses, min_budget), _MAX_AUTO_RAISE)
    max_steps = max_hypotheses * 5  # safety cap: generous budget per hypothesis

    # ── Layer 1: run characterization engine (deterministic, no LLM) ─────────
    hypotheses: list[dict] = list(seeds) + list(grid_hypotheses)  # S…, G…; H… appended during loop
    yield {"type": "mode", "mode": "reproduce" if temperature == 0.0 else "explore", "temperature": temperature}
    if max_hypotheses != orig_max:
        yield {"type": "seed", "text": (
            f"Budget auto-raised from {orig_max} to {max_hypotheses} "
            f"({n_auto_gsea} floor + {n_grid} grid + {K_OFF_GRID} off-grid)."
        ), "summary": ""}
    yield {"type": "seed", "text": "Layer 1: running characterization engine (deterministic)…", "summary": ""}
    engine_results = await loop.run_in_executor(
        None, lambda: characterize(datasets, deg_datasets, mappings, _deg_only, hypotheses, reference=_reference_group)
    )
    # Apply engine verdicts to hypothesis list
    for hyp in hypotheses:
        if hyp["id"] in engine_results:
            res = engine_results[hyp["id"]]
            hyp["status"] = res["status"]
            hyp["evidence"] = list(res["evidence"])
    layer1_summary = build_layer1_summary(hypotheses)
    n_confirmed_l1 = sum(1 for h in hypotheses if h.get("status") == "confirmed" and h.get("seeded_by") in ("auto_gsea", "grid"))
    n_uncertain_l1 = sum(1 for h in hypotheses if h.get("status") == "uncertain" and h.get("seeded_by") in ("auto_gsea", "grid"))
    yield {"type": "seed", "text": (
        f"Layer 1 complete: {n_confirmed_l1} CONFIRMED, {n_uncertain_l1} UNCERTAIN "
        f"across {n_auto_gsea + n_grid} cells."
    ), "summary": layer1_summary}

    # Yield hypothesis proposals with engine verdicts already applied
    yield {"type": "seed", "text": f"Pre-analysis: {len(seeds)} seed hypotheses + {n_grid} grid cells generated", "summary": seed_summary}
    for s in seeds:
        yield {"type": "hypothesis_propose", "hypothesis": dict(s)}
    for g in grid_hypotheses:
        yield {"type": "hypothesis_propose", "hypothesis": dict(g)}
    # Emit hypothesis_eval events so the frontend renders the engine verdicts
    for hyp in hypotheses:
        if hyp.get("seeded_by") in ("auto_gsea", "grid") and hyp["status"] != "pending":
            yield {"type": "hypothesis_eval", "hypothesis": dict(hyp), "reasoning": "Layer 1 engine"}

    # Build system prompt with Layer 1 context for the LLM
    system_prompt = build_system_prompt(
        datasets, len(common_genes),
        seed_summary=seed_summary, deg_datasets=deg_datasets,
        max_hypotheses=max_hypotheses, k_off_grid=K_OFF_GRID,
        layer1_summary=layer1_summary,
        reference_group=_reference_group,
    )
    if mappings:
        mapping_text = "\n".join(
            f"  '{canonical}' = {aliases}"
            for canonical, aliases in mappings.items()
        )
        system_prompt += f"\n\nGROUP MAPPINGS (use these canonical names in cross-dataset tools):\n{mapping_text}"

    messages = []
    discoveries = []
    hypo_counter = 0                    # agent-proposed: H1, H2, ...
    report_steps: list[dict] = []       # collected for final report
    last_call: tuple = None             # (action, params_json) of previous step
    once_only_called: set = set()       # tools that may only be called once per run
    total_cost_usd: float = 0.0         # accumulated API cost for this run
    post_grid_evidence: set = set()     # hypothesis IDs with ≥1 evidence added after grid covered
    pi_notebook: dict | None = None     # latest PI notebook from the AI (current_understanding / open_questions / next_action)
    # Off-grid novelty tracking: reinstated for Layer 2 H-proposals
    # Layer 2 explores until 3 consecutive H-proposals are novel:false → off_grid_exhausted
    from collections import deque as _deque
    off_grid_novelty_window: _deque = _deque(maxlen=3)
    _ONCE_ONLY = {"cross_dataset_de"}   # tools restricted to a single call per run
    _DEG_ONLY_ALLOWED = {"cross_dataset_de", "pathway_enrichment", "execute_code", "DONE"} | DEG_TOOL_NAMES

    for i in range(max_steps):
        step_num = i + 1
        is_last = step_num == max_steps

        # ── PI notebook block (the AI's own working state, rendered back each step) ──
        if pi_notebook is None:
            notebook_block = (
                "PI NOTEBOOK (your working state — empty, this is your first step):\n"
                "  current_understanding: (none yet — draft after reading the Layer 1 summary)\n"
                "  open_questions: (none yet)\n"
                "  next_action: (none yet — declare it in this step)\n"
            )
        else:
            _cu = (pi_notebook.get("current_understanding") or "").strip() or "(empty)"
            _oq = pi_notebook.get("open_questions") or []
            if isinstance(_oq, list) and _oq:
                _oq_lines = []
                for i, item in enumerate(_oq[:8], 1):
                    if isinstance(item, dict):
                        q = (item.get("q") or "").strip()
                        why = (item.get("why") or "").strip()
                        _oq_lines.append(f"    {i}. {q} — why: {why}")
                    else:
                        _oq_lines.append(f"    {i}. {str(item)[:160]}")
                _oq_str = "\n".join(_oq_lines)
            else:
                _oq_str = "    (none — if this persists, you may finalize)"
            _na = pi_notebook.get("next_action") or {}
            _choice = (_na.get("choice") if isinstance(_na, dict) else None) or "(unspecified)"
            _rat = (_na.get("rationale") if isinstance(_na, dict) else "") or ""
            notebook_block = (
                "PI NOTEBOOK (your last working state — REWRITE it this step):\n"
                f"  current_understanding: {_cu}\n"
                f"  open_questions:\n{_oq_str}\n"
                f"  last next_action: choice={_choice}; rationale={_rat}\n"
            )

        discovery_summary = (
            "Discoveries:\n" + "\n".join(f"- [{d['action']}] {d['summary']}" for d in discoveries[-8:])
            if discoveries else "First step."
        )
        # Build hypothesis display: show all PENDING in full; condensed for evaluated
        _pending_h = [h for h in hypotheses if h["status"] == "pending"]
        _eval_h    = [h for h in hypotheses if h["status"] != "pending"]
        hypo_lines = []
        for h in _pending_h:
            ev = len(h.get("evidence", []))
            short = h["text"][:80] + ("…" if len(h["text"]) > 80 else "")
            ev_tag = f", {ev}ev" if ev else ""
            if h.get("seeded_by") == "grid":
                qt_tag = f" [grid:{h.get('question_type','?')}→{h.get('tool','?')}]"
            else:
                qt_tag = ""
            hypo_lines.append(f"  {h['id']} [PENDING{ev_tag}]{qt_tag}: {short}")
        # Show last 12 evaluated in condensed form to limit context
        _show_eval = _eval_h[-12:]
        if len(_eval_h) > 12:
            hypo_lines.append(f"  … {len(_eval_h) - 12} earlier evaluated hypotheses not shown …")
        for h in _show_eval:
            ev = len(h.get("evidence", []))
            ev_tag = f", {ev}ev" if ev else ""
            hypo_lines.append(f"  {h['id']} [{h['status'].upper()}{ev_tag}]")
        hypo_summary = (
            "\nHYPOTHESES (use these exact IDs — never invent IDs):\n" + "\n".join(hypo_lines)
            if hypo_lines else ""
        )

        summary_block = f"{notebook_block}\n{discovery_summary}{hypo_summary}"
        evaluated = sum(1 for h in hypotheses if h["status"] != "pending")
        # Grid coverage: all G-hypotheses evaluated (empty grid → True)
        _gc = not any(h["status"] == "pending" for h in hypotheses if h.get("seeded_by") == "grid")
        _no_pending = not any(h["status"] == "pending" for h in hypotheses)
        _uncertain_now = {h["id"] for h in hypotheses if h["status"] == "uncertain"}
        _all_corroborated = _uncertain_now.issubset(post_grid_evidence)
        _next_grid = next(
            (h for h in hypotheses if h.get("seeded_by") == "grid" and h["status"] == "pending"),
            None,
        )
        _floor_seeds_done = not any(
            h["status"] == "pending"
            for h in hypotheses if h.get("seeded_by") == "auto_gsea"
        )

        if is_last:
            user_content = (
                f"Step {step_num} [{evaluated}/{max_hypotheses} hypotheses evaluated]. {summary_block}\n\n"
                "FINAL STEP — safety limit reached. Evaluate any remaining hypotheses as uncertain and call DONE."
            )
        elif _no_pending and (_gc and _all_corroborated or evaluated >= max_hypotheses):
            user_content = (
                f"Step {step_num} [{evaluated}/{max_hypotheses} hypotheses evaluated — TARGET REACHED]. {summary_block}\n\n"
                "You have evaluated all required hypotheses. Write a comprehensive final summary as the thought field — "
                "cover each hypothesis verdict with key evidence and statistics, the most important genes and their expression patterns, "
                "key pathways and mechanisms identified, and an overall biological conclusion. Then call DONE."
            )
        elif _gc:
            # Grid covered — corroboration mode (off-grid H-proposals still allowed)
            _off_grid_n = sum(1 for h in hypotheses if h.get("seeded_by") == "llm")
            _off_grid_rem = max(0, K_OFF_GRID - _off_grid_n)
            _pending_ids = [h["id"] for h in hypotheses if h["status"] == "pending"]
            _uncorroborated = sorted(_uncertain_now - post_grid_evidence)
            _msg_parts = [f"GRID COVERED ({n_grid}/{n_grid} cells done). Corroboration mode."]
            if _off_grid_rem > 0 and not _pending_ids:
                _msg_parts.append(
                    f"Off-grid budget: {_off_grid_n}/{K_OFF_GRID} proposals used; "
                    f"you may propose up to {_off_grid_rem} more genuinely novel hypotheses "
                    f"not covered by any grid cell."
                )
            if _pending_ids:
                _msg_parts.append(
                    f"Pending hypotheses (never evaluated): {_pending_ids}. "
                    "Gather evidence and evaluate each to confirmed/uncertain/rejected."
                )
            if _uncorroborated:
                _msg_parts.append(
                    f"Uncertain hypotheses needing corroboration: {_uncorroborated}. "
                    "For each: add the missing orthogonal method family or a second dataset replication. "
                    "If genuinely impossible to upgrade, make one attempt — "
                    "the attempt itself unblocks DONE even if the verdict stays uncertain."
                )
            if not _pending_ids and not _uncorroborated:
                _msg_parts.append(
                    "All hypotheses resolved and corroborated. Write your final summary and call DONE."
                )
            user_content = (
                f"Step {step_num} [{evaluated}/{max_hypotheses} hypotheses evaluated — GRID COVERED]. "
                f"{summary_block}\n\n" + " ".join(_msg_parts)
            )
        elif _next_grid is not None and _floor_seeds_done:
            # Floor seeds done; guide agent to next grid cell
            tp = _next_grid.get("tool_params", {})
            params_str = (
                ", ".join(f"{k}={repr(v)}" for k, v in sorted(tp.items()))
                if tp else "(no params)"
            )
            n_done_grid = sum(
                1 for h in hypotheses
                if h.get("seeded_by") == "grid" and h["status"] != "pending"
            )
            grid_hint = (
                f"GRID CELL {_next_grid['id']} ({n_done_grid}/{n_grid} done) — "
                f"question_type={_next_grid.get('question_type','?')}: "
                f"use {_next_grid.get('tool','?')}({params_str}) and evaluate {_next_grid['id']}."
            )
            user_content = (
                f"Step {step_num} [{evaluated}/{max_hypotheses} hypotheses evaluated]. "
                f"{summary_block}\n\n{grid_hint}"
            )
        else:
            user_content = f"Step {step_num} [{evaluated}/{max_hypotheses} hypotheses evaluated]. {summary_block}\n\nWhat will you investigate?"

        messages.append({"role": "user", "content": user_content})

        yield {"type": "thinking", "text": f"Agent thinking... ({evaluated}/{max_hypotheses} hypotheses evaluated)"}

        # Apply prompt caching: clear all existing marks, then mark last 3 cacheable messages.
        # System prompt uses 1 of 4 allowed cache_control slots, leaving 3 for messages.
        # Marks must be cleared each step because they accumulate in-place across iterations.
        for msg in messages:
            if isinstance(msg["content"], list):
                for block in msg["content"]:
                    block.pop("cache_control", None)
        for msg in messages[:-2][-3:]:
            if isinstance(msg["content"], list):
                msg["content"][-1]["cache_control"] = {"type": "ephemeral"}
            elif isinstance(msg["content"], str):
                msg["content"] = [{"type": "text", "text": msg["content"], "cache_control": {"type": "ephemeral"}}]

        raw = ""
        _step_usage = None
        try:
            async with client.messages.stream(
                model="claude-opus-4-8",
                max_tokens=16000,
                temperature=temperature,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
            ) as stream:
                chunk_buf = ""
                last_flush = asyncio.get_event_loop().time()
                async for text in stream.text_stream:
                    raw += text
                    chunk_buf += text
                    now = asyncio.get_event_loop().time()
                    if len(chunk_buf) >= 40 or (now - last_flush) >= 0.12:
                        yield {"type": "thought_stream", "delta": chunk_buf}
                        chunk_buf = ""
                        last_flush = now
                if chunk_buf:
                    yield {"type": "thought_stream", "delta": chunk_buf}
                try:
                    _step_usage = (await stream.get_final_message()).usage
                except Exception:
                    pass
        except Exception as e:
            logger.error("API error at step %d: %s", step_num, e, exc_info=True)
            yield {"type": "error", "text": f"API error: {e}"}
            return

        if _step_usage is not None:
            _in  = _step_usage.input_tokens
            _out = _step_usage.output_tokens
            _cw  = getattr(_step_usage, "cache_creation_input_tokens", 0) or 0
            _cr  = getattr(_step_usage, "cache_read_input_tokens", 0) or 0
            # claude-opus-4-8 pricing: $5/1M input, $25/1M output, $6.25/1M cache-write, $0.50/1M cache-read
            step_cost = _in * 5e-6 + _out * 25e-6 + _cw * 6.25e-6 + _cr * 0.5e-6
            total_cost_usd += step_cost
            yield {
                "type": "usage",
                "step": step_num,
                "input_tokens": _in,
                "output_tokens": _out,
                "cache_creation_tokens": _cw,
                "cache_read_tokens": _cr,
                "step_cost_usd": round(step_cost, 6),
                "total_cost_usd": round(total_cost_usd, 6),
            }

        m = _extract_first_json_object(_repair_json(raw))
        try:
            dec = json.loads(m if m else raw)
        except json.JSONDecodeError:
            logger.error("JSON parse error at step %d: %s", step_num, raw[:200])
            yield {"type": "error", "text": f"JSON parse error: {raw[:200]}"}
            messages.append({"role": "assistant", "content": raw})
            continue

        thought = dec.get("thought", "")
        action = dec.get("action", "")
        params = dec.get("params", {})
        hypo_action = dec.get("hypothesis_action")
        # Persist PI notebook if the AI wrote one this step. The notebook drives next-step rendering.
        _nb = dec.get("notebook")
        if isinstance(_nb, dict):
            pi_notebook = _nb

        # Guard: reject tools that may only be called once per run
        if action in _ONCE_ONLY and action in once_only_called:
            logger.warning("Once-only tool [%s] called again at step %d — blocking", action, step_num)
            report_steps.append({"step": step_num, "thought": thought, "action": action, "params": params,
                                  "blocked": f"'{action}' may only be called once per run — blocked"})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": (
                f"CRITICAL ERROR: '{action}' may only be called once per run and has already been called. "
                "Use a different tool to continue the analysis."
            )})
            continue

        # Guard: reject identical tool call repeated from the previous step
        current_call = (action, json.dumps(params, sort_keys=True, default=str))
        if action not in ("DONE", "hypothesis_action") and current_call == last_call:
            logger.warning("Duplicate tool call [%s] at step %d — forcing agent to advance", action, step_num)
            report_steps.append({"step": step_num, "thought": thought, "action": action, "params": params,
                                  "blocked": f"Duplicate call to '{action}' with identical parameters — blocked"})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": (
                f"CRITICAL ERROR: You just called '{action}' with identical parameters as the previous step. "
                "This is not allowed. You MUST choose a different tool or different parameters."
            )})
            continue

        # Process propose BEFORE tool call
        if isinstance(hypo_action, dict) and hypo_action.get("type") == "propose" and hypo_action.get("text"):
            hypo_counter += 1
            new_genes = hypo_action.get("genes", [])
            agent_novel = bool(hypo_action.get("novel", True))
            redundant_of = hypo_action.get("redundant_of", [])
            h = {
                "id": f"H{hypo_counter}",
                "text": hypo_action["text"],
                "genes": new_genes,
                "status": "pending",
                "evidence": [],
                "proposed_at": step_num,
                "seeded_by": "llm",
                "novel": agent_novel,
                "redundant_of": redundant_of,
            }
            hypotheses.append(h)
            yield {"type": "hypothesis_propose", "hypothesis": dict(h)}
            # Track novelty for off-grid (H-prefix) proposals only — drives Layer 2 termination
            agent_novel = bool(hypo_action.get("novel", True))
            resolved_so_far = [x for x in hypotheses[:-1] if x["status"] != "pending"]
            gene_set_novel = _is_novel(new_genes, resolved_so_far)
            off_grid_novelty_window.append(agent_novel and gene_set_novel)

        loop = asyncio.get_event_loop()

        if action == "DONE":
            evaluated = sum(1 for h in hypotheses if h["status"] != "pending")
            # floor+grid: all pre-evaluated by Layer 1 engine, so floor_done=True always
            floor_and_grid = [h for h in hypotheses if h.get("seeded_by") in ("auto_gsea", "grid")]
            floor_done = all(h["status"] != "pending" for h in floor_and_grid)
            no_pending = not any(h["status"] == "pending" for h in hypotheses)
            uncertain_at_done = {h["id"] for h in hypotheses if h["status"] == "uncertain"}
            all_corroborated = uncertain_at_done.issubset(post_grid_evidence)
            # Off-grid novelty exhausted = 3 consecutive novel:false H-proposals
            off_grid_exhausted = len(off_grid_novelty_window) >= 3 and not any(off_grid_novelty_window)
            # DONE: floor+grid done, no pending, AND (budget met OR off-grid exhausted+corroborated)
            can_done = is_last or (
                floor_done and no_pending and (
                    evaluated >= max_hypotheses or
                    (off_grid_exhausted and all_corroborated)
                )
            )
            if not can_done:
                pending_all = [h["id"] for h in hypotheses if h["status"] == "pending"]
                pending_grid = [h["id"] for h in hypotheses if h.get("seeded_by") == "grid" and h["status"] == "pending"]
                logger.warning(
                    "DONE blocked at step %d: floor_done=%s no_pending=%s off_grid_exhausted=%s "
                    "all_corroborated=%s eval=%d/%d",
                    step_num, floor_done, no_pending, off_grid_exhausted, all_corroborated,
                    evaluated, max_hypotheses,
                )
                if not floor_done:
                    # Shouldn't happen after engine, but handle gracefully
                    pending_engine = [h["id"] for h in floor_and_grid if h["status"] == "pending"]
                    detail = (
                        f"Floor/grid cells still pending: {pending_engine}. "
                        f"(These should have been pre-evaluated by Layer 1 — investigate.)"
                    )
                elif not no_pending:
                    detail = (
                        f"H-hypotheses still PENDING (never evaluated): {pending_all}. "
                        f"Gather evidence and evaluate each before calling DONE."
                    )
                elif not all_corroborated:
                    uncorroborated = sorted(uncertain_at_done - post_grid_evidence)
                    remaining = max_hypotheses - evaluated
                    detail = (
                        f"Corroboration required for UNCERTAIN hypotheses: {uncorroborated}. "
                        f"Gather at least one new evidence item for each — try an orthogonal method or "
                        f"a second dataset. Hypothesis may stay UNCERTAIN; the attempt unblocks DONE. "
                        f"({remaining} budget slots remain. Off-grid novelty window: {list(off_grid_novelty_window)}.)"
                    )
                else:
                    remaining = max_hypotheses - evaluated
                    detail = (
                        f"Need {remaining} more evaluated H-hypotheses, or signal off-grid novelty "
                        f"exhaustion: propose 3 consecutive H-hypotheses with novel:false. "
                        f"(Current off-grid window: {list(off_grid_novelty_window)}.)"
                    )
                report_steps.append({"step": step_num, "thought": thought, "action": "DONE", "params": {},
                                     "blocked": f"DONE blocked: {detail}"})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"ERROR: Cannot call DONE yet. {detail}"})
                continue
            yield {"type": "done", "text": thought}
            report_path = await loop.run_in_executor(
                None, _write_report, datasets, seed_summary, seed_data, report_steps, hypotheses, thought
            )
            yield {"type": "report", "path": report_path}
            return

        # Guard: model sometimes puts "hypothesis_action" in the action field by mistake
        if action == "hypothesis_action":
            logger.warning("Agent used 'hypothesis_action' as action at step %d — skipping tool call", step_num)
            report_steps.append({"step": step_num, "thought": thought, "action": action, "params": params,
                                  "blocked": "'hypothesis_action' used as action field — blocked (not a valid tool name)"})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "ERROR: 'hypothesis_action' is not a valid tool name. The 'action' field must be a tool name like differential_expression, execute_code, etc. The 'hypothesis_action' is a separate JSON field. Please retry with a valid tool."})
            continue

        if thought:
            yield {"type": "thought", "text": thought}
        await asyncio.sleep(0)  # flush thought before running tool

        # Guard: DEG-only mode — block tools that require raw expression data
        if _deg_only and action not in _DEG_ONLY_ALLOWED:
            logger.warning("DEG-only mode: blocked tool [%s] at step %d", action, step_num)
            report_steps.append({"step": step_num, "thought": thought, "action": action, "params": params,
                                  "blocked": f"DEG-only mode: '{action}' requires raw expression data — blocked"})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": (
                f"ERROR: No raw expression datasets are loaded. "
                f"Only cross_dataset_de and pathway_enrichment are available in DEG-only mode. "
                f"'{action}' requires a raw expression matrix and cannot be used."
            )})
            continue

        result = None
        if action == "execute_code":
            code = params.get("code", "").strip()
            if not code:
                logger.warning("execute_code at step %d: empty code parameter", step_num)
                yield {"type": "error", "text": "execute_code: missing code parameter"}
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": "ERROR: execute_code requires a non-empty 'code' parameter. Please provide the Python code to execute."})
                continue
            yield {"type": "code", "code": code}
            result = await loop.run_in_executor(None, execute_sandbox, code, datasets, deg_datasets)
            summary = f"ERROR: {result['error']}" if isinstance(result, dict) and result.get("error") else f"Code executed: {str(result)[:80]}"
            discoveries.append({"action": action, "params": params, "summary": summary, "result": result})
            yield {"type": "result", "action": action, "params": params, "result": result, "summary": summary, "isCross": False, "isDynamic": True}
        elif action in TOOLS:
            try:
                tool_fn = TOOLS[action]
                result = await loop.run_in_executor(None, lambda: tool_fn(datasets, mappings=mappings, deg_datasets=deg_datasets, **params))
                summary = summarize_result(action, result)
                discoveries.append({"action": action, "params": params, "summary": summary, "result": result})
                yield {
                    "type": "result", "action": action, "params": params, "result": result,
                    "summary": summary,
                    "isCross": action in CROSS_TOOL_NAMES,
                    "isDeg": action in DEG_TOOL_NAMES,
                    "isDynamic": False,
                }
            except Exception as e:
                logger.error("Tool error [%s] at step %d: %s", action, step_num, e, exc_info=True)
                result = {"error": str(e)}
                yield {"type": "error", "text": f"{action}: {e}"}
        else:
            logger.error("Unknown tool [%s] at step %d", action, step_num)
            result = {"error": f"Unknown tool: {action}"}
            yield {"type": "error", "text": f"Unknown tool: {action}"}

        # Process evaluate AFTER tool call
        _eval_correction = None
        if isinstance(hypo_action, dict) and hypo_action.get("type") == "evaluate" and hypo_action.get("hypothesis_id"):
            hid = hypo_action["hypothesis_id"]
            h = next((x for x in hypotheses if x["id"] == hid), None)

            if h is None:
                if hypo_action.get("text"):
                    # Auto-register as new pending hypothesis; do NOT apply the verdict yet
                    hypo_counter += 1
                    new_id = f"H{hypo_counter}"
                    new_genes = hypo_action.get("genes", [])
                    h_new = {
                        "id": new_id, "text": hypo_action["text"], "genes": new_genes,
                        "status": "pending", "evidence": [], "proposed_at": step_num, "seeded_by": "llm",
                    }
                    hypotheses.append(h_new)
                    yield {"type": "hypothesis_propose", "hypothesis": dict(h_new)}
                    logger.info("Auto-registered unknown id %s as %s at step %d", hid, new_id, step_num)
                    _eval_correction = (
                        f"NOTICE: hypothesis_id '{hid}' was not found. Your text was registered as "
                        f"new hypothesis {new_id} (PENDING). Gather evidence and evaluate {new_id} "
                        f"in a future step — it has NOT been marked with your requested verdict."
                    )
                    h = None  # don't process the verdict on the newly registered hypothesis
                else:
                    valid_ids = [x["id"] for x in hypotheses]
                    yield {"type": "error", "text": f"evaluate: unknown hypothesis_id '{hid}'; valid: {valid_ids}"}
                    logger.warning("Unknown hypothesis id '%s' at step %d, no text to register", hid, step_num)
                    _eval_correction = (
                        f"ERROR: hypothesis_id '{hid}' not found. Valid IDs: {valid_ids}. "
                        f"Propose it first with a 'propose' action (and get its assigned id), "
                        f"then evaluate that id in a subsequent step."
                    )

            if h is not None:
                # Attach structured evidence: dataset_ids is the set of underlying sources
                ds_ids, best_fdr = _extract_evidence_meta(action, result or {}, params=params, deg_datasets=deg_datasets)
                _orient = _extract_orientation_signed(action, result or {}, params=params)
                ev_item = {
                    "step": step_num,
                    "action": action,
                    "method_family": _METHOD_FAMILY.get(action, "other"),
                    "dataset_ids": sorted(ds_ids),   # list for JSON-serialisability; union used in gate
                    "n_datasets": len(ds_ids),        # kept for display
                    "best_fdr": best_fdr,
                    "reasoning": hypo_action.get("reasoning", ""),
                    "key_stats": extract_evidence_stats(action, result or {}, h.get("genes", [])),
                    "orientation":   _orient["orientation"],
                    "enriched_up":   _orient["enriched_up"],
                    "enriched_down": _orient["enriched_down"],
                    "genes_up":      _orient["genes_up"],
                    "genes_down":    _orient["genes_down"],
                }
                h["evidence"].append(ev_item)
                # Post-grid corroboration tracking
                _gc_now = not any(
                    x["status"] == "pending"
                    for x in hypotheses if x.get("seeded_by") == "grid"
                )
                if _gc_now:
                    post_grid_evidence.add(h["id"])
                # Warn when agent uses a different tool than the grid cell suggests
                if h.get("seeded_by") == "grid" and action != h.get("tool", action):
                    logger.warning(
                        "Grid cell %s suggests tool '%s' but agent used '%s' at step %d",
                        h["id"], h.get("tool"), action, step_num,
                    )
                    yield {
                        "type": "error",
                        "text": (
                            f"Note: grid cell {h['id']} suggests tool '{h.get('tool')}' "
                            f"but you used '{action}'. The evidence is recorded; "
                            f"consider using the suggested tool for richer evidence."
                        ),
                    }

                # Gate the verdict
                verdict = hypo_action.get("verdict", "uncertain")
                if verdict not in ("confirmed", "rejected", "uncertain"):
                    verdict = "uncertain"
                if verdict == "confirmed":
                    ok, issues = _check_confirmed_gate(h)
                    if ok:
                        # Direction-consistency check: any claimed direction must match signed stats
                        dir_claims = hypo_action.get("direction_claims", []) or []
                        dir_issues = _check_direction_consistency(h, dir_claims)
                        if dir_issues:
                            verdict = "uncertain"
                            _eval_correction = (
                                f"WARNING: {hid} verdict downgraded confirmed → uncertain due to "
                                f"DIRECTION mismatch with signed statistics. "
                                + " | ".join(dir_issues)
                                + " Restate the direction correctly (UP/DOWN in the right group "
                                + "under the canonical orientation) and re-evaluate."
                            )
                    else:
                        verdict = "uncertain"
                        _eval_correction = (
                            f"WARNING: {hid} verdict downgraded confirmed → uncertain. "
                            f"Gate not met: {'; '.join(issues)}. "
                            f"Add evidence from a second orthogonal method before re-evaluating."
                        )
                elif verdict == "rejected":
                    ok, issues = _check_rejected_gate(h)
                    if not ok:
                        verdict = "uncertain"
                        _eval_correction = (
                            f"WARNING: {hid} verdict downgraded rejected → uncertain. "
                            f"{'; '.join(issues)}."
                        )

                h["status"] = verdict
                yield {
                    "type": "hypothesis_eval",
                    "hypothesis": dict(h),
                    "reasoning": hypo_action.get("reasoning", ""),
                }

        # Collect step for report
        step_record: dict = {"step": step_num, "thought": thought, "action": action, "params": params}
        if action == "execute_code":
            step_record["code"] = params.get("code", "")
        if result is not None:
            step_record["summary"] = summarize_result(action, result) if action in TOOLS else (
                f"ERROR: {result.get('error')}" if isinstance(result, dict) and result.get("error") else str(result)[:120]
            )
            if isinstance(result, dict) and result.get("error"):
                step_record["error"] = result["error"]
        if isinstance(hypo_action, dict) and hypo_action.get("type") == "evaluate":
            step_record["hypo_eval"] = {
                "id": hypo_action.get("hypothesis_id", ""),
                "verdict": hypo_action.get("verdict", "uncertain"),
                "reasoning": hypo_action.get("reasoning", ""),
            }
        report_steps.append(step_record)
        last_call = current_call
        if action in _ONCE_ONLY:
            once_only_called.add(action)

        messages.append({"role": "assistant", "content": raw})
        result_str = json.dumps(result, default=str)[:2500] if result is not None else "null"
        user_result_msg = f"Result of {action}:\n{result_str}"
        if _eval_correction:
            user_result_msg += f"\n\n{_eval_correction}"
        messages.append({"role": "user", "content": user_result_msg})

    # Loop exhausted without DONE — write report with what we have
    evaluated = sum(1 for h in hypotheses if h["status"] != "pending")
    done_text = f"Safety step limit reached ({max_steps} steps). {evaluated}/{max_hypotheses} hypotheses evaluated."
    yield {"type": "done", "text": done_text, "exhausted": True}
    report_path = await loop.run_in_executor(
        None, _write_report, datasets, seed_summary, seed_data, report_steps, hypotheses, done_text
    )
    yield {"type": "report", "path": report_path}
