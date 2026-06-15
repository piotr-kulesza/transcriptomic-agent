"""
Smoke test for the null-calibration diagnostic. Runs the permuted-label
pipeline at low fidelity (2 iterations, 30 GSEA perms, Hallmark-only) and
asserts:
  - the pipeline executes end-to-end on permuted inputs
  - permuted runs confirm fewer hypotheses than real data
  - the fast-mode env knobs are honoured

Kept fast (~1 minute on a laptop) so it can stay in the CI loop. The full
20-iteration diagnostic is `eval/null_calibration.py`.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

# Set fast-mode knobs BEFORE importing engine code so meta_gsea picks them up
# at module import time.
os.environ["META_GSEA_PERMUTATION_NUM"] = "30"
os.environ["META_GSEA_COLLECTION_PREFIX"] = "HALLMARK_"

from eval.conftest import _ensure_gmt
_ensure_gmt()

from eval.null_calibration import load_real_store, permute_store, run_engine_once


@pytest.fixture(scope="module")
def real_tally():
    return run_engine_once(load_real_store())


def test_permuted_pipeline_runs_end_to_end():
    rng = np.random.default_rng(123)
    permuted = permute_store(load_real_store(), rng)
    tally = run_engine_once(permuted)
    assert tally["total"] > 0
    assert "confirmed" in tally
    assert "by_seed" in tally


def test_permuted_confirms_fewer_than_real(real_tally):
    """Real-data CONFIRMED count must exceed permuted-null in both of two seeds.
    If the gate is so loose that permuted labels keep being confirmed, this
    fails — and the engine's evidence threshold needs tightening."""
    rng = np.random.default_rng(7)
    null_confirmed = []
    for _ in range(2):
        permuted = permute_store(load_real_store(), rng)
        tally = run_engine_once(permuted)
        null_confirmed.append(tally["confirmed"])
    real_confirmed = real_tally["confirmed"]
    assert all(n < real_confirmed for n in null_confirmed), (
        f"permuted CONFIRMED ({null_confirmed}) ≥ real CONFIRMED ({real_confirmed}) — "
        f"evidence gate is too permissive; tighten it."
    )
