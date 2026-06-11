"""Headless DEG-only validation run.

Loads the 14 DEG tables from data_subtypes_new, replicates the backend
upload_deg column parsing, and drives run_agent_loop directly (no UI/server).
Writes the agent report to backend reports/ as usual.

Run from the transcriptomic-agent project root.
"""
import asyncio
import io
import os
import sys
import glob
import json

import pandas as pd
from dotenv import load_dotenv

# --- paths -------------------------------------------------------------------
PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT)
DEG_DIR = os.environ["DEG_DIR"]

load_dotenv(os.path.join(PROJECT, "backend", ".env"))
API_KEY = os.environ["ANTHROPIC_API_KEY"]
# Resolve GMT to an absolute path so tools find it regardless of cwd.
gmt = os.environ.get("GMT_FILE", "combined.gmt")
if not os.path.isabs(gmt):
    gmt = os.path.join(PROJECT, "backend", gmt)
os.environ["GMT_FILE"] = gmt

from backend.agent.runner import run_agent_loop  # noqa: E402

# --- group abbreviation -> canonical name ------------------------------------
GROUPS = {
    "DIE": "Deep infiltrating endometriosis",
    "OE":  "Ovarian endometriosis",
    "PE":  "Peritoneal endometriosis",
    "EH":  "Healthy endometrium",
}


def parse_comparison(fname):
    """wynik_GSE12345_AvsB.csv -> ('A canonical', 'B canonical')."""
    stem = os.path.basename(fname).replace(".csv", "")
    comp = stem.split("_")[-1]            # e.g. OEvsEH
    a, b = comp.split("vs")
    return GROUPS[a], GROUPS[b]


def parse_deg_csv(path):
    """Replicate backend upload_deg column auto-detection -> df[logFC,p,adj_p]."""
    raw = pd.read_csv(path)
    if raw.columns[0].startswith("Unnamed:"):
        raw = raw.rename(columns={raw.columns[0]: "gene"})

    def norm(s):
        return s.lower().replace(".", "_").replace(" ", "_")

    normed = {norm(c): c for c in raw.columns}
    col_map = {}
    for cand in ["gene", "symbol", "gene_symbol", "gene_name", "id", "geneid"]:
        if cand in normed and "gene" not in col_map:
            if cand == "gene_name" and "symbol" in normed:
                continue
            col_map["gene"] = normed[cand]
    for cand in ["logfc", "log2fc", "log2foldchange", "logfoldchange", "lfc", "log2_fold_change"]:
        if cand in normed and "logFC" not in col_map:
            col_map["logFC"] = normed[cand]
    for cand in ["adj_p_val", "adj_p", "padj", "adj_pval", "fdr", "q_value", "qvalue", "p_adj"]:
        if cand in normed and "adj_p" not in col_map:
            col_map["adj_p"] = normed[cand]
    for cand in ["p_value", "pvalue", "pval", "p"]:
        if cand in normed and "p" not in col_map:
            col_map["p"] = normed[cand]

    missing = [k for k in ["gene", "logFC", "p", "adj_p"] if k not in col_map]
    if missing:
        raise ValueError(f"{path}: missing {missing}; cols={raw.columns.tolist()}")

    df = raw.rename(columns={v: k for k, v in col_map.items()})
    df = df[["gene", "logFC", "p", "adj_p"]].dropna()
    df["gene"] = df["gene"].astype(str).str.strip().str.upper()
    df = df.set_index("gene")
    df = df[~df.index.duplicated(keep="first")]
    return df


def build_deg_store():
    files = sorted(glob.glob(os.path.join(DEG_DIR, "wynik_*.csv")))
    store = {}
    for i, f in enumerate(files, 1):
        gA, gB = parse_comparison(f)
        df = parse_deg_csv(f)
        name = f"DEG {i}"
        store[name] = {"name": name, "type": "deg",
                       "comparisons": [{"groupA": gA, "groupB": gB, "df": df}]}
        print(f"{name}: {os.path.basename(f)} -> {gA} vs {gB} ({len(df)} genes)", flush=True)
    return store


async def main():
    deg_store = build_deg_store()
    print(f"\nLoaded {len(deg_store)} DEG tables. Starting agent (DEG-only, "
          f"reproduce/temp=0, max_hypotheses=14)...\n", flush=True)
    report_path = None
    async for ev in run_agent_loop(
        datasets=[], max_hypotheses=14, api_key=API_KEY,
        temperature=0.0, mappings={}, deg_datasets=deg_store,
    ):
        t = ev.get("type")
        if t == "thinking":
            print(f"[step {ev.get('step','?')}] thinking...", flush=True)
        elif t == "result":
            print(f"  result: {str(ev.get('summary',''))[:120]}", flush=True)
        elif t == "hypothesis_eval":
            print(f"  HYP {ev.get('id','?')} -> {ev.get('verdict','?')}", flush=True)
        elif t == "error":
            print(f"  ERROR: {ev.get('message','')}", flush=True)
        elif t == "report":
            report_path = ev.get("path")
            print(f"\nREPORT WRITTEN: {report_path}", flush=True)
        elif t == "done":
            print("DONE", flush=True)
    print(f"\n__REPORT_PATH__={report_path}", flush=True)


if __name__ == "__main__":
    # cwd must be project root so reports/ lands in the repo
    os.chdir(PROJECT)
    asyncio.run(main())
