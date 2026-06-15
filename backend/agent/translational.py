"""
Translational annotation layer (opt-in, post-confirmation, REPORTING ONLY).

For each CONFIRMED hypothesis, look up the top leading-edge genes against
Open Targets (tractability + target-disease association), ChEMBL (drugs and
mechanisms for tractable targets), and ClinicalTrials.gov (trials referencing
those targets for the run's condition).

Strict guardrails:
- Disease-agnostic. The only inputs are gene symbols and an optional condition
  string supplied by the user.
- This is downstream of the evidence gate. The returned record is annotation,
  never evidence. Nothing here can change a verdict.
- Graceful degradation: any connector failure becomes a "not retrieved"
  sentinel on that record. The run must never fail because of this module.
- Caps: at most MAX_LEADING_GENES genes per hypothesis; small per-target /
  per-gene result limits.

Every record carries provenance: connector name, query, retrieval timestamp,
and the IDs returned, so the report can render them as clickable links.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)

OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"
CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
CLINICAL_TRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"

PER_REQUEST_TIMEOUT = 6.0  # seconds, per HTTP call
MAX_LEADING_GENES = 10
MAX_DRUGS_PER_TARGET = 5
MAX_TRIALS_PER_GENE = 5

_SYMBOL_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,9}\b")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _provenance(connector: str, query: str, ids: list, error: str = "") -> dict:
    rec: dict = {
        "connector": connector,
        "query": query,
        "retrieved_at": _now_iso(),
        "ids": [str(i) for i in ids if i],
    }
    if error:
        rec["error"] = error[:160]
    return rec


def leading_genes_for_hypothesis(hypothesis: dict, cap: int = MAX_LEADING_GENES) -> list[str]:
    """
    Build an ordered, deduped list of leading-edge gene symbols for a hypothesis.

    Source priority:
      1. hypothesis['genes'] (the symbols the proposer pinned to the hypothesis).
      2. evidence rows' genes_up / genes_down (gene-level signed lists).
      3. last-resort: ALL-CAPS symbols scraped from the hypothesis text.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _push(g):
        if not g:
            return
        s = str(g).strip().upper()
        if not s or s in seen:
            return
        if not re.match(r"^[A-Z][A-Z0-9\-]{0,15}$", s):
            return
        seen.add(s)
        ordered.append(s)

    for g in hypothesis.get("genes") or []:
        _push(g)
        if len(ordered) >= cap:
            return ordered[:cap]

    for ev in hypothesis.get("evidence") or []:
        for g in (ev.get("genes_up") or []) + (ev.get("genes_down") or []):
            _push(g)
            if len(ordered) >= cap:
                return ordered[:cap]

    if len(ordered) < cap:
        text = hypothesis.get("text") or ""
        for m in _SYMBOL_RE.findall(text):
            _push(m)
            if len(ordered) >= cap:
                break

    return ordered[:cap]


# ── Connector: Open Targets ─────────────────────────────────────────────────

def _ot_lookup(gene: str, condition: Optional[str], client) -> dict:
    """Return {ot_target_id, ot_approved_symbol, ot_tractability, ot_assoc_score, provenance}."""
    search_q = (
        "query Search($q: String!) {"
        " search(queryString: $q, entityNames: [\"target\"]) {"
        " hits { id name entity } } }"
    )
    try:
        r = client.post(
            OPEN_TARGETS_URL,
            json={"query": search_q, "variables": {"q": gene}},
            timeout=PER_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        hits = (r.json().get("data") or {}).get("search", {}).get("hits") or []
        target_id = next((h["id"] for h in hits if h.get("entity") == "target" and h.get("name", "").upper() == gene), None)
        if not target_id:
            target_id = next((h["id"] for h in hits if h.get("entity") == "target"), None)
    except Exception as e:
        return {
            "ot_target_id": None,
            "ot_tractability": "not retrieved",
            "ot_assoc_score": None,
            "provenance": _provenance("open_targets", f"search:{gene}", [], error=str(e)),
        }

    if not target_id:
        return {
            "ot_target_id": None,
            "ot_tractability": "no Open Targets target match",
            "ot_assoc_score": None,
            "provenance": _provenance("open_targets", f"search:{gene}", []),
        }

    detail_q = (
        "query Detail($id: String!, $disease: String!, $hasDisease: Boolean!) {"
        " target(ensemblId: $id) {"
        " id approvedSymbol"
        " tractability { modality value label }"
        " associatedDiseases(query: $disease, page: { index: 0, size: 1 }) @include(if: $hasDisease) {"
        "   rows { score disease { id name } } } } }"
    )
    has_disease = bool((condition or "").strip())
    try:
        r = client.post(
            OPEN_TARGETS_URL,
            json={"query": detail_q, "variables": {"id": target_id, "disease": condition or "", "hasDisease": has_disease}},
            timeout=PER_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        target = ((r.json().get("data") or {}).get("target")) or {}
    except Exception as e:
        return {
            "ot_target_id": target_id,
            "ot_approved_symbol": gene,
            "ot_tractability": "not retrieved",
            "ot_assoc_score": None,
            "provenance": _provenance("open_targets", f"target:{target_id}", [target_id], error=str(e)),
        }

    tract = target.get("tractability") or []
    labels = [t.get("label") for t in tract if t.get("value") and t.get("label")]
    tract_summary = "; ".join(labels[:4]) if labels else "no tractable modality reported"

    assoc_rows = ((target.get("associatedDiseases") or {}).get("rows")) or []
    assoc_score = float(assoc_rows[0]["score"]) if assoc_rows else None
    assoc_disease = ""
    if assoc_rows:
        d = assoc_rows[0].get("disease") or {}
        assoc_disease = d.get("name", "")

    return {
        "ot_target_id": target_id,
        "ot_approved_symbol": target.get("approvedSymbol") or gene,
        "ot_tractability": tract_summary,
        "ot_assoc_score": assoc_score,
        "ot_assoc_disease": assoc_disease,
        "provenance": _provenance(
            "open_targets",
            f"target:{target_id} disease:{condition or 'n/a'}",
            [target_id],
        ),
    }


# ── Connector: ChEMBL ───────────────────────────────────────────────────────

def _chembl_target_id_for_gene(gene: str, client) -> tuple[Optional[str], str]:
    """Return (chembl_target_id, raw_query)."""
    params = {"target_synonym__synonym__iexact": gene, "limit": 1, "format": "json"}
    try:
        r = client.get(f"{CHEMBL_BASE}/target.json", params=params, timeout=PER_REQUEST_TIMEOUT)
        r.raise_for_status()
        targets = (r.json() or {}).get("targets") or []
        if targets:
            return targets[0].get("target_chembl_id"), f"synonym:{gene}"
    except Exception:
        pass
    # Fallback: gene symbol search
    try:
        r = client.get(
            f"{CHEMBL_BASE}/target/search.json",
            params={"q": gene, "limit": 1, "format": "json"},
            timeout=PER_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        targets = (r.json() or {}).get("targets") or []
        if targets:
            return targets[0].get("target_chembl_id"), f"search:{gene}"
    except Exception:
        pass
    return None, f"search:{gene}"


def _chembl_lookup(gene: str, client) -> dict:
    """Return {chembl_target_id, chembl_drugs:[...], provenance}."""
    target_id, query_used = _chembl_target_id_for_gene(gene, client)
    if not target_id:
        return {
            "chembl_target_id": None,
            "chembl_drugs": [],
            "provenance": _provenance("chembl", query_used, []),
        }

    try:
        r = client.get(
            f"{CHEMBL_BASE}/mechanism.json",
            params={"target_chembl_id": target_id, "limit": MAX_DRUGS_PER_TARGET, "format": "json"},
            timeout=PER_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        mechs = (r.json() or {}).get("mechanisms") or []
    except Exception as e:
        return {
            "chembl_target_id": target_id,
            "chembl_drugs": [],
            "provenance": _provenance("chembl", f"mechanism:{target_id}", [target_id], error=str(e)),
        }

    drugs: list[dict] = []
    drug_ids: list[str] = []
    for m in mechs:
        molecule_id = m.get("parent_molecule_chembl_id") or m.get("molecule_chembl_id")
        action = m.get("action_type") or ""
        moa = m.get("mechanism_of_action") or ""
        max_phase = m.get("max_phase_for_ind")
        if not molecule_id:
            continue
        drug_ids.append(molecule_id)
        drugs.append({
            "chembl_id": molecule_id,
            "action_type": action,
            "mechanism_of_action": moa[:200],
            "max_phase": max_phase,
        })

    return {
        "chembl_target_id": target_id,
        "chembl_drugs": drugs[:MAX_DRUGS_PER_TARGET],
        "provenance": _provenance("chembl", f"mechanism:{target_id}", [target_id] + drug_ids),
    }


# ── Connector: ClinicalTrials.gov ───────────────────────────────────────────

def _trials_lookup(gene: str, condition: Optional[str], client) -> dict:
    """Return {trials:[...], provenance}."""
    params = {
        "query.intr": gene,
        "pageSize": MAX_TRIALS_PER_GENE,
        "format": "json",
        "fields": (
            "NCTId,BriefTitle,OverallStatus,Phase,Condition"
        ),
    }
    if condition and condition.strip():
        params["query.cond"] = condition.strip()

    try:
        r = client.get(CLINICAL_TRIALS_URL, params=params, timeout=PER_REQUEST_TIMEOUT)
        r.raise_for_status()
        studies = (r.json() or {}).get("studies") or []
    except Exception as e:
        return {
            "trials": [],
            "provenance": _provenance(
                "clinicaltrials",
                f"intr:{gene} cond:{condition or 'n/a'}",
                [],
                error=str(e),
            ),
        }

    out: list[dict] = []
    ids: list[str] = []
    for s in studies[:MAX_TRIALS_PER_GENE]:
        proto = s.get("protocolSection") or {}
        ident = proto.get("identificationModule") or {}
        status = proto.get("statusModule") or {}
        design = proto.get("designModule") or {}
        nct = ident.get("nctId") or ""
        if not nct:
            continue
        ids.append(nct)
        out.append({
            "nct_id": nct,
            "title": (ident.get("briefTitle") or "")[:160],
            "status": status.get("overallStatus") or "",
            "phases": list(design.get("phases") or []),
        })

    return {
        "trials": out,
        "provenance": _provenance(
            "clinicaltrials",
            f"intr:{gene} cond:{condition or 'n/a'}",
            ids,
        ),
    }


# ── Main entrypoint ─────────────────────────────────────────────────────────

def _per_gene(gene: str, condition: Optional[str], client) -> dict:
    """Combine all three connectors for one gene. Each connector is independent
    and failure-isolated — one connector erroring out does not block the others."""
    record: dict = {"gene": gene}
    record.update(_ot_lookup(gene, condition, client))
    record.update(_chembl_lookup(gene, client))
    record.update(_trials_lookup(gene, condition, client))
    return record


def annotate_translational(
    hypothesis: dict,
    condition: Optional[str] = None,
    cache: Optional[dict] = None,
    client=None,
) -> dict:
    """
    Build a translational annotation for a CONFIRMED hypothesis.

    Args:
        hypothesis: the hypothesis dict (must contain 'genes' and/or 'evidence').
        condition: optional disease/condition string supplied by the user.
        cache: optional dict keyed by gene symbol → previous per-gene record.
               Used to skip re-querying unchanged confirmed axes across runs.
        client: optional httpx.Client (for testing). If None, a fresh one is built.

    Returns a dict {condition, retrieved_at, genes:[per-gene record], note}.
    Never raises — failures collapse into "not retrieved" sentinels.
    """
    if (hypothesis.get("status") or "").lower() != "confirmed":
        return {
            "condition": condition or "",
            "retrieved_at": _now_iso(),
            "genes": [],
            "note": "skipped: hypothesis is not CONFIRMED — translational annotation is reporting only",
        }

    if not _HTTPX_AVAILABLE:
        return {
            "condition": condition or "",
            "retrieved_at": _now_iso(),
            "genes": [],
            "note": "skipped: httpx not available",
        }

    genes = leading_genes_for_hypothesis(hypothesis, cap=MAX_LEADING_GENES)
    if not genes:
        return {
            "condition": condition or "",
            "retrieved_at": _now_iso(),
            "genes": [],
            "note": "no leading-edge genes available for annotation",
        }

    cache = cache or {}
    cache_used: list[str] = []
    fresh_queries = 0
    per_gene_records: list[dict] = []

    own_client = False
    try:
        if client is None:
            client = httpx.Client(headers={"User-Agent": "transcriptomic-agent/translational"})
            own_client = True

        for gene in genes:
            key = gene.upper()
            if key in cache and cache[key].get("condition", "") == (condition or ""):
                per_gene_records.append(dict(cache[key]["record"]))
                cache_used.append(key)
                continue
            try:
                rec = _per_gene(gene, condition, client)
            except Exception as e:
                logger.warning("translational lookup for %s failed: %s", gene, e)
                rec = {
                    "gene": gene,
                    "ot_tractability": "not retrieved",
                    "chembl_drugs": [],
                    "trials": [],
                    "provenance": _provenance("translational", f"gene:{gene}", [], error=str(e)),
                }
            per_gene_records.append(rec)
            fresh_queries += 1
    finally:
        if own_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    return {
        "condition": condition or "",
        "retrieved_at": _now_iso(),
        "genes": per_gene_records,
        "note": (
            f"{len(per_gene_records)} genes annotated "
            f"({fresh_queries} freshly retrieved, {len(cache_used)} from memory cache)"
        ),
        "cache_hits": cache_used,
    }


def build_translational_cache(knowledge_store: dict) -> dict:
    """
    Walk a knowledge store and extract any previously-stored translational
    annotations into a per-gene cache. Keyed by gene symbol (upper).

    Each cache value: {"condition": "...", "record": {per-gene record}}.
    The cache is used by annotate_translational to skip re-querying.
    """
    cache: dict = {}
    for entry in knowledge_store.get("entries") or []:
        ann = entry.get("translational_annotation") or {}
        cond = ann.get("condition", "")
        for rec in ann.get("genes") or []:
            gene = (rec.get("gene") or "").upper()
            if not gene:
                continue
            # Most-recent wins (entries are appended, last seen overrides).
            cache[gene] = {"condition": cond, "record": rec}
    return cache


# ── Report rendering ────────────────────────────────────────────────────────

def render_translational_markdown(annotation: dict) -> str:
    """
    Render the translational annotation block as Markdown for the report.

    Returns an empty string if there is nothing meaningful to show (so the
    report renderer can skip the subsection entirely).
    """
    if not annotation:
        return ""
    genes = annotation.get("genes") or []
    if not genes:
        # If we explicitly tried but found nothing, surface the reason.
        note = annotation.get("note") or ""
        return f"_Translational annotation: {note}_" if note else ""

    lines: list[str] = []
    lines.append("**Translational (external annotation — not part of the evidence gate)**")
    cond = annotation.get("condition") or ""
    if cond:
        lines.append(f"_Condition queried: {cond}_  ")
    lines.append(f"_Retrieved: {annotation.get('retrieved_at','')}_  ")
    if annotation.get("note"):
        lines.append(f"_{annotation['note']}_")
    lines.append("")

    for rec in genes:
        gene = rec.get("gene") or "?"
        ot_id = rec.get("ot_target_id") or ""
        ot_link = (
            f"[{ot_id}](https://platform.opentargets.org/target/{ot_id})"
            if ot_id else "—"
        )
        tract = rec.get("ot_tractability") or "—"
        assoc = rec.get("ot_assoc_score")
        assoc_str = (
            f"{assoc:.3f}" if isinstance(assoc, (int, float)) else "—"
        )
        assoc_disease = rec.get("ot_assoc_disease") or ""
        lines.append(f"- **{gene}** — Open Targets: {ot_link}")
        lines.append(
            f"  - tractability: {tract}"
            + (f"; association(disease={assoc_disease}): {assoc_str}" if assoc_disease else "")
        )

        drugs = rec.get("chembl_drugs") or []
        if drugs:
            lines.append("  - ChEMBL drugs:")
            for d in drugs:
                cid = d.get("chembl_id") or ""
                link = (
                    f"[{cid}](https://www.ebi.ac.uk/chembl/explore/compound/{cid})"
                    if cid else "—"
                )
                phase = d.get("max_phase")
                phase_str = f" phase={phase}" if phase is not None else ""
                lines.append(
                    f"    - {link} — {d.get('action_type','')} "
                    f"{d.get('mechanism_of_action','') or '(no mechanism)'}{phase_str}"
                )
        else:
            lines.append("  - ChEMBL drugs: none")

        trials = rec.get("trials") or []
        if trials:
            lines.append("  - ClinicalTrials:")
            for t in trials:
                nct = t.get("nct_id") or ""
                link = (
                    f"[{nct}](https://clinicaltrials.gov/study/{nct})"
                    if nct else "—"
                )
                phases = ", ".join(t.get("phases") or []) or "—"
                lines.append(
                    f"    - {link} — {t.get('status','')} ({phases}) — {t.get('title','')}"
                )
        else:
            lines.append("  - ClinicalTrials: none")

        prov = rec.get("provenance") or {}
        if isinstance(prov, dict) and prov.get("error"):
            lines.append(f"  - _connector error: {prov.get('connector','?')}: {prov['error']}_")
        lines.append("")

    return "\n".join(lines)
