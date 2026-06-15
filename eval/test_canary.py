"""
Canary tests: confirm the regression harness actually catches direction flips.

This is the acceptance check from the tier-1 prompt — ``pytest eval/`` must FAIL
if a direction is intentionally flipped. We deepcopy the fixture, multiply
``logFC`` (and CI bounds, when present) by -1 for a single comparison, run
``meta_gsea`` on the mutated store, and assert the previously-confirmed
direction is now wrong.

If these canaries themselves stop catching the flip — they shouldn't until the
gate logic is gutted — the suite no longer guards against regressions and
something is wrong upstream. They are fast and run on every commit.
"""
from __future__ import annotations

import copy

import pytest

from eval.conftest import _ensure_gmt
_ensure_gmt()

from backend.tools.cross import meta_gsea


OE = "Ovarian endometriosis"
EH = "Healthy endometrium"


def _flip_direction(deg_store: dict, gA: str, gB: str) -> dict:
    """Return a deepcopy of deg_store with every logFC for the (gA,gB)
    comparison sign-flipped — simulates a direction-flip regression."""
    flipped = copy.deepcopy(deg_store)
    n_touched = 0
    for ds in flipped.values():
        for comp in ds["comparisons"]:
            if {comp["groupA"], comp["groupB"]} == {gA, gB}:
                df = comp["df"]
                df["logFC"] = -df["logFC"]
                for c in ("ci_l", "ci_r"):
                    if c in df.columns:
                        df[c] = -df[c]
                n_touched += 1
    assert n_touched > 0, f"No comparisons matched {gA} vs {gB} — fixture mis-loaded"
    return flipped


def _nes_for(result, pathway):
    for entry in result.get("top_enriched_up", []) + result.get("top_enriched_down", []):
        if entry["pathway"] == pathway:
            return float(entry["nes"])
    return None


def test_canary_flipped_complement_now_down(deg_store, mappings, gmt_file):
    """Sign-flip all OE-vs-EH logFCs in the fixture. HALLMARK_COMPLEMENT must
    now point DOWN (the wrong direction) — proves the harness would catch a
    regression that flipped the sign in ``meta_rank`` or upstream."""
    flipped = _flip_direction(deg_store, OE, EH)
    r = meta_gsea(datasets=[], deg_datasets=flipped, groupA=OE, groupB=EH,
                  mappings=mappings, collection_prefix="HALLMARK_", topN=50)
    assert "error" not in r, r.get("error")
    nes = _nes_for(r, "HALLMARK_COMPLEMENT")
    assert nes is not None
    assert nes < 0, (
        "Canary failed: even after flipping logFCs, HALLMARK_COMPLEMENT still "
        f"reads UP (NES={nes}). The harness is no longer direction-sensitive."
    )


def test_canary_flipped_proliferation_now_up(deg_store, mappings, gmt_file):
    """After the flip, E2F_TARGETS / G2M_CHECKPOINT must read UP in OE vs EH —
    the opposite of the established truth."""
    flipped = _flip_direction(deg_store, OE, EH)
    r = meta_gsea(datasets=[], deg_datasets=flipped, groupA=OE, groupB=EH,
                  mappings=mappings, collection_prefix="HALLMARK_", topN=50)
    assert "error" not in r, r.get("error")
    for pathway in ("HALLMARK_E2F_TARGETS", "HALLMARK_G2M_CHECKPOINT"):
        nes = _nes_for(r, pathway)
        assert nes is not None
        assert nes > 0, (
            f"Canary failed: after flipping logFCs, {pathway} still reads DOWN "
            f"(NES={nes}). The harness no longer catches direction regressions."
        )
