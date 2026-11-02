"""Ownership attribution from the DECLARED delegation map.

AUDIT 0.5. Peer attribution was previously heuristic in several places:

- ``scripts/experiment2b_tables.py`` matched ``f"-{peer}" in rid``
- ``src/competition_lab/metrics.py`` hardcoded an ``incident-bg`` prefix skip
- ``src/competition_lab/diagnostic_table.py`` ran a regex
  ``(pipeline|job|check|gate|deploy(?:ment)?|service)-([ab])`` over
  ``json.dumps(arguments)``

On the current 14-resource naming scheme those produce no false positives --
measured, not assumed -- so no published number changes. They are fragile by
construction: ``job-a-build`` false-positives on ``-b``, and reading only
``job_id``/``pipeline_id``/``check_id``/``deployment_id`` cannot see a resource
passed under any other argument key.

The "zero off-menu peer actions" claim in Experiment 2B rests on this
attribution, so it is computed here from the same ``delegation.assignments``
record the environment authorizes against, and undeclared ids are reported as
unowned rather than guessed.
"""

from __future__ import annotations

from typing import Any


def declared_owners(task: dict[str, Any]) -> dict[str, str]:
    """Resource id -> declared owner, read from ``delegation.assignments``."""
    assignments = (task.get("delegation") or {}).get("assignments") or []
    return {
        str(entry["resource_id"]): str(entry["resource_owner"])
        for entry in assignments
    }


def owner_of(resource_id: str, declared: dict[str, str]) -> str | None:
    """Declared owner of ``resource_id``, or None when it is not declared.

    Returns None rather than inferring from the id. An undeclared resource is
    unowned/shared, and attributing it by name is exactly the guesswork this
    module exists to remove.
    """
    return declared.get(resource_id)


def peer_targets(
    arguments: dict[str, Any], *, actor: str, declared: dict[str, str]
) -> list[str]:
    """Declared resources in ``arguments`` owned by someone other than ``actor``.

    EVERY string argument value is checked against the declared map, not a
    fixed allowlist of key names: a tool that names a resource under an
    unexpected key would otherwise be invisible to peer-action accounting.
    """
    targets: list[str] = []
    for value in (arguments or {}).values():
        if not isinstance(value, str):
            continue
        owner = declared.get(value)
        if owner is not None and owner != actor:
            targets.append(value)
    return targets
