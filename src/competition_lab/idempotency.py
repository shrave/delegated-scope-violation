from __future__ import annotations

import hashlib
import json

from competition_lab.schemas import ActionResult, ToolCall


def action_fingerprint(call: ToolCall) -> str:
    """Content hash of a tool call, ignoring the model-supplied call id."""
    material = json.dumps(
        {"name": call.name, "arguments": call.arguments}, sort_keys=True, default=str
    )
    return hashlib.sha256(material.encode()).hexdigest()


class DuplicateActionIdError(ValueError):
    """Raised when a model reuses a call id for a materially different action.

    Reusing an id for different content is a protocol violation, not a retry.
    Silently returning the cached result would erase a real action (and any
    violation it contained) and attribute the earlier result to the wrong
    target, so this fails loudly instead.
    """


class IdempotencyCache:
    """Caches results per logical turn, keyed by orchestrator-owned identity.

    The key is ``(actor, turn, fingerprint)``. ``turn`` is supplied by the
    orchestrator, never by the model, so a genuine retry of one logical turn
    hits the cache while two distinct turns never collide -- even if the model
    reuses ``call.id``.
    """

    def __init__(self) -> None:
        self._results: dict[tuple[str, int, str], ActionResult] = {}
        self._ids: dict[tuple[str, int, str], str] = {}

    def key(self, actor: str, turn: int, call: ToolCall) -> tuple[str, int, str]:
        return (actor, turn, action_fingerprint(call))

    def get(self, actor: str, turn: int, call: ToolCall) -> ActionResult | None:
        seen = self._ids.get((actor, turn, call.id))
        fingerprint = action_fingerprint(call)
        if seen is not None and seen != fingerprint:
            raise DuplicateActionIdError(
                f"call id {call.id!r} reused by {actor} on turn {turn} for a "
                "different action; refusing to substitute the cached result"
            )
        cached = self._results.get(self.key(actor, turn, call))
        return cached.model_copy(deep=True) if cached else None

    def put(self, actor: str, turn: int, call: ToolCall, result: ActionResult) -> None:
        self._results[self.key(actor, turn, call)] = result.model_copy(deep=True)
        self._ids[(actor, turn, call.id)] = action_fingerprint(call)
