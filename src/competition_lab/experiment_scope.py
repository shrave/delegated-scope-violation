"""Experiment 1 episode selection, with an independent structural guard.

TWO SOURCES THAT MUST AGREE, NEITHER DERIVED FROM THE OTHER.

  semantic:   select by CELL through the resolver -- an episode is in
              Experiment 1 because of what it is (architecture, environment,
              run), not where it sits on disk.
  structural: the depth-2 glob that paper_tables.py has always used.

The glob is NOT the selection mechanism any more, and it is NOT redundant.
It is the guard. Its exclusion is by DEPTH, not by cell, so it isolates
Experiment 1 today only because final-paper runs happen to be depth 2 while
2A and 2B are depth 3 and 4. Nothing enforces that. `sonnet-post-tiebreak-
20pair` is already 40 compute episodes at depth 3, invisible to the glob for
no reason but its layout.

Keeping both and asserting equality means a layout change breaks the build
instead of silently moving a denominator.
"""

from __future__ import annotations

import json
from pathlib import Path

from competition_lab import cells

# WHAT "EXPERIMENT 1 SCOPE" MEANS HERE.
#
# paper_tables.py does not filter by architecture. It takes every episode in
# scope and assigns each a CAMPAIGN LABEL, reporting modified-interface
# pilots (the SOC option-generation and architecture pilots) as separate
# labelled rows rather than excluding them. Separation happens at LABELLING,
# not at selection.
#
# So the semantic selector must exclude exactly the modified-interface
# EXPERIMENTS -- 2A and 2B, which are never pooled with Experiment 1 rates
# and have their own table scripts -- and nothing else. An earlier version
# of this file excluded by architecture and wrongly flagged the SOC
# option-generation pilot, which the tables handle explicitly.
# `experiment1-completion-` runs are the paper's Experiment 1 menu study, run
# in the 2B modified-interface setting; the name says "experiment1" but they
# are not base-Experiment-1 episodes and have their own table script.
NON_E1_RUN_PREFIXES = ("exp2-", "experiment2-", "experiment2b-", "exploratory-",
                       "experiment1-completion-")

# Modified-interface architectures (2A option scaffold, 2B menus). An episode
# with one of these is never base Experiment 1, WHATEVER its run is called:
# selection rejects it and the base tables refuse it (assert_no_modified_
# interface). Other non-`base` architectures (telemetry_aware, the SOC
# rationale/option-generation pilots) ARE in base-E1 scope and are separated
# by campaign label in paper_tables.py, so this is a denylist, not `== base`.
MODIFIED_INTERFACE_ARCHITECTURES = frozenset({
    "neutral_tool_affordance_menu_probe",
    "null_menu_control",
    "own_resource_only_menu_control",
    "padded_own_resource_menu_control",
    "labelled_owner_menu_probe",
    "option_structured_two_phase",
})


# KNOWN DIVERGENCE, recorded rather than suppressed.
#
# `sonnet-post-tiebreak-20pair` is 40 episodes (20 matched pairs, 20/20
# complete) at DEPTH 3. It is a valid, preregistered, fully analysed run --
# `docs/sonnet_post_tiebreak_20pair_review.md`, pre-analysis plan fixed
# before collection -- and it is referenced by NO table script. It is
# invisible to paper_tables.py for one reason: its layout.
#
# This is the exact failure the guard exists to catch, and it was already
# live when the guard was written. It is waived here so the guard can be
# committed green, NOT because it is acceptable. Whether those 40 episodes
# belong in the Experiment 1 compute tables is a scientific question for the
# reviewer, not a layout question to be silently resolved by a glob.
#
# Removing this waiver is the fix. Widening the glob is not.
# Both are VALID runs at a depth the glob cannot see:
#   sonnet-post-tiebreak-20pair  40 eps, depth 3, docs/sonnet_post_tiebreak_20pair_review.md
#   team-rerun-v2-001           120 eps, depth 4, the team-arm rerun (6/120)
# Neither is referenced by any table script.
KNOWN_DIVERGENT_RUNS = frozenset({
    "sonnet-post-tiebreak-20pair",
    "team-rerun-v2-001",
})


class ExperimentScopeError(AssertionError):
    """Semantic and structural selection of Experiment 1 disagree."""


class ModifiedInterfaceInBaseTablesError(AssertionError):
    """A modified-interface episode reached the base Experiment 1 path."""


def is_experiment1(episode: cells.Episode) -> bool:
    """Semantic membership: by cell, not by directory depth or run name alone."""
    if episode.manifest.get("agent_architecture") in MODIFIED_INTERFACE_ARCHITECTURES:
        return False
    return not episode.run.startswith(NON_E1_RUN_PREFIXES)


def assert_no_modified_interface(episode_dirs) -> None:
    """Refuse the base-E1 episode list if any manifest has a menu/option architecture."""
    leaked = []
    for directory in episode_dirs:
        manifest = json.loads((Path(directory) / "manifest.json").read_text())
        if manifest.get("agent_architecture") in MODIFIED_INTERFACE_ARCHITECTURES:
            leaked.append(f"{directory} ({manifest.get('agent_architecture')})")
    if leaked:
        raise ModifiedInterfaceInBaseTablesError(
            f"{len(leaked)} modified-interface episode(s) reached the base "
            f"Experiment 1 tables: {leaked[:5]}")


def semantic_set(root: Path = cells.ARTIFACT_ROOT) -> set[Path]:
    return {e.directory for e in cells.all_episodes(root) if is_experiment1(e)}


def structural_set(root: Path = cells.ARTIFACT_ROOT) -> set[Path]:
    """The depth-2 glob, computed independently of the resolver."""
    return {
        p.parent
        for p in root.glob("*/*/manifest.json")
        if not any(m in str(p) for m in cells.EXCLUDED_MARKERS)
    }


def check(root: Path = cells.ARTIFACT_ROOT) -> dict[str, int]:
    """Fail loudly, naming the episodes, if the two sources disagree."""
    semantic = {p for p in semantic_set(root)
                if cells.run_name_of(p, root) not in KNOWN_DIVERGENT_RUNS}
    structural = structural_set(root)
    if semantic != structural:
        only_semantic = sorted(str(p) for p in semantic - structural)
        only_structural = sorted(str(p) for p in structural - semantic)
        raise ExperimentScopeError(
            "Experiment 1 selection disagrees between the resolver and the "
            "depth-2 glob.\n"
            f"  resolver only ({len(only_semantic)}): {only_semantic[:10]}\n"
            f"  glob only ({len(only_structural)}): {only_structural[:10]}\n"
            "An episode in 'resolver only' is an Experiment 1 episode written "
            "at an unexpected depth -- the glob would silently drop it. An "
            "episode in 'glob only' is a modified-interface episode that "
            "would be pooled into Experiment 1 rates."
        )
    waived = sum(1 for e in cells.all_episodes(root)
                 if e.run in KNOWN_DIVERGENT_RUNS)
    return {"experiment1_episodes": len(semantic), "waived_episodes": waived}
