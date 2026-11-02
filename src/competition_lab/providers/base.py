from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from competition_lab.schemas import ModelResponse


class ModelProvider(ABC):
    @abstractmethod
    def complete(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelResponse:
        raise NotImplementedError
