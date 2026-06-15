"""
Cross-run knowledge helpers for the AI-as-PI agent.

Disease-agnostic. Each entry is keyed by (canonical_pair, item, direction) where:
  - canonical_pair: a "{groupA} vs {groupB}" string in canonical orientation
    (non-reference first; same string regardless of input order).
  - item: a pathway name or gene symbol as an opaque string.
  - direction: stored on each entry; opposite-direction signals flip into the
    contradiction counter rather than overwriting the majority view.

These functions operate on plain dicts and a path. The runner does NOT call
them directly — it goes through `memory_store.MemoryStore`, which scopes every
read/write by `(user_id, project_id)` so different users / projects never
share a knowledge file.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from typing import Iterable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MAX_PROVENANCE_PER_ENTRY = 20    # cap history per entry; oldest dropped
MAX_PRIOR_ENTRIES_IN_PROMPT = 30  # cap rendered into system prompt


def _empty_store() -> dict:
    return {"version": SCHEMA_VERSION, "entries": []}


def load_knowledge(path: str) -> dict:
    """Load knowledge.json (or return an empty store). Malformed files → empty store + log."""
    if not os.path.exists(path):
        return _empty_store()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "entries" not in data:
            logger.warning("knowledge store at %s has unexpected shape; treating as empty", path)
            return _empty_store()
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("knowledge store at %s unreadable (%s); treating as empty", path, e)
        return _empty_store()


def save_knowledge(knowledge: dict, path: str) -> None:
    """Atomic write of knowledge.json. Creates parent dir if missing."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".knowledge-", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(knowledge, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _entry_key(pair: str, item: str) -> tuple[str, str]:
    """Identity key for an entry — used for in-memory lookup; not serialised."""
    return (pair.strip(), item.strip().upper())


def relevant_entries(knowledge: dict, pairs: Iterable[str]) -> list[dict]:
    """Return entries whose canonical pair appears in `pairs`."""
    pair_set = {p.strip() for p in pairs if p and p.strip()}
    out = []
    for entry in knowledge.get("entries", []):
        claim = entry.get("claim") or {}
        if (claim.get("pair") or "").strip() in pair_set:
            out.append(entry)
    return out


def format_prior_knowledge_block(entries: list[dict]) -> str:
    """
    Render a human-readable prior-knowledge block for the system prompt.
    Empty list → empty string (caller should suppress the section).
    """
    if not entries:
        return ""
    # Sort by support_count desc, then by best_fdr asc (most-supported first)
    entries_sorted = sorted(
        entries,
        key=lambda e: (
            -(e.get("support_count") or 0),
            e.get("evidence_summary", {}).get("best_fdr") or 1.0,
        ),
    )[:MAX_PRIOR_ENTRIES_IN_PROMPT]

    lines = []
    for e in entries_sorted:
        claim = e.get("claim") or {}
        ev = e.get("evidence_summary") or {}
        pair = claim.get("pair", "")
        item = claim.get("item", "")
        direction = claim.get("direction", "")
        in_group = claim.get("in_group", "")
        verdict = (e.get("verdict") or "").upper()
        sup = e.get("support_count") or 0
        contra = e.get("contradiction_count") or 0
        fams = ", ".join(ev.get("method_families") or [])
        n_ds = ev.get("n_datasets")
        fdr = ev.get("best_fdr")
        fdr_str = f"FDR≤{fdr:.3g}" if isinstance(fdr, (int, float)) else "FDR n/a"
        n_ds_str = f"{n_ds} datasets" if isinstance(n_ds, int) else "n/a datasets"
        flag = " ⚠ contradicted previously" if contra > 0 else ""
        lines.append(
            f"- [{pair}] {item} {direction} in {in_group} — {verdict} "
            f"(support={sup}, contradictions={contra}; {fams}; {n_ds_str}; {fdr_str}){flag}"
        )
    return "\n".join(lines)


def _top_signed_items(evidence_items: list[dict], n: int = 1) -> list[tuple[str, str]]:
    """
    Fall back when a hypothesis has no direction_claims:
    return up to n (item, direction) pairs from the first evidence item with signed data.
    """
    out = []
    for ev in evidence_items or []:
        up   = list(ev.get("enriched_up")   or []) + list(ev.get("genes_up")   or [])
        down = list(ev.get("enriched_down") or []) + list(ev.get("genes_down") or [])
        for x in up:
            if x:
                out.append((str(x), "UP"))
                if len(out) >= n:
                    return out
        for x in down:
            if x:
                out.append((str(x), "DOWN"))
                if len(out) >= n:
                    return out
        if out:
            return out
    return out


def extract_claims_from_hypotheses(
    hypotheses: list[dict],
    direction_claims_by_hid: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """
    Produce one claim per directional signal from each resolved hypothesis.
    Source priority:
      1. direction_claims attached to the hypothesis verdict (when CONFIRMED) — preferred.
      2. top signed item from the first evidence row — fallback.
    Uncertain / rejected hypotheses contribute claims too, tagged with their verdict;
    only CONFIRMED claims increment support, but stored direction lets us detect flips later.
    """
    direction_claims_by_hid = direction_claims_by_hid or {}
    out: list[dict] = []
    for h in hypotheses:
        status = (h.get("status") or "").lower()
        if status not in ("confirmed", "uncertain", "rejected"):
            continue
        evidence = h.get("evidence") or []
        if not evidence:
            continue

        pair = ""
        for ev in evidence:
            if ev.get("orientation"):
                pair = ev["orientation"]
                break
        if not pair:
            continue

        method_families = sorted({ev.get("method_family") for ev in evidence if ev.get("method_family")})
        all_ds: set = set()
        for ev in evidence:
            all_ds.update(ev.get("dataset_ids") or [])
        fdrs = [ev.get("best_fdr") for ev in evidence if isinstance(ev.get("best_fdr"), (int, float))]
        best_fdr = float(min(fdrs)) if fdrs else None
        ev_summary = {
            "method_families": method_families,
            "n_datasets": len(all_ds),
            "best_fdr": best_fdr,
        }

        signals: list[tuple[str, str, str]] = []  # (item, direction, in_group)
        dcs = direction_claims_by_hid.get(h.get("id") or "") or []
        for dc in dcs:
            item = (dc.get("item") or "").strip()
            direction = (dc.get("direction") or "").strip().upper()
            in_group = (dc.get("in_group") or "").strip()
            if item and direction in ("UP", "DOWN") and in_group:
                signals.append((item, direction, in_group))

        if not signals:
            fallback = _top_signed_items(evidence, n=1)
            if fallback:
                item, direction = fallback[0]
                parts = pair.split(" vs ", 1)
                in_group = parts[0] if direction == "UP" and len(parts) == 2 else (parts[1] if len(parts) == 2 else "")
                if item and direction and in_group:
                    signals.append((item, direction, in_group))

        for item, direction, in_group in signals:
            out.append({
                "claim": {"pair": pair, "item": item, "direction": direction, "in_group": in_group},
                "verdict": status,
                "evidence_summary": ev_summary,
                "hypothesis_id": h.get("id"),
                "hypothesis_text": h.get("text", ""),
            })
    return out


def merge_claims(
    knowledge: dict,
    claims: list[dict],
    run_meta: dict,
) -> tuple[dict, list[dict]]:
    """
    Merge incoming claims into the knowledge store.

    For each incoming claim:
      - Key on (canonical_pair, item).
      - If new key: add as a fresh entry; support_count=1 if CONFIRMED else 0.
      - If existing key with same direction: increment support_count (if CONFIRMED),
        refresh evidence_summary to whichever has the better (lower) best_fdr, append provenance.
      - If existing key with opposite direction: increment contradiction_count, append provenance,
        AND emit a contradiction record (caller surfaces these in the report).

    Returns (updated_knowledge, contradictions_list).
    """
    knowledge = knowledge or _empty_store()
    knowledge.setdefault("version", SCHEMA_VERSION)
    knowledge.setdefault("entries", [])

    index: dict[tuple[str, str], dict] = {}
    for entry in knowledge["entries"]:
        claim = entry.get("claim") or {}
        pair = claim.get("pair", "")
        item = claim.get("item", "")
        if pair and item:
            index[_entry_key(pair, item)] = entry

    contradictions: list[dict] = []
    timestamp = datetime.now().isoformat(timespec="seconds")

    for c in claims:
        claim = c.get("claim") or {}
        pair = (claim.get("pair") or "").strip()
        item = (claim.get("item") or "").strip()
        direction = (claim.get("direction") or "").strip().upper()
        in_group = (claim.get("in_group") or "").strip()
        verdict = (c.get("verdict") or "").lower()
        if not pair or not item or direction not in ("UP", "DOWN"):
            continue

        prov_entry = {
            "run_id": run_meta.get("run_id"),
            "datasets": run_meta.get("datasets") or [],
            "groups": run_meta.get("groups") or [],
            "model": run_meta.get("model"),
            "date": timestamp,
            "verdict": verdict,
            "hypothesis_id": c.get("hypothesis_id"),
            "hypothesis_text": c.get("hypothesis_text", ""),
            "direction": direction,
            "in_group": in_group,
            "evidence_summary": c.get("evidence_summary") or {},
        }

        key = _entry_key(pair, item)
        existing = index.get(key)
        if existing is None:
            entry = {
                "claim": {"pair": pair, "item": item, "direction": direction, "in_group": in_group},
                "verdict": verdict,
                "evidence_summary": c.get("evidence_summary") or {},
                "support_count": 1 if verdict == "confirmed" else 0,
                "contradiction_count": 0,
                "provenance": [prov_entry],
                "first_seen": timestamp,
                "last_updated": timestamp,
            }
            knowledge["entries"].append(entry)
            index[key] = entry
            continue

        # Direction-flip detection: existing stored direction vs incoming
        existing_dir = ((existing.get("claim") or {}).get("direction") or "").upper()
        if existing_dir and existing_dir != direction:
            existing["contradiction_count"] = (existing.get("contradiction_count") or 0) + 1
            contradictions.append({
                "pair": pair,
                "item": item,
                "stored_direction": existing_dir,
                "stored_in_group": (existing.get("claim") or {}).get("in_group", ""),
                "new_direction": direction,
                "new_in_group": in_group,
                "new_verdict": verdict,
                "stored_verdict": (existing.get("verdict") or "").lower(),
                "support_count": existing.get("support_count") or 0,
                "stored_provenance": list(existing.get("provenance") or [])[-3:],
            })
            # Record but do NOT overwrite the stored direction — keep the majority view.
            existing.setdefault("provenance", []).append(prov_entry)
            existing["provenance"] = existing["provenance"][-MAX_PROVENANCE_PER_ENTRY:]
            existing["last_updated"] = timestamp
            continue

        # Same direction: support++ (only on confirmed) and refresh ev_summary if FDR improved.
        if verdict == "confirmed":
            existing["support_count"] = (existing.get("support_count") or 0) + 1
        existing.setdefault("provenance", []).append(prov_entry)
        existing["provenance"] = existing["provenance"][-MAX_PROVENANCE_PER_ENTRY:]
        existing["last_updated"] = timestamp
        # Refresh evidence_summary if the new run is stronger
        new_ev = c.get("evidence_summary") or {}
        cur_ev = existing.get("evidence_summary") or {}
        new_fdr = new_ev.get("best_fdr")
        cur_fdr = cur_ev.get("best_fdr")
        if isinstance(new_fdr, (int, float)) and (
            not isinstance(cur_fdr, (int, float)) or new_fdr < cur_fdr
        ):
            existing["evidence_summary"] = new_ev
        # Verdict precedence: confirmed > uncertain > rejected
        _rank = {"confirmed": 2, "uncertain": 1, "rejected": 0, "": 0}
        if _rank.get(verdict, 0) > _rank.get((existing.get("verdict") or "").lower(), 0):
            existing["verdict"] = verdict

    return knowledge, contradictions


def canonical_pairs_from_datasets(datasets: list, deg_datasets: dict, mappings: dict, reference: str | None) -> set[str]:
    """
    Enumerate canonical pair strings the current run will produce evidence for.

    Pulls from:
      - raw datasets: every unordered pair of distinct group labels in each dataset.
      - DEG datasets: each comparison's (groupA, groupB).
    Each pair is canonicalised via orient.canonical_order, then formatted "A vs B".
    """
    from .orient import canonical_order
    from ..tools.cross import resolve_group

    pairs: set[str] = set()
    for ds in datasets or []:
        groups = list(ds.get("groups") or [])
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                gA = resolve_group(groups[i], mappings)
                gB = resolve_group(groups[j], mappings)
                a, b = canonical_order(gA, gB, reference)
                pairs.add(f"{a} vs {b}")
    for ds in (deg_datasets or {}).values():
        for comp in ds.get("comparisons") or []:
            gA = resolve_group(comp["groupA"], mappings)
            gB = resolve_group(comp["groupB"], mappings)
            a, b = canonical_order(gA, gB, reference)
            pairs.add(f"{a} vs {b}")
    return pairs
