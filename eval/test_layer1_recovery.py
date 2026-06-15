"""
Layer-1 regression harness.

Drives only the deterministic engine (meta_gsea + cross_dataset_de — no LLM,
no API cost) on the 14 endometriosis DEG fixtures and asserts the
direction-of-signal calls match prior fgsea/enrichR ground truth (parsed in
validation/ground_truth_parsed.txt).

These are explicit expected-direction assertions: a direction flip in
``meta_rank`` / ``cross_dataset_de`` (the bug the original tier-1 prompt
called out) would fail the suite immediately. Test data is endometriosis;
the engine itself stays disease-agnostic.
"""
from __future__ import annotations

import os
from typing import Optional

import pytest

# Ensure GMT_FILE is set before tool import so deferred loaders see it.
from eval.conftest import _ensure_gmt
_ensure_gmt()

from backend.tools.cross import meta_gsea, cross_dataset_de, meta_rank


OE = "Ovarian endometriosis"
PE = "Peritoneal endometriosis"
DIE = "Deep infiltrating endometriosis"
EH = "Healthy endometrium"


def _nes_for(result: dict, pathway: str) -> Optional[float]:
    """Return signed NES for `pathway` from a meta_gsea result, or None if absent."""
    for entry in result.get("top_enriched_up", []) + result.get("top_enriched_down", []):
        if entry.get("pathway") == pathway:
            return float(entry.get("nes", 0.0))
    return None


def _fdr_for(result: dict, pathway: str) -> Optional[float]:
    for entry in result.get("top_enriched_up", []) + result.get("top_enriched_down", []):
        if entry.get("pathway") == pathway:
            return float(entry.get("fdr", 1.0))
    return None


# ---------------------------------------------------------------------------
# meta_gsea direction calls. Orientation: meta_gsea(groupA=X, groupB=Y)
# returns NES>0 = higher in X. Ground truth uses the same convention.
# ---------------------------------------------------------------------------

# Restrict to MSigDB Hallmarks so per-pathway assertions match the manual
# fgsea ground truth one-to-one. Other collections (Reactome/WP/KEGG) crowd
# top-N when the GMT spans all collections.
@pytest.fixture(scope="module")
def gsea_OE_vs_EH(deg_store, mappings, gmt_file):
    return meta_gsea(datasets=[], deg_datasets=deg_store,
                     groupA=OE, groupB=EH, mappings=mappings,
                     collection_prefix="HALLMARK_", topN=50)


@pytest.fixture(scope="module")
def gsea_PE_vs_EH(deg_store, mappings, gmt_file):
    return meta_gsea(datasets=[], deg_datasets=deg_store,
                     groupA=PE, groupB=EH, mappings=mappings,
                     collection_prefix="HALLMARK_", topN=50)


@pytest.fixture(scope="module")
def gsea_DIE_vs_EH(deg_store, mappings, gmt_file):
    return meta_gsea(datasets=[], deg_datasets=deg_store,
                     groupA=DIE, groupB=EH, mappings=mappings,
                     collection_prefix="HALLMARK_", topN=50)


def test_meta_gsea_pools_all_OE_vs_EH_sources(gsea_OE_vs_EH):
    """5 fixture comparisons contribute to OE vs EH; meta_gsea must pool all of them."""
    assert "error" not in gsea_OE_vs_EH, gsea_OE_vs_EH.get("error")
    # 4 files written as "OEvsEH" + 1 written as "EHvsOE" — both directions pool.
    assert gsea_OE_vs_EH["n_datasets_pooled"] == 5, gsea_OE_vs_EH["contributing_datasets"]


def test_OE_vs_EH_complement_up(gsea_OE_vs_EH):
    """Ground truth: HALLMARK_COMPLEMENT UP in OE vs EH (NES=+1.87, padj=8e-06)."""
    nes = _nes_for(gsea_OE_vs_EH, "HALLMARK_COMPLEMENT")
    fdr = _fdr_for(gsea_OE_vs_EH, "HALLMARK_COMPLEMENT")
    assert nes is not None, "HALLMARK_COMPLEMENT missing from OE vs EH result"
    assert nes > 0, f"complement direction flipped: NES={nes}"
    assert fdr < 0.05, f"complement not significant: FDR={fdr}"


def test_OE_vs_EH_immune_up(gsea_OE_vs_EH):
    """Ground truth: HALLMARK_INTERFERON_GAMMA_RESPONSE UP in OE vs EH (NES=+1.82)."""
    nes = _nes_for(gsea_OE_vs_EH, "HALLMARK_INTERFERON_GAMMA_RESPONSE")
    assert nes is not None
    assert nes > 0, f"IFN-gamma direction flipped: NES={nes}"


def test_OE_vs_EH_proliferation_down(gsea_OE_vs_EH):
    """Ground truth: E2F_TARGETS DOWN (-2.52), G2M_CHECKPOINT DOWN (-2.51) in OE vs EH."""
    for pathway in ("HALLMARK_E2F_TARGETS", "HALLMARK_G2M_CHECKPOINT"):
        nes = _nes_for(gsea_OE_vs_EH, pathway)
        fdr = _fdr_for(gsea_OE_vs_EH, pathway)
        assert nes is not None, f"{pathway} missing from OE vs EH"
        assert nes < 0, f"{pathway} direction flipped: NES={nes}"
        assert fdr < 0.05, f"{pathway} not significant in OE vs EH: FDR={fdr}"


def test_OE_vs_EH_estrogen_response_down(gsea_OE_vs_EH):
    """Ground truth: HALLMARK_ESTROGEN_RESPONSE_LATE DOWN in OE vs EH (NES=-1.70)."""
    nes = _nes_for(gsea_OE_vs_EH, "HALLMARK_ESTROGEN_RESPONSE_LATE")
    assert nes is not None
    assert nes < 0, f"ESTROGEN_RESPONSE_LATE direction flipped: NES={nes}"


def test_PE_vs_EH_immune_up(gsea_PE_vs_EH):
    """Ground truth: ALLOGRAFT_REJECTION (+2.20, padj=6e-11) and INFLAMMATORY_RESPONSE
    (+1.97) UP in PE vs EH. Both are dominant immune signals in peritoneal lesions."""
    assert "error" not in gsea_PE_vs_EH, gsea_PE_vs_EH.get("error")
    for pathway in ("HALLMARK_ALLOGRAFT_REJECTION", "HALLMARK_INFLAMMATORY_RESPONSE"):
        nes = _nes_for(gsea_PE_vs_EH, pathway)
        fdr = _fdr_for(gsea_PE_vs_EH, pathway)
        assert nes is not None, f"{pathway} missing from PE vs EH"
        assert nes > 0, f"{pathway} direction flipped in PE vs EH: NES={nes}"
        assert fdr < 0.05, f"{pathway} not significant in PE vs EH: FDR={fdr}"


def test_PE_vs_EH_proliferation_down(gsea_PE_vs_EH):
    """Ground truth: MYC_TARGETS_V1 (-2.57), OXIDATIVE_PHOSPHORYLATION (-2.45),
    E2F_TARGETS (-2.22), G2M_CHECKPOINT (-2.09) DOWN in PE vs EH."""
    for pathway in (
        "HALLMARK_MYC_TARGETS_V1",
        "HALLMARK_OXIDATIVE_PHOSPHORYLATION",
        "HALLMARK_E2F_TARGETS",
        "HALLMARK_G2M_CHECKPOINT",
    ):
        nes = _nes_for(gsea_PE_vs_EH, pathway)
        fdr = _fdr_for(gsea_PE_vs_EH, pathway)
        assert nes is not None, f"{pathway} missing from PE vs EH"
        assert nes < 0, f"{pathway} direction flipped in PE vs EH: NES={nes}"
        assert fdr < 0.05, f"{pathway} not significant in PE vs EH: FDR={fdr}"


def test_DIE_vs_EH_proliferation_down(gsea_DIE_vs_EH):
    """Ground truth: E2F_TARGETS DOWN (-2.17, padj=5e-07) in DIE vs EH —
    proliferation suppression replicates across all three lesion subtypes."""
    assert "error" not in gsea_DIE_vs_EH, gsea_DIE_vs_EH.get("error")
    nes = _nes_for(gsea_DIE_vs_EH, "HALLMARK_E2F_TARGETS")
    fdr = _fdr_for(gsea_DIE_vs_EH, "HALLMARK_E2F_TARGETS")
    assert nes is not None and nes < 0, f"E2F_TARGETS direction flipped in DIE vs EH: NES={nes}"
    assert fdr < 0.05, f"E2F_TARGETS not significant in DIE vs EH: FDR={fdr}"


# ---------------------------------------------------------------------------
# cross_dataset_de direction sanity. Operating on the same fixture, the
# DEG-pool Fisher meta should keep top consistent UP genes with positive
# logFC and DOWN with negative — direction flip catch at the gene level.
# ---------------------------------------------------------------------------

def test_cross_dataset_de_OE_vs_EH_direction_consistency(deg_store, mappings):
    res = cross_dataset_de(
        datasets=[], deg_datasets=deg_store, groupA=OE, groupB=EH,
        mappings=mappings, topN=10,
    )
    assert "error" not in res, res.get("error")
    assert res["n_consistent_genes"] > 0
    for g in res.get("top_consistent_up", []):
        # avg_abs_logFC is unsigned; direction key holds sign.
        assert g["direction"] == "UP"
    for g in res.get("top_consistent_down", []):
        assert g["direction"] == "DOWN"


def test_meta_rank_orientation_OE_vs_EH(deg_store, mappings):
    """meta_rank(groupA=OE, groupB=EH) must give an opposite-signed series to
    meta_rank(groupA=EH, groupB=OE) — this guards the direction sign flip the
    original tier-1 prompt called out."""
    rnk_oe_eh = meta_rank(datasets=[], deg_datasets=deg_store,
                          groupA=OE, groupB=EH, mappings=mappings)
    rnk_eh_oe = meta_rank(datasets=[], deg_datasets=deg_store,
                          groupA=EH, groupB=OE, mappings=mappings)
    assert not rnk_oe_eh.empty
    assert not rnk_eh_oe.empty
    # The two series should be near-exact mirror images: corr ≈ -1
    common = rnk_oe_eh.index.intersection(rnk_eh_oe.index)
    corr = rnk_oe_eh.loc[common].corr(rnk_eh_oe.loc[common])
    assert corr < -0.99, f"meta_rank orientation not symmetric: corr={corr}"
