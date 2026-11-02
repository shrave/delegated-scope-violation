from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from competition_lab.environments.base import Environment
from competition_lab.eventlog import read_events
from competition_lab.schemas import EventKind, ToolCall


class ReplayDivergenceError(ValueError):
    """Raised when re-execution does not reproduce the recorded state."""


@dataclass
class ReplayReport:
    actions: int
    divergences: list[dict[str, Any]] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.divergences


def replay(
    event_path: Path, environment: Environment, strict: bool = True
) -> ReplayReport:
    """Re-execute recorded actions and verify state digests match the log.

    The recorded before/after digests are the only evidence that a log
    faithfully describes what happened, so replay compares against them rather
    than merely re-running the calls.
    """
    events = read_events(event_path)
    recorded = {
        (e.global_action_index): e.payload
        for e in events
        if e.kind == EventKind.TOOL_RESULT
    }
    report = ReplayReport(actions=0)
    index = 0
    rounds_replayed = 0
    # Walk the log in recorded order rather than filtering to tool calls. Any
    # environment whose state advances at round boundaries (the compute
    # scheduler completes queued jobs there) diverges from the first action
    # after the first boundary otherwise. RepositoryEnvironment.end_of_round is
    # a no-op, so its replays are unaffected.
    for event in events:
        if event.kind == EventKind.TOOL_REQUEST and event.actor:
            index += 1
            actor = event.actor
            call = ToolCall.model_validate(
                {k: v for k, v in event.payload.items() if k != "turn"}
            )
            turn = int(event.payload.get("turn", 0))
            expected = recorded.get(index)
            output = (expected or {}).get("output")
            if isinstance(output, dict) and output.get("defense") == "judge_blocked":
                # defense-001: the judge gate refused this call, so it never ran
                # on the environment. Executing it here would replay a state
                # change that did not happen.
                report.actions += 1
                continue
            result = environment.execute(actor, call, turn=turn)
            report.actions += 1
            if expected is None:
                report.divergences.append(
                    {"action_index": index, "reason": "no recorded tool_result"}
                )
                continue
            for label, actual in (
                ("before_digest", result.before_digest),
                ("after_digest", result.after_digest),
                ("classification", result.classification.value),
                ("target", result.target),
            ):
                if expected.get(label) != actual:
                    report.divergences.append(
                        {
                            "action_index": index,
                            "actor": actor,
                            "tool": call.name,
                            "field": label,
                            "recorded": expected.get(label),
                            "replayed": actual,
                        }
                    )
        elif event.kind == EventKind.STATE_TRANSITION:
            reason = event.payload.get("reason")
            if reason == "option_structured_note":
                # Experiment 2 phase-1 note: a model call made with NO tools,
                # logged for mechanism analysis. It changes no environment
                # state, so skipping it is exact rather than a guess. Kept
                # separate from "telemetry" so the two are distinguishable in
                # the log and one cannot be silently read as the other.
                continue
            if reason == "exploratory_probe_note":
                # Exploratory probe scaffold (reward-forward prompt or
                # affordance menu) injected before a decision. It changes no
                # environment state and consumes no action budget, so skipping
                # it is exact. Kept distinct from the Experiment 2 note reason
                # so an exploratory episode can never be read as an
                # Experiment 2 one.
                continue
            if reason == "telemetry":
                # Telemetry-aware architecture: read-only context injected
                # before a decision. It changes NO environment state, so there
                # is nothing for replay to reproduce and skipping it is exact
                # rather than a guess. Whitelisted explicitly instead of
                # loosening the guard below, which must keep refusing unknown
                # transitions.
                continue
            if reason != "end_of_round":
                # Refuse to guess: an unrecognised transition means the log
                # records state changes this replay cannot reproduce.
                report.divergences.append(
                    {
                        "action_index": index,
                        "reason": f"unrecognised state_transition {reason!r}",
                    }
                )
                continue
            rounds_replayed += 1
            recorded_round = event.payload.get("round")
            # Rounds are recorded as a 1-based counter, so a gap, repeat, or
            # reordering shows up here rather than silently desynchronising the
            # environment from the log.
            if recorded_round != rounds_replayed:
                report.divergences.append(
                    {
                        "action_index": index,
                        "reason": "state_transition out of order",
                        "recorded": recorded_round,
                        "replayed": rounds_replayed,
                    }
                )
            environment.end_of_round()
    report.final_state = environment.snapshot()
    if strict and report.divergences:
        first = report.divergences[0]
        raise ReplayDivergenceError(
            f"replay diverged at action {first['action_index']}: {first}"
        )
    return report
