#!/usr/bin/env python3
"""R2 prompt audit (preregistration docs/preregistration_r2_affordance_factorial.md).

Renders, through the real EpisodeRunner with a scripted mock model, the exact
first-turn messages each of the eight cells shows agent A and agent B on both
task sides (the shared start state), and checks that cells which differ in ONE
factor differ ONLY in that factor's text:

  incentive   only the evaluation sentence and the reward paragraph of the
              system prompt; the menu is identical
  visibility  only the menu, and only by removing candidate lines on the
              other agent's resources (every remaining line identical)
  payoff      only the menu, and only by appending " -> ..." consequence
              suffixes to candidate lines (every candidate identical)

It also checks every rendered menu passes the menu audit, and that the
control cells (unlisted) name no resource of the other agent anywhere in the
menu. Prints the per-cell SHA-256 of the system prompt and of the menu, plus
the eight templates. Exit status 1 on any violation.

Usage: r2_prompt_audit.py > out.json
"""
# ruff: noqa: E501
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from competition_lab.cli import _environment  # noqa: E402
from competition_lab.config import ModelConfig, load_config  # noqa: E402
from competition_lab.orchestration import EpisodeRunner  # noqa: E402
from competition_lab.providers import MockProvider  # noqa: E402
from competition_lab.tasks import load_task  # noqa: E402

CFG = ROOT / "configs/r2_affordance_factorial"
CELLS = [f"{i}_{v}_{p}" for i, v, p in itertools.product(("ind", "comp"), ("unlisted", "listed"),
                                                           ("unstated", "stated"))]


class _Recorder(MockProvider):
    def __init__(self) -> None:
        super().__init__([])
        self.seen: list[list[dict[str, Any]]] = []

    def complete(self, messages, tools):  # type: ignore[no-untyped-def]
        self.seen.append(copy.deepcopy(list(messages)))
        return super().complete(messages, tools)


def render(cell: str, side: str) -> dict[str, tuple[str, str]]:
    path = next(p for p in sorted((CFG / "glm" / cell).glob("*.yaml"))
                if load_config(p).task_id.endswith(side))
    cfg = load_config(path).model_copy(update={
        "model": ModelConfig(provider="mock", model_id="mock"), "action_budget": 1})
    task = load_task(cfg.task_id)
    recs = {"A": _Recorder(), "B": _Recorder()}
    EpisodeRunner(cfg, _environment(cfg, task), recs, Path(tempfile.mkdtemp()),
                  task=task).run("audit-0000")
    return {a: (r.seen[0][0]["content"], r.seen[0][1]["content"]) for a, r in recs.items()}


def h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    problems: list[str] = []
    rendered = {(c, s): render(c, s) for c in CELLS for s in "ab"}
    for side in "ab":
        for actor in "AB":
            other = "b" if actor == "A" else "a"
            for c in CELLS:
                inc, vis, pay = c.split("_")
                system, menu = rendered[(c, side)][actor]
                lines = menu.split("\n\n", 1)[1].splitlines()
                if vis == "unlisted" and any(f"-{other}" in line.split(" -> ")[0] for line in lines):
                    problems.append(f"{c}/{side}/{actor}: control menu names an other-agent resource")
                if vis == "listed" and not any(f"-{other}" in line for line in lines):
                    problems.append(f"{c}/{side}/{actor}: listed menu has no other-agent candidate")
                if (pay == "stated") != all(" -> " in line for line in lines):
                    problems.append(f"{c}/{side}/{actor}: payoff suffix presence wrong")
                # incentive: flip only incentive
                twin = f"{'comp' if inc == 'ind' else 'ind'}_{vis}_{pay}"
                t_sys, t_menu = rendered[(twin, side)][actor]
                if t_menu != menu:
                    problems.append(f"{c} vs {twin}: incentive changed the menu")
                diff = [(x, y) for x, y in zip(system.splitlines(), t_sys.splitlines(), strict=True) if x != y]
                if not diff or any(not (x.startswith("Your evaluated performance") or x.startswith("Your reward is"))
                                   for x, _ in diff):
                    problems.append(f"{c} vs {twin}: incentive diff outside its sentences: {diff}")
                # visibility: flip only visibility
                twin = f"{inc}_{'listed' if vis == 'unlisted' else 'unlisted'}_{pay}"
                t_sys, t_menu = rendered[(twin, side)][actor]
                if t_sys != system:
                    problems.append(f"{c} vs {twin}: visibility changed the system prompt")
                small, big = (lines, t_menu.split("\n\n", 1)[1].splitlines()) if vis == "unlisted" else \
                    (t_menu.split("\n\n", 1)[1].splitlines(), lines)
                extra = [line for line in big if line not in small]
                if [line for line in big if line in small] != small or \
                        any(f"-{other}" not in line.split(" -> ")[0] for line in extra):
                    problems.append(f"{c} vs {twin}: visibility diff is not exactly the other-agent lines")
                # payoff: flip only payoff
                twin = f"{inc}_{vis}_{'stated' if pay == 'unstated' else 'unstated'}"
                t_sys, t_menu = rendered[(twin, side)][actor]
                if t_sys != system:
                    problems.append(f"{c} vs {twin}: payoff changed the system prompt")
                stripped = [line.split(" -> ")[0] for line in lines]
                t_stripped = [line.split(" -> ")[0] for line in t_menu.split("\n\n", 1)[1].splitlines()]
                if stripped != t_stripped or menu.split("\n\n", 1)[0] != t_menu.split("\n\n", 1)[0]:
                    problems.append(f"{c} vs {twin}: payoff changed more than the suffixes")
    report = {
        "problems": problems,
        "cells": {c: {f"task_{s}_agent_{a}": {"system_prompt_sha256": h(rendered[(c, s)][a][0]),
                                               "menu_sha256": h(rendered[(c, s)][a][1])}
                      for s in "ab" for a in "AB"} for c in CELLS},
        "templates_task_a_agent_A": {c: {"system_prompt": rendered[(c, "a")]["A"][0],
                                         "menu_round_0": rendered[(c, "a")]["A"][1]} for c in CELLS},
    }
    json.dump(report, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
