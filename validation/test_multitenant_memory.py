"""
Verify multi-tenant memory isolation:
- two projects under the same user never cross-read
- two users never cross-read
- re-running the same (user, project) does load prior knowledge
- swapping FileMemoryStore for a stub DbMemoryStore needs no runner changes
"""
from __future__ import annotations

import os
import tempfile
from copy import deepcopy

from backend.agent.memory_store import (
    FileMemoryStore, MemoryStore, derive_project_id, DEFAULT_PROJECT_ID,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

CLAIM_TUMOR_UP_TP53 = {
    "claim": {"pair": "tumor vs normal", "item": "TP53", "direction": "UP", "in_group": "tumor"},
    "verdict": "confirmed",
    "evidence_summary": {"method_families": ["deg_replication", "enrichment"], "n_datasets": 2, "best_fdr": 1e-6},
    "hypothesis_id": "H1",
    "hypothesis_text": "TP53 up in tumor",
}
CLAIM_TUMOR_DN_TP53 = {
    **deepcopy(CLAIM_TUMOR_UP_TP53),
    "claim": {"pair": "tumor vs normal", "item": "TP53", "direction": "DOWN", "in_group": "tumor"},
}
RUN_META = {"run_id": "test_run", "datasets": ["dsA"], "groups": ["tumor", "normal"], "model": "test"}


def _check(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


# ── 1. File layout: each (user, project) gets its own file ───────────────────

def test_file_isolation(root: str) -> None:
    print("== test_file_isolation ==")
    store = FileMemoryStore(root=root)

    store.merge("alice", "projA", [CLAIM_TUMOR_UP_TP53], RUN_META)
    store.merge("alice", "projB", [CLAIM_TUMOR_DN_TP53], RUN_META)
    store.merge("bob",   "projA", [], RUN_META)

    p_alice_A = os.path.join(root, "alice", "projA", "knowledge.json")
    p_alice_B = os.path.join(root, "alice", "projB", "knowledge.json")
    p_bob_A   = os.path.join(root, "bob",   "projA", "knowledge.json")

    _check(os.path.exists(p_alice_A), "alice/projA file exists")
    _check(os.path.exists(p_alice_B), "alice/projB file exists")
    _check(os.path.exists(p_bob_A),   "bob/projA file exists")
    _check(not os.path.exists(os.path.join(root, "knowledge.json")),
           "no global knowledge.json was created at root")


# ── 2. Same group labels in different projects do not contaminate ────────────

def test_no_cross_read(root: str) -> None:
    print("== test_no_cross_read ==")
    store = FileMemoryStore(root=root)

    # alice/projA has TP53 UP, alice/projB has TP53 DOWN — same canonical pair,
    # same item. If we leaked across projects we'd see both.
    a = store.get("alice", "projA")["entries"]
    b = store.get("alice", "projB")["entries"]
    bob = store.get("bob", "projA")["entries"]

    _check(len(a) == 1 and a[0]["claim"]["direction"] == "UP",
           "alice/projA only sees its UP entry, not projB's DOWN")
    _check(len(b) == 1 and b[0]["claim"]["direction"] == "DOWN",
           "alice/projB only sees its DOWN entry, not projA's UP")
    _check(len(bob) == 0, "bob/projA sees nothing from alice/*")


# ── 3. Re-running the same namespace accumulates and detects flips ───────────

def test_rerun_accumulates(root: str) -> None:
    print("== test_rerun_accumulates ==")
    store = FileMemoryStore(root=root)

    # Confirm TP53 UP a second time in alice/projA → support_count should grow.
    contradictions = store.merge("alice", "projA", [CLAIM_TUMOR_UP_TP53], RUN_META)
    _check(contradictions == [], "no contradictions on same-direction re-confirm")

    entry = store.get("alice", "projA")["entries"][0]
    _check(entry["support_count"] >= 2, f"support_count incremented (got {entry['support_count']})")

    # Now push the opposite direction — must flag a contradiction and NOT
    # overwrite the stored UP direction.
    contradictions = store.merge("alice", "projA", [CLAIM_TUMOR_DN_TP53], RUN_META)
    _check(len(contradictions) == 1, "flip surfaces exactly one contradiction")
    entry = store.get("alice", "projA")["entries"][0]
    _check(entry["claim"]["direction"] == "UP", "majority direction (UP) preserved after flip")
    _check(entry["contradiction_count"] == 1, "contradiction_count incremented")


# ── 4. Stub DbMemoryStore — drop-in proves the abstraction ───────────────────

class _InMemoryStub(MemoryStore):
    """Pretend per-tenant DB. Swap-in must require zero runner changes."""
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict] = {}

    def get(self, user_id, project_id):
        return self._rows.get((user_id, project_id), {"version": 1, "entries": []})

    def merge(self, user_id, project_id, claims, run_meta):
        from backend.agent.memory import merge_claims
        cur = self.get(user_id, project_id)
        updated, contradictions = merge_claims(cur, claims, run_meta)
        self._rows[(user_id, project_id)] = updated
        return contradictions


def test_stub_db_is_drop_in() -> None:
    print("== test_stub_db_is_drop_in ==")
    stub = _InMemoryStub()
    stub.merge("u1", "p1", [CLAIM_TUMOR_UP_TP53], RUN_META)
    stub.merge("u1", "p2", [CLAIM_TUMOR_DN_TP53], RUN_META)

    p1 = stub.get("u1", "p1")["entries"]
    p2 = stub.get("u1", "p2")["entries"]
    _check(len(p1) == 1 and p1[0]["claim"]["direction"] == "UP", "stub: p1 isolated UP")
    _check(len(p2) == 1 and p2[0]["claim"]["direction"] == "DOWN", "stub: p2 isolated DOWN")
    _check(stub.get("u2", "p1")["entries"] == [], "stub: unknown user is empty")


# ── 5. derive_project_id is deterministic and order-independent ──────────────

def test_derive_project_id_deterministic() -> None:
    print("== test_derive_project_id_deterministic ==")
    dsA = {"name": "GSE_A", "groups": ["tumor", "normal"]}
    dsB = {"name": "GSE_B", "groups": ["normal", "tumor"]}
    id1 = derive_project_id([dsA, dsB], {}, {})
    id2 = derive_project_id([dsB, dsA], {}, {})  # different order, same content
    _check(id1 == id2, f"id stable under input ordering ({id1} == {id2})")
    _check(id1 != DEFAULT_PROJECT_ID, "non-empty context → non-default id")

    # Different content → different id
    dsC = {"name": "GSE_C", "groups": ["case", "control"]}
    id3 = derive_project_id([dsC], {}, {})
    _check(id3 != id1, "different content → different id")

    # Empty context falls back to default
    id_default = derive_project_id([], {}, {})
    _check(id_default == DEFAULT_PROJECT_ID, "empty context → default id")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "memory")
        test_file_isolation(root)
        test_no_cross_read(root)
        test_rerun_accumulates(root)
    test_stub_db_is_drop_in()
    test_derive_project_id_deterministic()
    print("\nAll multi-tenant isolation tests passed.")


if __name__ == "__main__":
    main()
