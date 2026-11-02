"""Experimental arm resolution. The single definition of which arm an episode
belongs to.

WHY THIS EXISTS
---------------
There was no arm field. `analysis.primary_analysis` subset on
`pressure in {P0, P4}` and grouped by `pressure` -- but EVERY team and
high-stakes manifest carries `pressure: "P0"`, with the arm actually encoded
in `shared_reward_weight` (1.0 for team, 0 otherwise). Grouping on pressure
therefore pools three distinct arms into one "P0" stratum.

Measured on GPT CI/CD: team 7/20, P0 0/20 and high-stakes 0/20 collapse into
7/60 = 11.7%, which is then compared against P4 = 0/20 -- REVERSING the
direction of the reported effect. The arm the paper reports as the treatment
becomes part of the control.

Run-directory names cannot substitute: `final-paper-cicd-sonnet-nonp4-001`
holds both srw=0 and srw=1.0 episodes, so one directory spans two arms.
"""
from __future__ import annotations

from typing import Any

ARMS = ("P0", "P4", "team", "highstakes")


def arm_of(manifest: dict[str, Any]) -> str:
    """-> one of ARMS.

    Resolution order matters. `shared_reward_weight` is checked FIRST because
    a team episode also carries pressure P0, so testing pressure first would
    silently classify every team episode as a control.
    """
    srw = manifest.get("shared_reward_weight") or 0
    try:
        srw = float(srw)
    except (TypeError, ValueError):
        srw = 0.0
    if srw > 0:
        return "team"

    if str(manifest.get("pressure") or "") == "P4":
        return "P4"

    # P0 and high-stakes are both independent-reward controls at pressure P0;
    # only the task difficulty differs, and that is carried in the condition.
    condition = str(manifest.get("condition") or "")
    experiment = str(manifest.get("experiment_id") or "")
    if "highstakes" in condition or "highstakes" in experiment:
        return "highstakes"
    return "P0"


def arm_is_treatment(arm: str) -> bool:
    """P0 is the control; everything else is a treatment."""
    return arm in ("P4", "team", "highstakes")
