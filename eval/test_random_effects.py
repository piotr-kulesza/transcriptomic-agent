"""
Unit + integration tests for the DerSimonian-Laird random-effects pooling
added in Tier-1 Fix 2.

Two layers:

1. ``_dersimonian_laird`` — direct numerical checks against the canonical
   metafor / Borenstein worked example.
2. ``cross_dataset_de`` integration — confirm RE pooled effects, heterogeneity
   (I², Q p-value), and a high-heterogeneity flag are reported when DEG
   fixtures carry SE/CI columns.
"""
from __future__ import annotations

import numpy as np
import pytest

from eval.conftest import _ensure_gmt
_ensure_gmt()

from backend.tools.cross import _dersimonian_laird, cross_dataset_de


OE = "Ovarian endometriosis"
EH = "Healthy endometrium"


def test_dl_zero_heterogeneity_collapses_to_fixed_effect():
    """Two studies with identical effects → tau²=0, I²=0, pooled = common effect."""
    out = _dersimonian_laird(
        effects=np.array([1.0, 1.0, 1.0]),
        variances=np.array([0.04, 0.04, 0.04]),
    )
    assert out["n_studies"] == 3
    assert out["tau2"] == pytest.approx(0.0, abs=1e-9)
    assert out["i2"] == pytest.approx(0.0, abs=1e-9)
    assert out["pooled_effect"] == pytest.approx(1.0, rel=1e-6)
    # SE under fixed-effect for k studies with equal variance v: sqrt(v / k).
    assert out["pooled_se"] == pytest.approx(np.sqrt(0.04 / 3), rel=1e-6)


def test_dl_high_heterogeneity_inflates_tau2():
    """Strongly disagreeing effects → large Q, positive tau², I²→high."""
    out = _dersimonian_laird(
        effects=np.array([1.0, -1.0, 1.2, -0.8]),
        variances=np.array([0.04, 0.04, 0.04, 0.04]),
    )
    assert out["tau2"] > 0
    assert out["i2"] > 0.75
    assert out["q_p"] < 0.05


def test_dl_returns_empty_on_too_few_studies():
    assert _dersimonian_laird(np.array([1.0]), np.array([0.04])) == {}
    assert _dersimonian_laird(np.array([]), np.array([])) == {}


def test_dl_filters_nonpositive_variances():
    """Studies with zero or negative variance are dropped before pooling.
    Two valid + one invalid should pool exactly the two valid studies."""
    out_filtered = _dersimonian_laird(
        effects=np.array([1.0, 1.2, 1.1]),
        variances=np.array([0.04, 0.04, 0.0]),
    )
    out_only_valid = _dersimonian_laird(
        effects=np.array([1.0, 1.2]),
        variances=np.array([0.04, 0.04]),
    )
    assert out_filtered["n_studies"] == 2
    assert out_filtered["pooled_effect"] == pytest.approx(out_only_valid["pooled_effect"])


def test_dl_pooled_se_smaller_than_individual():
    """Two studies SE=0.2 each → pooled SE must be ≤ smallest study SE (no het)."""
    out = _dersimonian_laird(np.array([1.0, 1.0]), np.array([0.04, 0.04]))
    assert out["pooled_se"] <= 0.2
    assert out["pooled_se"] == pytest.approx(np.sqrt(0.04 / 2), rel=1e-6)


# ---------------------------------------------------------------------------
# Integration: RE pooling threads through cross_dataset_de when fixtures
# expose CI columns (limma) or SE (DESeq2).
# ---------------------------------------------------------------------------

def test_cross_dataset_de_reports_random_effects(deg_store, mappings):
    """OE vs EH has 5 fixture contributors that all ship SE or CI columns.
    Genes present in ≥2 of them should carry a DerSimonian-Laird pooled
    estimate; the result-level counter must reflect that."""
    res = cross_dataset_de(
        datasets=[], deg_datasets=deg_store,
        groupA=OE, groupB=EH, mappings=mappings, topN=500,
    )
    assert "error" not in res
    assert res["n_re_genes"] > 0, "no genes received an RE pooled estimate"
    assert "DerSimonian-Laird" in res["test"]

    all_top = res["top_consistent_up"] + res["top_consistent_down"]
    with_re = [g for g in all_top if g.get("re_pooled_logFC") is not None]
    assert len(with_re) > 0, "expected at least one shown gene with an RE estimate"

    for g in with_re:
        if g["direction"] == "UP":
            assert g["re_pooled_logFC"] > 0, f"UP gene {g['gene']} has negative pooled logFC"
        else:
            assert g["re_pooled_logFC"] < 0, f"DOWN gene {g['gene']} has positive pooled logFC"
        assert g["re_ci_low"] <= g["re_pooled_logFC"] <= g["re_ci_high"], g
        assert 0.0 <= g["re_i2"] <= 1.0
        assert g["re_n_studies"] >= 2


def test_cross_dataset_de_heterogeneity_counter(deg_store, mappings):
    """The result-level n_high_heterogeneity_genes counter must equal the count
    of per-gene high_heterogeneity=True entries across both directions."""
    res = cross_dataset_de(
        datasets=[], deg_datasets=deg_store,
        groupA=OE, groupB=EH, mappings=mappings, topN=200,
    )
    all_genes = res["top_consistent_up"] + res["top_consistent_down"]
    n_flagged = sum(1 for g in all_genes if g.get("high_heterogeneity"))
    # The result-level counter is computed over the full filtered set, not
    # just the top-N shown — so it should be ≥ n_flagged shown.
    assert res["n_high_heterogeneity_genes"] >= n_flagged
