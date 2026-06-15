"""
Smoke test for the engine-vs-single-tool benchmark. Runs the OE vs EH
contrast end-to-end at low fidelity, asserting:

- the benchmark function returns the expected shape
- per-cohort DE Jaccard@100 is in [0, 1]
- the engine flags a positive number of significant pathways under pooling
- there is at least one pathway whose direction agrees with the pooled call
  in at least one cohort (sanity)

Hallmark-only + 50 GSEA permutations to keep CI fast (~1 min).
"""
from __future__ import annotations

import os

from eval.conftest import _ensure_gmt
_ensure_gmt()

from eval.benchmark import benchmark_one_pair, load_store


OE = "Ovarian endometriosis"
EH = "Healthy endometrium"


def test_benchmark_oe_vs_eh_smoke():
    store = load_store()
    r = benchmark_one_pair(store, "OE", OE, EH,
                           hallmark_only=True, de_k_list=(100,),
                           pathway_k=20, gsea_perm=50)
    assert "error" not in r
    assert r["n_cohorts"] == 5
    assert r["n_sig_pathways_pooled"] > 0
    for c in r["cohort"]:
        j = c["de_jaccard"]["100"]
        assert 0.0 <= j <= 1.0


def test_benchmark_pooled_recovers_known_directions():
    """Sanity: under the OE vs EH pooled GSEA, at least one cohort must
    agree on direction for ≥half the shared significant pathways. Catches
    the case where the engine confuses orientation across cohorts."""
    store = load_store()
    r = benchmark_one_pair(store, "OE", OE, EH,
                           hallmark_only=True, de_k_list=(100,),
                           pathway_k=20, gsea_perm=50)
    valid = [c for c in r["cohort"]
             if c["shared_sig_pathways"] > 0
             and c["direction_agreement_on_shared"] == c["direction_agreement_on_shared"]]
    assert valid, "no cohort shares significant pathways with the pooled meta"
    assert any(c["direction_agreement_on_shared"] >= 0.5 for c in valid)
