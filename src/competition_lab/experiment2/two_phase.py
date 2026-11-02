"""The ``option_structured_two_phase`` decision interface.

WHY TWO PHASES. The earlier ``structured_rationale`` architecture asked for a
note and offered tools in the SAME call. Qwen answered by writing a complete
seven-field note as plain text and never calling a tool: 2 tool calls against
14 for the base architecture, and the episode was quarantined as invalid.
Splitting the call makes that failure structurally impossible -- phase 1 has no
tools to skip to, and phase 2 has no note to write instead of acting.

INVARIANTS (each asserted by a test):
  * Phase 1 is sent with NO tools, so it cannot produce a tool call.
  * The note is logged as a ``state_transition`` with reason
    ``option_structured_note`` -- never a tool call, so it cannot inflate the
    action budget or any tool-usage count.
  * Phase 1 changes no environment state, so replay skips it exactly rather
    than guessing.
  * Phase 1 costs are recorded normally; the probe is not cheaper than it looks.
  * Phase 2 receives the normal tool set and is expected to act exactly once.

This module changes the DECISION INTERFACE only. It touches no tool, no
detector, no scoring rule, no task state and no delegation logic.
"""

from __future__ import annotations

from typing import Any, Protocol

from competition_lab.experiment2.scaffold import (
    DEFAULT_VARIANT,
    OPTION_STRUCTURED_PHASE1_PROMPT,
    OPTION_STRUCTURED_PHASE2_PROMPT,
    phase1_prompt_for,
)

# Re-exported so callers depend on this module alone rather than reaching past
# it into scaffold.py.
PHASE1_PROMPT = OPTION_STRUCTURED_PHASE1_PROMPT
PHASE2_PROMPT = OPTION_STRUCTURED_PHASE2_PROMPT

ARCHITECTURE = "option_structured_two_phase"

# Explicit so callers depend on this module alone rather than reaching past it
# into scaffold.py, and so the re-export is visible to static checking.
__all__ = [
    "ARCHITECTURE",
    "DEFAULT_VARIANT",
    "NOTE_REASON",
    "PHASE1_PROMPT",
    "PHASE2_PROMPT",
    "note_event_payload",
    "phase1_messages",
    "phase1_prompt_for",
    "phase2_followup",
    "run_option_note_phase",
]
NOTE_REASON = "option_structured_note"


class _Provider(Protocol):
    def complete(
        self, messages: Any, tools: Any
    ) -> Any:  # pragma: no cover - structural
        ...


def phase1_messages(
    history: list[dict[str, Any]], variant: str = DEFAULT_VARIANT
) -> list[dict[str, Any]]:
    """History plus the note request. Tools are withheld by the caller."""
    return [*history, {"role": "user", "content": phase1_prompt_for(variant)}]


def phase2_followup() -> dict[str, Any]:
    """The turn that restores tools and asks for exactly one action."""
    return {"role": "user", "content": OPTION_STRUCTURED_PHASE2_PROMPT}


def run_option_note_phase(
    provider: _Provider,
    history: list[dict[str, Any]],
    tools: Any,
    variant: str = DEFAULT_VARIANT,
) -> tuple[str, Any]:
    """Run phase 1 and return ``(note_text, raw_response)``.

    TOOLS ARE PASSED THROUGH, and that is forced by the provider rather than
    chosen. Bedrock Converse rejects a request whose history contains toolUse
    or toolResult blocks unless ``toolConfig`` is present -- "The toolConfig
    field must be defined when using toolUse and toolResult content blocks" --
    and it offers no ``toolChoice: none``. So after the first action of an
    episode, withholding tools is simply not expressible on this API.

    The note is therefore enforced by the PROMPT ("Provide only the note in
    this reply"), verified live: with tools available and the note requested,
    GPT returns stop_reason=end_turn and zero toolUse blocks.

    Any tool call that does arrive in phase 1 is DISCARDED by the caller rather
    than executed, so the two-phase contract still holds: no environment action
    can originate from the note phase. That discard is the real guarantee, and
    it does not depend on provider cooperation.
    """
    response = provider.complete(phase1_messages(history, variant), tools)
    return (getattr(response, "text", "") or ""), response


def note_event_payload(
    note: str,
    *,
    turn: int,
    actor: str,
    cost_usd: float,
    variant: str = DEFAULT_VARIANT,
    discarded_tool_calls: list[str] | None = None,
) -> dict[str, Any]:
    """Payload for the phase-1 ``state_transition`` event.

    ``reason`` is distinct from ``"telemetry"`` so replay can whitelist it on
    its own terms, and so a future reader can tell an Experiment 2 note from an
    Experiment 1 telemetry block without inspecting the content.
    """
    return {
        "reason": NOTE_REASON,
        "architecture": ARCHITECTURE,
        # Recorded per note so a variant can never be inferred wrongly from a
        # config that was edited after the run.
        "scaffold_variant": variant,
        "turn": turn,
        "actor": actor,
        "note": note,
        "phase": 1,
        "request_cost_usd": cost_usd,
        # Stated explicitly so the invariant travels with the artifact rather
        # than living only in this docstring.
        "changed_state": False,
        "consumed_action_budget": False,
        # Recorded so "the model tried to act during the note phase" is
        # measurable rather than invisible. A non-empty list is a protocol
        # observation about the model, not an environment action.
        "discarded_tool_calls": discarded_tool_calls or [],
    }
