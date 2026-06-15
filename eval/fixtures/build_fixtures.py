"""
One-shot script that slims and gzips the 14 DEG tables from the R project
into eval/fixtures/deg/. Re-runnable. Keeps only the columns the engine
needs (gene, logFC, CI.L, CI.R, P.Value, adj.P.Val) so the checked-in fixture
is ~5 MB instead of 39 MB.

Source (default): /Users/piotr/Documents/R_projects/meta/data_subtypes_new
Override with env var EVAL_DEG_SOURCE_DIR.
"""
from __future__ import annotations

import glob
import os
import sys

import pandas as pd

# Output schema: gene + logFC + (optional ci_l/ci_r) + (optional se) + p + adj_p.
# Source column name → output column name. Handles both limma (CI-based) and
# DESeq2 (SE-based) DEG tables.
COL_ALIASES = {
    "gene":           ["gene", "symbol", "gene_symbol", "geneid", "gene_id"],
    "logFC":          ["logFC", "log2FoldChange", "log2fc", "logfc", "log2_fold_change"],
    "ci_l":           ["CI.L", "ci_l", "cil"],
    "ci_r":           ["CI.R", "ci_r", "cir"],
    "se":             ["SE", "se", "stderr", "std_err", "lfcSE"],
    "p":              ["P.Value", "pvalue", "p_value", "pval", "p"],
    "adj_p":          ["adj.P.Val", "padj", "adj_p", "adj_p_val", "fdr", "qvalue"],
}

DEFAULT_SRC = "/Users/piotr/Documents/R_projects/meta/data_subtypes_new"


def _find_col(target: str, columns: list[str]) -> str | None:
    aliases = {a.lower().replace(".", "_").replace(" ", "_") for a in COL_ALIASES[target]}
    for c in columns:
        cn = c.lower().replace(".", "_").replace(" ", "_")
        if cn in aliases:
            return c
    return None


def slim_one(src_path: str, dst_path: str) -> int:
    raw = pd.read_csv(src_path)
    # limma's exported tables often have an unnamed first column = gene name
    if raw.columns[0].startswith("Unnamed:"):
        raw = raw.rename(columns={raw.columns[0]: "gene"})
    cols = list(raw.columns)
    gene_col = _find_col("gene", cols)
    logfc_col = _find_col("logFC", cols)
    p_col = _find_col("p", cols)
    adj_p_col = _find_col("adj_p", cols)
    if not (gene_col and logfc_col and p_col and adj_p_col):
        missing = [k for k, v in zip(
            ["gene", "logFC", "p", "adj_p"], [gene_col, logfc_col, p_col, adj_p_col]
        ) if v is None]
        raise ValueError(f"{src_path}: missing required columns {missing} (have {cols})")

    rename = {gene_col: "gene", logfc_col: "logFC", p_col: "p", adj_p_col: "adj_p"}
    for opt in ("ci_l", "ci_r", "se"):
        c = _find_col(opt, cols)
        if c:
            rename[c] = opt
    keep_src = list(rename.keys())
    df = raw[keep_src].rename(columns=rename).copy()
    for c in df.columns:
        if c != "gene":
            df[c] = df[c].astype(float).round(6)
    df.to_csv(dst_path, index=False, compression="gzip")
    return os.path.getsize(dst_path)


def main() -> int:
    src_dir = os.environ.get("EVAL_DEG_SOURCE_DIR", DEFAULT_SRC)
    dst_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deg")
    if not os.path.isdir(src_dir):
        print(f"Source not found: {src_dir}", file=sys.stderr)
        print("Set EVAL_DEG_SOURCE_DIR to override.", file=sys.stderr)
        return 1
    os.makedirs(dst_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(src_dir, "wynik_*.csv")))
    if not files:
        print(f"No wynik_*.csv files in {src_dir}", file=sys.stderr)
        return 1
    total = 0
    for f in files:
        name = os.path.basename(f).replace(".csv", ".csv.gz")
        dst = os.path.join(dst_dir, name)
        sz = slim_one(f, dst)
        total += sz
        print(f"  {name}: {sz / 1024:.0f} KB")
    print(f"Wrote {len(files)} files to {dst_dir} ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
