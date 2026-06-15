"""
Multi-tenant memory store for the AI-as-PI agent.

All cross-run knowledge is scoped by `(user_id, project_id)`. A single global
file would, in a multi-user setting, (a) leak one user's findings into
another's runs and (b) collide on generic group labels ("tumor"/"normal")
across unrelated projects.

`MemoryStore` is the abstract interface that the runner depends on. The current
implementation, `FileMemoryStore`, persists each namespace as a JSON file at
`<root>/<user_id>/<project_id>/knowledge.json`. A future `DbMemoryStore`
(per-tenant rows) can be swapped in with no call-site changes.

A namespaced run reads and writes ONLY its own `(user_id, project_id)` slot.
No process ever reads another namespace. There is no global knowledge file.

There is a separate, optional `shared`/known-biology namespace hook reserved
for future cross-study knowledge — it is read-only, opt-in, and never
auto-merged into a private namespace. Not active yet.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Iterable

from .memory import (
    _empty_store,
    load_knowledge,
    save_knowledge,
    merge_claims,
)

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_ROOT = "memory"
DEFAULT_USER_ID = "local"
DEFAULT_PROJECT_ID = "default"
SHARED_NAMESPACE = "shared"  # reserved, read-only hook for future cross-study layer


_SAFE_ID = re.compile(r"[^A-Za-z0-9_.\-]+")


def _safe_segment(s: str, fallback: str) -> str:
    """Sanitise an id into a filesystem-safe path segment."""
    s = (s or "").strip()
    if not s:
        return fallback
    cleaned = _SAFE_ID.sub("_", s)
    return cleaned or fallback


def derive_project_id(datasets: list, deg_datasets: dict | None, mappings: dict | None) -> str:
    """
    Deterministic fingerprint of the dataset/group context used when the
    caller does not pass an explicit project_id.

    Hashes sorted dataset names + sorted unique canonical group labels +
    sorted DEG comparison pairs. The same project context → the same id,
    regardless of upload order. No biology is encoded — just identifiers.
    """
    deg_datasets = deg_datasets or {}
    mappings = mappings or {}

    raw_names = sorted({(ds.get("name") or "").strip() for ds in (datasets or [])})
    raw_names += sorted({(name or "").strip() for name in deg_datasets.keys()})

    raw_groups: set[str] = set()
    for ds in datasets or []:
        for g in ds.get("groups") or []:
            raw_groups.add(str(g).strip())
    raw_comparisons: set[str] = set()
    for ds in deg_datasets.values():
        for comp in ds.get("comparisons") or []:
            a, b = sorted([(comp.get("groupA") or "").strip(), (comp.get("groupB") or "").strip()])
            if a or b:
                raw_comparisons.add(f"{a}|{b}")

    payload = "||".join([
        ";".join(n for n in raw_names if n),
        ";".join(sorted(g for g in raw_groups if g)),
        ";".join(sorted(raw_comparisons)),
    ])
    if not payload.strip("|"):
        return DEFAULT_PROJECT_ID
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"p_{digest}"


class MemoryStore(ABC):
    """
    Abstract per-tenant knowledge store. Implementations MUST keep each
    `(user_id, project_id)` slot fully isolated.
    """

    @abstractmethod
    def get(self, user_id: str, project_id: str) -> dict:
        """Return the knowledge dict for the namespace, or an empty store."""

    @abstractmethod
    def merge(
        self,
        user_id: str,
        project_id: str,
        claims: list[dict],
        run_meta: dict,
    ) -> list[dict]:
        """
        Merge `claims` into the namespace and persist atomically.
        Returns any direction-flip contradictions surfaced during merge.
        """


class FileMemoryStore(MemoryStore):
    """File-backed implementation. Each namespace lives in its own JSON file."""

    def __init__(self, root: str = DEFAULT_MEMORY_ROOT):
        self.root = root

    def _path(self, user_id: str, project_id: str) -> str:
        user_seg = _safe_segment(user_id, DEFAULT_USER_ID)
        # Never let a caller resolve to the shared namespace through user_id.
        if user_seg == SHARED_NAMESPACE:
            user_seg = f"_{user_seg}"
        proj_seg = _safe_segment(project_id, DEFAULT_PROJECT_ID)
        return os.path.join(self.root, user_seg, proj_seg, "knowledge.json")

    def get(self, user_id: str, project_id: str) -> dict:
        path = self._path(user_id, project_id)
        if not os.path.exists(path):
            return _empty_store()
        return load_knowledge(path)

    def merge(
        self,
        user_id: str,
        project_id: str,
        claims: list[dict],
        run_meta: dict,
    ) -> list[dict]:
        path = self._path(user_id, project_id)
        knowledge = self.get(user_id, project_id)
        updated, contradictions = merge_claims(knowledge, claims, run_meta)
        save_knowledge(updated, path)
        return contradictions


# ── Shared / known-biology namespace (read-only, opt-in, not active) ─────────
# Reserved for a future cross-study layer. The current code does not auto-merge
# it into any user's private namespace and the runner does not call it. Kept
# here so the storage layout doesn't have to be retrofitted later.
def load_shared_knowledge(root: str = DEFAULT_MEMORY_ROOT) -> dict:
    """Load the shared/known-biology namespace if present. Never auto-merged."""
    path = os.path.join(root, SHARED_NAMESPACE, "knowledge.json")
    if not os.path.exists(path):
        return _empty_store()
    return load_knowledge(path)
