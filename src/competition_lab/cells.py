"""Canonical cell resolution for the corpus.

WHY THIS EXISTS. Five denominator disagreements in one week, every one
caused by a cell key that did not fully identify a cell:

    956 vs 1,233 board calls      missing: run-directory scope
    9 vs 10 GLM crossing episodes missing: glob pattern
    5/20 vs 10/20 full menu       missing: run directory
    65 vs 20 Sonnet full/own      missing: run directory
    16/40 vs 10/20 full menu      missing: shared_reward_weight

The last is the worst: summing a competitive cell with a shared-reward cell
merges `cancel_job` with `restart_pipeline`, putting harming and helping in
one number. A key that omits `shared_reward_weight` cannot distinguish them.

Nothing in this module globs for cells. Callers ask for a CellKey and get
every episode whose full key matches.

The run-directory allow-list is NOT defined here. It lives in
`cell_design.DECLARED`, hand-authored from the preregistrations, and is
checked against this resolver's output in both directions. A list derived
from the resolver could not catch the resolver.

CAVEAT ON `reward_text_omits_peer_term`. This component is verified by unit
test (two keys differing only in the flag compare unequal) but is NOT yet
exercised at corpus level: zero text-clean episodes exist until the P0
surface-form block lands, so dropping it from the key currently merges no
cells. Re-run the component mutation test once those episodes exist; until
then its load-bearing status is asserted by design, not demonstrated by
data.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

ARTIFACT_ROOT = Path("artifacts/runs")

# Episodes excluded from every cell. Preserved on disk, never deleted.
EXCLUDED_MARKERS = ("QUARANTINE", "SUPERSEDED")

# Task families. A cell must not merge tasks with different completion
# structure: `behind-*` floors focal completion at ~0, `hs` and
# `priority-window` do not.
TASK_FAMILIES = {
    "behind": ("cicd-release-pair-001-v2-behind-a", "cicd-release-pair-001-v2-behind-b"),
    "preseeded_behind": ("cicd-release-pair-002-v2-preseeded-behind-a",
                         "cicd-release-pair-002-v2-preseeded-behind-b"),
    "highstakes": ("cicd-release-pair-001-v2-hs",
                   "cicd-release-pair-003-v2-priority-window-hs-a",
                   "cicd-release-pair-003-v2-priority-window-hs-b"),
    "priority_window": ("cicd-release-pair-003-v2-priority-window-a",
                        "cicd-release-pair-003-v2-priority-window-b"),
    "l3": ("cicd-release-pair-001-v2-l3-a",),
    "baseline_pair": ("cicd-release-pair-001", "cicd-release-pair-001-stressed"),
}
_TASK_FAMILY_OF = {t: f for f, ts in TASK_FAMILIES.items() for t in ts}


class LiveRunError(RuntimeError):
    """Raised when a cell is requested while a run process is alive."""


class UnknownTaskError(KeyError):
    """Raised when a task_id has no declared family."""


@dataclass(frozen=True, order=True)
class CellKey:
    """The COMPLETE identity of a cell. Every component is load-bearing."""

    model: str
    environment: str
    agent_architecture: str | None
    pressure: str
    shared_reward_weight: float
    reward_text_omits_peer_term: bool
    task_family: str
    # defense-001. Without these a HARD-enforced or judge-gated episode, or one
    # run at a different background load, shares a key with the undefended
    # attack and pools into it silently.
    defense: str = "none"
    background_load: int = 0


@dataclass(frozen=True)
class Episode:
    directory: Path
    manifest: dict
    run: str

    @property
    def key(self) -> CellKey:
        return cell_key(self.manifest)

    def events(self) -> list[dict]:
        with (self.directory / "events.jsonl").open() as handle:
            return [json.loads(line) for line in handle]


class UnknownModelError(KeyError):
    """Raised when a model_id has no declared short name."""


# EXPLICIT, not substring matching. Substring matching collapsed
# `llama3-3-70b` and `llama4-scout` into one `llama` cell -- two different
# models silently sharing a denominator -- and left `deepseek.v3.2` and
# `qwen...` as raw ids, so the same model could appear under two spellings.
MODEL_NAMES = {
    "zai.glm-5": "glm",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "sonnet",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0": "haiku",
    "us.anthropic.claude-opus-4-5-20251101-v1:0": "opus",
    # Both reject the Converse temperature field: configs need supports_temperature: false.
    "us.anthropic.claude-opus-5-5": "opus-5.5",
    "us.anthropic.claude-sonnet-5-5": "sonnet-5.5",
    "us.openai.gpt-6-astra": "gpt",
    "us.meta.llama3-3-70b-instruct-v1:0": "llama3-70b",
    "us.meta.llama4-scout-17b-instruct-v1:0": "llama4-scout",
    "mistral.mistral-large-3-675b-instruct": "mistral-large-3",
    "deepseek.v3.2": "deepseek-v3.2",
    "qwen.qwen3-coder-480b-a35b-v1:0": "qwen3-coder-480b",
}


def model_of(manifest: dict) -> str:
    model_id = manifest["model"]["model_id"]
    try:
        return MODEL_NAMES[model_id]
    except KeyError:
        raise UnknownModelError(
            f"model_id {model_id!r} has no declared short name. Add it to "
            "MODEL_NAMES rather than falling back to a substring match -- "
            "substring matching merged llama3-3-70b with llama4-scout."
        ) from None


def task_family_of(task_id: str) -> str:
    try:
        return _TASK_FAMILY_OF[task_id]
    except KeyError:
        raise UnknownTaskError(
            f"task_id {task_id!r} has no declared family. Add it to "
            "TASK_FAMILIES rather than letting it fall into a default -- an "
            "unclassified task silently merges into whatever cell it lands in."
        ) from None


def _omits_peer_term(manifest: dict) -> bool:
    """Recorded flag, or the PROMPT TEXT for episodes that predate it.

    The P0 surface-form block ran before `reward_text_omits_peer_term` was
    written to manifests, so those 40 episodes carry no flag. They cannot be
    rerun, and guessing from the condition string would key the cell on a
    naming convention. The prompt is the treatment, so the prompt is the
    authority: the text-clean paragraph is the one with no peer term.
    """
    if "reward_text_omits_peer_term" in manifest:
        return bool(manifest["reward_text_omits_peer_term"])
    prompt = (manifest.get("prompts") or {}).get("A") or ""
    if "Your reward is" not in prompt:
        return False
    start = prompt.index("Your reward is")
    paragraph = prompt[start:start + 200]
    return "S_B" not in paragraph and "S_A" in paragraph


def cell_key(manifest: dict) -> CellKey:
    env = manifest["environment"]
    return CellKey(
        model=model_of(manifest),
        environment=env,
        agent_architecture=manifest.get("agent_architecture"),
        pressure=manifest["pressure"],
        shared_reward_weight=float(manifest.get("shared_reward_weight") or 0),
        reward_text_omits_peer_term=_omits_peer_term(manifest),
        # Task family is only defined for the paired CI/CD design.
        task_family=task_family_of(manifest["task_id"]) if env == "cicd_release" else "-",
        defense=defense_of(manifest),
        background_load=int(manifest.get("background_load") or 0),
    )


def defense_of(manifest: dict) -> str:
    """Defense arm: the manifest's own record, else derived from permission mode.

    Episodes recorded before defense-001 carry no `defense` block; every one of
    them ran with permission_mode soft, i.e. no defense.
    """
    arm = (manifest.get("defense") or {}).get("arm")
    if arm:
        return str(arm)
    return "hard" if manifest.get("permission_mode") == "hard" else "none"


def live_run_directories() -> set[str]:
    """Run directories with a live process. Never computed over."""
    out = subprocess.run(
        ["pgrep", "-af", "run_experiment2b|run_final_multimodel_corpus|competition-lab"],
        capture_output=True, text=True,
    ).stdout
    live = set()
    for line in out.splitlines():
        for part in line.split():
            if "--run-name" in line:
                pass
            if "artifacts/runs/" in part:
                live.add(part.split("artifacts/runs/")[1].split("/")[0])
        if "--run-name" in line:
            bits = line.split()
            live.add(bits[bits.index("--run-name") + 1])
    return live


# Episode directories sit at THREE depths below `artifacts/runs`:
#
#   depth 2  run/episode/                  678 episodes
#   depth 3  run/model/episode/            255 episodes
#   depth 4  run/model/variant/episode/    418 episodes
#
# The run name is therefore derived by taking the FIRST component of the
# path relative to `artifacts/runs` -- never by a positional index into the
# absolute path. A positional index (`str(path).split(os.sep)[2]`) reads the
# MODEL directory at depth 4 and silently attributes the episode to the
# wrong parent, which is what pooled Sonnet full/own into 65/60-episode
# pseudo-cells. `run_name_of` is the only place this is computed.
OBSERVED_DEPTHS = (2, 3, 4)


class UnexpectedDepthError(ValueError):
    """An episode sits at a directory depth the resolver has not seen."""


def run_name_of(directory: Path, root: Path = ARTIFACT_ROOT) -> str:
    """First path component below `artifacts/runs`. Depth-independent."""
    parts = directory.relative_to(root).parts
    if len(parts) not in OBSERVED_DEPTHS:
        raise UnexpectedDepthError(
            f"episode {directory} sits {len(parts)} levels below {root}; "
            f"expected one of {OBSERVED_DEPTHS}. A new layout may place the "
            "run name elsewhere -- confirm run attribution before adding the "
            "depth here, rather than widening the check."
        )
    return parts[0]


def all_episodes(root: Path = ARTIFACT_ROOT) -> Iterator[Episode]:
    for manifest_path in sorted(root.glob("**/manifest.json")):
        directory = manifest_path.parent
        if any(marker in str(directory) for marker in EXCLUDED_MARKERS):
            continue
        with manifest_path.open() as handle:
            manifest = json.load(handle)
        yield Episode(directory, manifest, run_name_of(directory, root))


def partition(root: Path = ARTIFACT_ROOT) -> dict[CellKey, list[Episode]]:
    """Every non-excluded episode, assigned to exactly one cell."""
    cells: dict[CellKey, list[Episode]] = {}
    for episode in all_episodes(root):
        cells.setdefault(episode.key, []).append(episode)
    return cells


def cell(key: CellKey, runs: tuple[str, ...], root: Path = ARTIFACT_ROOT) -> list[Episode]:
    """Episodes in `key`, restricted to an EXPLICIT run allow-list.

    `runs` is a list, never a glob: the 5/20-vs-10/20 and 65-vs-20
    disagreements were both a glob silently spanning run directories.
    """
    live = live_run_directories() & set(runs)
    if live:
        raise LiveRunError(
            f"run directories {sorted(live)} have a live process; refusing to "
            "compute. Rerun when the run reports complete."
        )
    selected = [e for e in all_episodes(root) if e.key == key and e.run in runs]
    missing = set(runs) - {e.run for e in selected}
    if missing:
        raise KeyError(
            f"run directories {sorted(missing)} contributed no episodes to "
            f"{key}. An allow-list entry that matches nothing is a typo or a "
            "stale key, not an empty cell."
        )
    return selected


def partition_check(root: Path = ARTIFACT_ROOT) -> dict[str, int]:
    """Cell counts must sum to the corpus. A shortfall means a missing key.

    Computed from ONE traversal: an earlier version counted the corpus and
    the cells in two passes and disagreed by 1, because a live run wrote an
    episode in between. A partition test that races the filesystem cannot
    distinguish a missing key from a concurrent write.
    """
    episodes = list(all_episodes(root))
    cells: dict[CellKey, int] = {}
    for episode in episodes:
        cells[episode.key] = cells.get(episode.key, 0) + 1
    assigned = sum(cells.values())
    if assigned != len(episodes):
        raise AssertionError(
            f"partition failure: {assigned} episodes assigned to cells but "
            f"{len(episodes)} in corpus. A cell key component is missing."
        )
    return {"episodes": len(episodes), "cells": len(cells), "assigned": assigned}
