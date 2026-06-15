"""
Shared pytest fixtures for the Layer-1 regression harness.

Loads the 14 slim DEG tables from eval/fixtures/deg/ into the same
``deg_datasets`` dict shape the backend produces from ``upload_deg``, and
exports the canonical group-name mapping used in the endometriosis study.

The DEG tables live in ``eval/fixtures/deg/`` (5 MB, gzipped). They are
checked into the repo so the suite runs without external data. Rebuild
them with ``python eval/fixtures/build_fixtures.py``.

The fixtures are TEST DATA only — engine code remains disease-agnostic.
"""
from __future__ import annotations

import glob
import os
from typing import Dict, List, Tuple

import pandas as pd
import pytest

# Group abbreviations used in fixture filenames → canonical group labels.
# Mirrors validation/headless_run.py so seeders see identical names.
GROUPS: Dict[str, str] = {
    "DIE": "Deep infiltrating endometriosis",
    "OE":  "Ovarian endometriosis",
    "PE":  "Peritoneal endometriosis",
    "EH":  "Healthy endometrium",
}

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "deg")


def _parse_comparison(filename: str) -> Tuple[str, str]:
    stem = os.path.basename(filename).replace(".csv.gz", "").replace(".csv", "")
    comp = stem.split("_")[-1]  # e.g. "OEvsEH"
    a, b = comp.split("vs")
    return GROUPS[a], GROUPS[b]


def _load_one(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    rename = {}
    # First pass: detect adj_p columns before p (so "adj_p_val" doesn't match the p rule)
    for c in df.columns:
        cn = c.lower().replace(".", "_").replace(" ", "_")
        if cn in ("adj_p_val", "adj_p", "padj", "fdr"):
            rename[c] = "adj_p"
    for c in df.columns:
        if c in rename:
            continue
        cn = c.lower().replace(".", "_").replace(" ", "_")
        if cn in ("gene", "symbol", "gene_symbol"):
            rename[c] = "gene"
        elif cn in ("logfc",):
            rename[c] = "logFC"
        elif cn in ("p_value", "pvalue", "p"):
            rename[c] = "p"
        elif cn in ("ci_l",):
            rename[c] = "ci_l"
        elif cn in ("ci_r",):
            rename[c] = "ci_r"
        elif cn in ("se",):
            rename[c] = "se"
    df = df.rename(columns=rename)
    df["gene"] = df["gene"].astype(str).str.strip().str.upper()
    keep = ["gene", "logFC", "p", "adj_p"]
    if "ci_l" in df.columns and "ci_r" in df.columns:
        keep += ["ci_l", "ci_r"]
    if "se" in df.columns:
        keep.append("se")
    df = df[keep].dropna(subset=["gene", "logFC", "p", "adj_p"]).set_index("gene")
    df = df[~df.index.duplicated(keep="first")]
    return df


def _ensure_gmt() -> str:
    """Resolve GMT_FILE to an absolute path; mutate env so tools that read
    GMT_FILE at call-time pick it up regardless of cwd."""
    proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    gmt = os.environ.get("GMT_FILE", "combined.gmt")
    if not os.path.isabs(gmt):
        gmt = os.path.join(proj_root, "backend", gmt)
    os.environ["GMT_FILE"] = gmt
    return gmt


@pytest.fixture(scope="session")
def gmt_file() -> str:
    path = _ensure_gmt()
    if not os.path.isfile(path):
        pytest.skip(f"GMT_FILE not found at {path}")
    return path


@pytest.fixture(scope="session")
def deg_store() -> Dict[str, dict]:
    files = sorted(glob.glob(os.path.join(FIXTURE_DIR, "wynik_*.csv.gz")))
    if not files:
        pytest.skip(
            f"No DEG fixtures in {FIXTURE_DIR}. "
            f"Run `python eval/fixtures/build_fixtures.py` to generate."
        )
    store: Dict[str, dict] = {}
    for i, f in enumerate(files, 1):
        gA, gB = _parse_comparison(f)
        df = _load_one(f)
        name = f"DEG {i}"
        store[name] = {
            "name": name,
            "type": "deg",
            "source_file": os.path.basename(f),
            "comparisons": [{"groupA": gA, "groupB": gB, "df": df}],
        }
    return store


@pytest.fixture(scope="session")
def mappings() -> Dict[str, list]:
    """No alias mappings — fixture comparisons already use canonical names."""
    return {}


@pytest.fixture(scope="session")
def canonical_pairs(deg_store) -> List[Tuple[str, str]]:
    pairs = set()
    for ds in deg_store.values():
        for comp in ds["comparisons"]:
            pairs.add(tuple(sorted([comp["groupA"], comp["groupB"]])))
    return sorted(pairs)
