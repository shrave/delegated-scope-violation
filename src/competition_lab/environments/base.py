from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from competition_lab.schemas import ActionResult, ToolCall


class Environment(ABC):
    @abstractmethod
    def execute(self, actor: str, call: ToolCall, turn: int = 0) -> ActionResult:
        """Execute one structured action.

        ``turn`` is the orchestrator-owned logical turn number and scopes
        idempotency, so a retried request is deduplicated while two distinct
        turns never collide even if the model reuses a call id.
        """
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def end_of_round(self) -> None:
        """Hook run once per full round, after every agent has acted.

        Default is a no-op. Environments with time-advancing state (such as a
        job scheduler) override this so that state advances symmetrically for
        both agents rather than depending on within-round turn order.
        """
        return None
