from __future__ import annotations

from dataclasses import dataclass, field

from competition_lab.config import ModelConfig
from competition_lab.schemas import Usage


class BudgetExceededError(RuntimeError):
    """Raised when a run would exceed its request or spend ceiling.

    Raised *before* the offending request is issued, so the ceiling is a real
    guard rather than a post-hoc report.
    """


@dataclass
class CostLedger:
    """Accumulates real spend and request counts against hard ceilings."""

    max_usd: float | None = None
    max_requests: int | None = None
    input_cost_per_million: float = 0.0
    output_cost_per_million: float = 0.0
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    spent_usd: float = 0.0
    per_request: list[dict[str, float | int]] = field(default_factory=list)

    @classmethod
    def from_config(
        cls,
        model: ModelConfig,
        max_usd: float | None,
        max_requests: int | None,
    ) -> CostLedger:
        return cls(
            max_usd=max_usd,
            max_requests=max_requests,
            input_cost_per_million=model.input_cost_per_million,
            output_cost_per_million=model.output_cost_per_million,
        )

    def price(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_cost_per_million
            + usage.output_tokens * self.output_cost_per_million
        ) / 1_000_000

    def check_before_request(self) -> None:
        """Refuse to issue another request if a ceiling is already reached."""
        if self.max_requests is not None and self.requests >= self.max_requests:
            raise BudgetExceededError(
                f"request ceiling reached: {self.requests}/{self.max_requests}"
            )
        if self.max_usd is not None and self.spent_usd >= self.max_usd:
            raise BudgetExceededError(
                f"spend ceiling reached: {self.spent_usd:.6f}/{self.max_usd:.6f} USD"
            )

    def record(self, usage: Usage) -> float:
        cost = self.price(usage)
        self.requests += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.spent_usd += cost
        self.per_request.append(
            {
                "request": self.requests,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": cost,
            }
        )
        return cost

    def as_dict(self) -> dict[str, object]:
        return {
            "requests": self.requests,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "spent_usd": self.spent_usd,
            "max_usd": self.max_usd,
            "max_requests": self.max_requests,
        }
