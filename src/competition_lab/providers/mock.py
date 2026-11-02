from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from competition_lab.providers.base import ModelProvider
from competition_lab.schemas import ModelResponse, StopReason, ToolCall, Usage


class MockProvider(ModelProvider):
    def __init__(self, actions: Sequence[ToolCall]) -> None:
        self._actions = iter(actions)

    def complete(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelResponse:
        # An empty tool list means the caller withheld tools, which a real
        # provider cannot answer with a tool call. Honouring that here keeps the
        # mock faithful to the Experiment 2 phase-1 contract; without it the
        # mock would emit a scripted tool call in a phase that has no tools,
        # and the invariant would be untestable locally.
        if not tools:
            return ModelResponse(
                text="objective_relevant_state: mock note",
                stop_reason=StopReason.END_TURN,
                usage=Usage(input_tokens=10, output_tokens=5),
            )
        try:
            action = next(self._actions)
        except StopIteration:
            return ModelResponse(text="Finished.", stop_reason=StopReason.END_TURN)
        return ModelResponse(
            tool_calls=[action],
            stop_reason=StopReason.TOOL_USE,
            request_id=f"mock-{action.id}",
            usage=Usage(input_tokens=10, output_tokens=5),
        )
