"""
Deterministic coverage grid: enumerates (question_type × group_config) cells,
pruned to applicable + tool-addressable cells only. Purely generic — no biology
hardcoded. The grid is identical for the same input data across runs.
"""
from __future__ import annotations

import itertools

from ..tools.cross import resolve_group
from .orient import canonical_order

# Off-grid budget: agent-proposed H-hypotheses allowed after grid is covered
# Layer 2 explores until novelty exhausted (3 consecutive novel:false), up to this cap
K_OFF_GRID: int = 15
# Hard cap on grid cells — prevents balloon for large many-group datasets
_MAX_GRID_CELLS: int = 20
# Safety ceiling on auto-raised max_hypotheses
_MAX_AUTO_RAISE: int = 80


def _canonical_pair(a: str, b: str) -> tuple[str, str]:
    return (min(a, b), max(a, b))


def _deg_source_count(deg_datasets: dict, gA: str, gB: str, mappings: dict) -> int:
    """Count DEG files whose comparison is gA vs gB in either direction."""
    target = _canonical_pair(gA, gB)
    n = 0
    for ds in deg_datasets.values():
        for comp in ds["comparisons"]:
            rA = resolve_group(comp["groupA"], mappings)
            rB = resolve_group(comp["groupB"], mappings)
            if _canonical_pair(rA, rB) == target:
                n += 1
    return n


def build_coverage_grid(
    datasets: list,
    deg_datasets: dict,
    mappings: dict,
    deg_only: bool,
    max_cells: int = _MAX_GRID_CELLS,
    reference: str = None,
) -> list[dict]:
    """
    Return a deterministic, pruned, capped list of grid-cell hypothesis dicts.

    Each dict has the same shape as a seeder hypothesis, plus:
      question_type, tool, tool_params

    IDs are G1, G2, ... in stable priority order, identical across runs for
    the same input data.
    """
    mappings = mappings or {}
    deg_datasets = deg_datasets or {}

    # ── Collect canonical groups and pairwise comparison pairs ─────────────
    groups: set[str] = set()
    pairs: set[tuple[str, str]] = set()

    for ds in datasets:
        gc = ds.get("group_col", "")
        meta = ds.get("meta")
        if gc and meta is not None and gc in meta.columns:
            ds_groups = sorted({
                resolve_group(str(g), mappings)
                for g in meta[gc].dropna().unique()
            })
            groups.update(ds_groups)
            for a, b in itertools.combinations(ds_groups, 2):
                pairs.add(_canonical_pair(a, b))

    for dset in deg_datasets.values():
        for comp in dset["comparisons"]:
            a = resolve_group(comp["groupA"], mappings)
            b = resolve_group(comp["groupB"], mappings)
            groups.add(a)
            groups.add(b)
            pairs.add(_canonical_pair(a, b))

    if not groups:
        return []

    groups_sorted = sorted(groups)
    pairs_sorted = sorted(pairs)

    raw: list[dict] = []  # list of cell descriptors before conversion

    # ── Priority 1: gradient ──────────────────────────────────────────────
    # One cell using network_meta_analysis (no params = all indirect pairs).
    # Requires ≥3 groups so at least one indirect path exists.
    if len(groups_sorted) >= 3:
        groups_display = ", ".join(groups_sorted[:5])
        if len(groups_sorted) > 5:
            groups_display += f" … (+{len(groups_sorted) - 5} more)"
        raw.append({
            "priority": 1,
            "sort_key": "0",
            "question_type": "gradient",
            "tool": "network_meta_analysis",
            "tool_params": {},
            "text": (
                f"Across {len(groups_sorted)} groups ({groups_display}), effect sizes "
                f"along pairwise comparisons may form a monotonic gradient — "
                f"indirect cross-comparison meta-analysis reveals the ordering."
            ),
        })

    # ── Priority 2: specificity (one-vs-rest) ────────────────────────────────
    # For each group G appearing in ≥2 canonical pairs, test what is specific to G
    # vs all other groups. Engine implements via _one_vs_rest_de + meta_gsea.
    for g in groups_sorted:
        comps_g = sorted([p for p in pairs_sorted if g in p])
        if len(comps_g) < 2:
            continue
        other_groups = sorted({h for p in comps_g for h in p if h != g})
        raw.append({
            "priority": 2,
            "sort_key": g,
            "question_type": "specificity",
            "tool": "one_vs_rest",
            "tool_params": {"group": g},
            "text": (
                f"Group {g} has a specific transcriptomic signature distinct from all "
                f"other groups ({', '.join(other_groups[:4])}"
                + (f" ... +{len(other_groups)-4} more" if len(other_groups) > 4 else "")
                + f") across {len(comps_g)} comparisons."
            ),
        })

    # ── Priority 3: shared_vs_unique ──────────────────────────────────────
    # For each group G that appears in ≥2 canonical pairs, compare its first
    # two comparisons (sorted → deterministic) via deg_direction_comparison.
    group_to_pairs: dict[str, list[tuple]] = {}
    for (a, b) in pairs_sorted:
        group_to_pairs.setdefault(a, []).append((a, b))
        group_to_pairs.setdefault(b, []).append((a, b))

    seen_svu: set[frozenset] = set()
    for g in groups_sorted:
        comps = sorted(group_to_pairs.get(g, []))
        if len(comps) < 2:
            continue
        c1, c2 = comps[0], comps[1]
        key: frozenset = frozenset([c1, c2])
        if key in seen_svu:
            continue
        seen_svu.add(key)
        a1, b1 = canonical_order(c1[0], c1[1], reference)
        a2, b2 = canonical_order(c2[0], c2[1], reference)
        raw.append({
            "priority": 3,
            "sort_key": f"{a1}|{b1}|{a2}|{b2}",
            "question_type": "shared_vs_unique",
            "tool": "deg_direction_comparison",
            "tool_params": {
                "comparisonA_groupA": a1,
                "comparisonA_groupB": b1,
                "comparisonB_groupA": a2,
                "comparisonB_groupB": b2,
            },
            "text": (
                f"Comparisons {a1} vs {b1} and {a2} vs {b2} both involve group {g}: "
                f"characterising concordant vs unique DE programs reveals what is "
                f"{g}-specific biology vs comparison-specific noise."
            ),
        })

    # ── Priority 3: biomarker ─────────────────────────────────────────────
    # One deg_biomarker_ranking cell per comparison pair with ≥1 source.
    for (a, b) in pairs_sorted:
        n_deg = _deg_source_count(deg_datasets, a, b, mappings)
        n_raw = sum(
            1 for ds in datasets
            if (gc := ds.get("group_col", ""))
            and (meta := ds.get("meta")) is not None
            and gc in meta.columns
            and {a, b}.issubset({
                resolve_group(str(g), mappings)
                for g in meta[gc].dropna().unique()
            })
        )
        n_total = n_deg + n_raw
        if n_total == 0:
            continue
        ca, cb = canonical_order(a, b, reference)
        raw.append({
            "priority": 4,
            "sort_key": f"{a}|{b}",
            "question_type": "biomarker",
            "tool": "deg_biomarker_ranking",
            "tool_params": {"groupA": ca, "groupB": cb},
            "text": (
                f"A composite biomarker ranking for {ca} vs {cb} — weighting frequency, "
                f"direction consistency, effect size, and significance across "
                f"{n_total} source(s) — identifies the most reproducible candidate markers."
            ),
        })

    # ── Priority 4: hub ───────────────────────────────────────────────────
    if deg_only:
        # deg_cooccurrence_network: comparison-specific, needs ≥3 DEG source files
        for (a, b) in pairs_sorted:
            n_deg = _deg_source_count(deg_datasets, a, b, mappings)
            if n_deg < 3:
                continue
            ha, hb = canonical_order(a, b, reference)
            raw.append({
                "priority": 5,
                "sort_key": f"{a}|{b}",
                "question_type": "hub",
                "tool": "deg_cooccurrence_network",
                "tool_params": {"groupA": ha, "groupB": hb},
                "text": (
                    f"Co-occurrence hub genes in the {ha} vs {hb} DE network are the "
                    f"most consistently co-DE nodes across {n_deg} source(s)."
                ),
            })
    else:
        # gene_network_hub: per dataset (not comparison-specific); needs ≥30 samples
        for ds in sorted(datasets, key=lambda d: d["name"]):
            meta = ds.get("meta")
            if meta is None or len(meta) < 30:
                continue
            raw.append({
                "priority": 5,
                "sort_key": ds["name"],
                "question_type": "hub",
                "tool": "gene_network_hub",
                "tool_params": {"datasetName": ds["name"], "topN": 20},
                "text": (
                    f"The {ds['name']} dataset has co-expression hub genes — "
                    f"central nodes in its genome-wide co-expression network."
                ),
            })

    # ── Priority 5: subtype (raw-expression only) ─────────────────────────
    if not deg_only and datasets:
        for ds in sorted(datasets, key=lambda d: d["name"]):
            gc = ds.get("group_col", "")
            meta = ds.get("meta")
            if not gc or meta is None or gc not in meta.columns or len(meta) < 30:
                continue
            for raw_g in sorted({str(g) for g in meta[gc].dropna().unique()}):
                raw.append({
                    "priority": 6,
                    "sort_key": f"{ds['name']}|{raw_g}",
                    "question_type": "subtype",
                    "tool": "subgroup_discovery",
                    "tool_params": {"datasetName": ds["name"], "group": raw_g},
                    "text": (
                        f"The {raw_g} group in {ds['name']} may contain transcriptionally "
                        f"distinct subtypes detectable by unsupervised clustering."
                    ),
                })

    # ── Sort by (priority, sort_key), cap, convert to hypothesis dicts ─────
    raw.sort(key=lambda c: (c["priority"], c["sort_key"]))
    raw = raw[:max_cells]

    grid: list[dict] = []
    for i, cell in enumerate(raw, start=1):
        grid.append({
            "id": f"G{i}",
            "text": cell["text"],
            "status": "pending",
            "evidence": [],
            "proposed_at": 0,
            "seeded_by": "grid",
            "genes": [],
            "question_type": cell["question_type"],
            "tool": cell["tool"],
            "tool_params": cell["tool_params"],
        })

    return grid
