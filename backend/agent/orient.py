"""
Canonical comparison orientation utilities.

All tool calls for a given group pair should use the SAME (groupA, groupB) order so
signed statistics (NES, logFC) have a consistent meaning throughout the analysis.

Convention:
  - If a reference group is known: (non-reference, reference).
    Positive NES / logFC > 0 then means HIGHER IN THE NON-REFERENCE GROUP.
  - Fallback when no reference or neither input is the reference: alphabetical (min, max).

The same input pair always maps to the same output regardless of input order.
Disease-agnostic: the reference is detected from DEG table metadata (most-common groupB),
not from biology keywords.
"""
from __future__ import annotations

from typing import Optional


def detect_reference_group(deg_datasets: dict, mappings: dict) -> Optional[str]:
    """
    Identify the reference (control / baseline) group from DEG table metadata.

    Heuristic: the group most frequently appearing as groupB across all DEG comparisons
    is the reference — researchers conventionally write "treatment vs control", placing the
    control second.

    Returns None when deg_datasets is empty or there is no clear majority.
    """
    from ..tools.cross import resolve_group

    mappings = mappings or {}
    counts: dict[str, int] = {}
    for ds in (deg_datasets or {}).values():
        for comp in ds["comparisons"]:
            gB = resolve_group(comp["groupB"], mappings)
            counts[gB] = counts.get(gB, 0) + 1
    if not counts:
        return None
    max_count = max(counts.values())
    # Alphabetical tie-break for determinism
    candidates = sorted(g for g, c in counts.items() if c == max_count)
    return candidates[0] if candidates else None


def canonical_order(gA: str, gB: str, reference: Optional[str] = None) -> tuple[str, str]:
    """
    Return (groupA, groupB) in canonical orientation.

    Rules (applied in order):
      1. If reference is known and exactly one input equals the reference:
         → (non-reference, reference).  Positive = UP in the non-reference group.
      2. If both inputs are the reference (shouldn't happen) or no reference is known:
         → alphabetical (min, max).

    Property: canonical_order(a, b, ref) == canonical_order(b, a, ref) for all inputs.
    """
    if reference is not None:
        if gA == reference and gB != reference:
            return (gB, gA)     # flip — non-reference first
        if gB == reference:
            return (gA, gB)     # already correct — non-reference first
    # Alphabetical fallback
    return (min(gA, gB), max(gA, gB))


def orientation_note(gA: str, gB: str) -> str:
    """
    Short annotation appended to tool outputs to make the orientation unambiguous.
    '[orientation: X vs Y; NES>0/logFC>0 = higher in X]'
    """
    return f"[orientation: {gA} vs {gB}; NES>0/logFC>0 = higher in {gA}]"
