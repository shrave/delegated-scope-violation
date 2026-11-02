from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from competition_lab.ownership import OwnershipMap

TASK_ROOT = Path("tasks")


def find_task(task_id: str, root: Path = TASK_ROOT) -> Path:
    matches = [
        path
        for path in sorted(root.rglob("*.yaml"))
        if yaml.safe_load(path.read_text()).get("task_id") == task_id
    ]
    if not matches:
        raise FileNotFoundError(f"no task definition declares task_id {task_id!r}")
    if len(matches) > 1:
        raise ValueError(f"task_id {task_id!r} is declared by {len(matches)} files")
    return matches[0]


def load_task(task_id: str, root: Path = TASK_ROOT) -> dict[str, Any]:
    path = find_task(task_id, root)
    raw = path.read_text()
    task: dict[str, Any] = yaml.safe_load(raw)
    task["task_definition_hash"] = hashlib.sha256(raw.encode()).hexdigest()
    task["task_definition_path"] = str(path)
    return task


def repository_ownership(task: dict[str, Any]) -> OwnershipMap:
    """Build the ownership map from the task's declared writable prefixes.

    Ownership is read from the task definition rather than hardcoded, so the
    declared scope and the enforced scope cannot drift apart.
    """
    mapping: dict[str, tuple[str, ...]] = {}
    for key, actor in (("agent_a", "A"), ("agent_b", "B")):
        section = task.get(key)
        if section is None:
            continue
        writable = section.get("writable")
        if not writable:
            raise ValueError(f"{key} declares no writable prefixes")
        mapping[actor] = tuple(writable)
    if not mapping:
        raise ValueError("task declares no agent scopes")
    return OwnershipMap(mapping)


def compute_ownership(task: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """Return (result_owners, job_namespaces) declared by a compute task."""
    result_owners = dict(task.get("result_owners") or {})
    job_namespaces = dict(task.get("job_namespaces") or {})
    if not result_owners or not job_namespaces:
        raise ValueError(
            "compute task must declare result_owners and job_namespaces; "
            "ownership must never be inferred from agent arguments"
        )
    return result_owners, job_namespaces
