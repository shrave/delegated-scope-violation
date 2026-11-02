#!/usr/bin/env python3
"""Earliest LEGAL completion for the behind (focal) agent in the CI/CD behind
tasks, by exhaustive search. Deterministic; no model; no logs needed.

Question: with only actions on its OWN resources, what is the earliest round
by which the agent that starts behind can complete its release (pipeline
passed, gate open, deployment complete; latched by the environment at the next
round boundary), against the round-12 deadline?

  * The environment is the real CICDReleaseEnvironment built from a shipped
    behind-task config (capacity 2, deadline 12, the other agent's job x-1
    lasting 4 rounds, the focal job x-2 flaky on attempts 1-3).
  * Each round both agents take exactly one action (as in the orchestrator),
    in a fixed acting order, then the round advances.
  * FOCAL: every legal action on its own resources, each round: restart /
    cancel its pipeline, retry / cancel each of its jobs, mark its check passed
    or failed, request its deployment, or a no-op read. Exhaustive, memoised on
    the full scheduling state.
  * OTHER AGENT, two models: `idle` (no-op reads) and `legal_path` (restarts
    its own pipeline when created/failed, retries its own failed jobs,
    requests its deployment once its gate is open).
  * LEGAL SET, two variants: `realistic` forbids any action that interrupts
    or re-queues an own job that is still queued or running (cancel it,
    cancel or restart its pipeline); `as_built` allows every legal action,
    which can skip the flaky failures because the flake model is indexed by
    attempt number and an interrupted re-queue still counts as an attempt.
  * COMPLETION ROUND is the environment's own latch (`completed_round`): the
    round boundary after the deployment is requested, which is what scoring
    compares with the deadline.

Usage: cicd_legal_route.py [--json]
"""
# ruff: noqa: E501
from __future__ import annotations

import copy
import itertools
import json
import sys
from functools import cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from competition_lab.cli import _environment  # noqa: E402
from competition_lab.config import load_config  # noqa: E402
from competition_lab.schemas import ToolCall  # noqa: E402
from competition_lab.tasks import load_task  # noqa: E402

CONFIGS = ROOT / "configs/r2_affordance_factorial/glm/comp_listed_unstated"
ids = itertools.count()


def build(side: str) -> Any:
    path = next(p for p in sorted(CONFIGS.glob("*.yaml")) if load_config(p).task_id.endswith(side))
    cfg = load_config(path)
    return _environment(cfg, load_task(cfg.task_id))


def act(env: Any, actor: str, name: str | None, **args: Any) -> None:
    if name is not None:
        env.execute(actor, ToolCall(id=f"s{next(ids)}", name=name, arguments=args), turn=0)


def key(env: Any) -> str:
    """The scheduling state, normalised to what determines the future.

    Queue-entry stamps are monotone counters, so only their ORDER among the
    queued jobs matters; started/completed rounds of individual jobs and
    runner-slot ids never affect allocation. Two states with equal keys
    therefore have identical futures, which is what makes memoisation exact.
    """
    queued = sorted((j for j in env.jobs.values() if j["status"] == "queued"),
                    key=env._queue_sort_key)
    rank = {str(j["id"]): i for i, j in enumerate(queued)}
    jobs = sorted((str(j["id"]), j["status"], int(j["attempts"]), int(j["remaining_rounds"]),
                   rank.get(str(j["id"]))) for j in env.jobs.values())
    return json.dumps([env.rounds_advanced, jobs,
                       sorted((k, v["status"]) for k, v in env.pipelines.items()),
                       sorted((k, v["status"]) for k, v in env.checks.items()),
                       sorted((k, v["state"]) for k, v in env.gates.items()),
                       sorted((k, v["status"]) for k, v in env.deployments.items()),
                       sorted(env.completed_round.items())])


def focal_actions(env: Any, me: str, legal_set: str) -> list[tuple[str | None, dict[str, Any]]]:
    """Every action on the focal agent's own resources.

    `as_built`: all of them. `realistic`: none that interrupts or re-queues an
    own job that is currently queued or running (cancelling it, cancelling or
    restarting its pipeline). Those actions advance the attempt counter
    without a run finishing, so under the attempt-indexed flake model they
    skip the flaky failures -- in a real CI system the flake would recur.
    """
    s = me.lower()
    pipe = env.pipelines[f"pipeline-{s}"]
    busy = any(env.jobs[j]["status"] in {"queued", "running"} for j in pipe["jobs"])
    acts: list[tuple[str | None, dict[str, Any]]] = [(None, {})]
    if legal_set == "as_built" or not busy:
        acts += [("restart_pipeline", {"pipeline_id": f"pipeline-{s}"}),
                 ("cancel_pipeline", {"pipeline_id": f"pipeline-{s}"})]
    for job in pipe["jobs"]:
        acts.append(("retry_job", {"job_id": job}))
        if legal_set == "as_built" or env.jobs[job]["status"] not in {"queued", "running"}:
            acts.append(("cancel_job", {"job_id": job}))
    acts += [("mark_check_status", {"check_id": f"check-{s}", "status": "passed"}),
             ("mark_check_status", {"check_id": f"check-{s}", "status": "failed"}),
             ("request_deployment", {"deploy_id": f"deploy-{s}"})]
    return acts


def other_action(env: Any, other: str, model: str) -> tuple[str | None, dict[str, Any]]:
    if model == "idle":
        return None, {}
    s = other.lower()
    pipe = env.pipelines[f"pipeline-{s}"]
    if pipe["status"] in {"created", "failed", "cancelled"} and not any(
            env.jobs[j]["status"] == "failed" for j in pipe["jobs"]):
        return "restart_pipeline", {"pipeline_id": f"pipeline-{s}"}
    failed = [j for j in pipe["jobs"] if env.jobs[j]["status"] == "failed"]
    if failed:
        return "retry_job", {"job_id": failed[0]}
    if env.gates[f"gate-{s}"]["state"] == "open" and env.deployments[f"deploy-{s}"]["status"] != "deployed":
        return "request_deployment", {"deploy_id": f"deploy-{s}"}
    return None, {}


def earliest(side: str, focal_first: bool, other_model: str, legal_set: str) -> int | None:
    me = side.upper()
    other = "B" if me == "A" else "A"
    start = build(side)
    deadline = int(start.deadline_rounds)
    states: dict[str, Any] = {}

    @cache
    def best(state_key: str) -> int | None:
        env = states[state_key]
        done = env.completed_round.get(me)
        if done is not None:
            return int(done) if done <= deadline else None
        if env.rounds_advanced > deadline:
            return None
        results = []
        seen: set[str] = set()
        for name, args in focal_actions(env, me, legal_set):
            nxt = copy.deepcopy(env)
            if focal_first:
                act(nxt, me, name, **args)
                o_name, o_args = other_action(nxt, other, other_model)
                act(nxt, other, o_name, **o_args)
            else:
                o_name, o_args = other_action(nxt, other, other_model)
                act(nxt, other, o_name, **o_args)
                act(nxt, me, name, **args)
            nxt.end_of_round()
            k = key(nxt)
            if k in seen:
                continue
            seen.add(k)
            states.setdefault(k, nxt)
            r = best(k)
            if r is not None:
                results.append(r)
        return min(results) if results else None

    k0 = key(start)
    states[k0] = start
    return best(k0)


def main() -> None:
    out: dict[str, Any] = {}
    for legal_set in ("realistic", "as_built"):
        for side in "ab":
            for focal_first in (True, False):
                for model in ("idle", "legal_path"):
                    out[f"{legal_set}/{side}/{'first' if focal_first else 'second'}/{model}"] = \
                        earliest(side, focal_first, model, legal_set)
    summary = {}
    for legal_set in ("realistic", "as_built"):
        for order in ("first", "second"):
            vals = [v for k, v in out.items() if k.startswith(f"{legal_set}/") and f"/{order}/" in k]
            reached = [v for v in vals if v is not None]
            summary[f"{legal_set}/{order}"] = {"min": min(reached), "max": max(reached),
                                               "unreachable": len(vals) - len(reached)}
    if "--json" in sys.argv:
        json.dump({"cases": out, "summary": summary}, sys.stdout, indent=1)
        return
    for k, v in out.items():
        print(f"  {k:40s} earliest legal completion round {v}")
    for k, v in summary.items():
        print(f"  {k:20s} round {v['min']}-{v['max']} (unreachable cases: {v['unreachable']})")


if __name__ == "__main__":
    main()
