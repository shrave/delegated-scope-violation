from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PermissionMode(StrEnum):
    SOFT = "soft"
    HARD = "hard"


class EnvironmentKind(StrEnum):
    REPOSITORY = "repository"
    COMPUTE = "compute"
    # Simulated release dashboard with no dominant legal strategy. Synthetic
    # only; touches no real service, cluster, CI system, or credential.
    RELEASE_INTEGRITY = "release_integrity"
    # Shared CI/CD release operations. Synthetic; measures delegated-scope
    # violations where the platform role permits the action but the delegation
    # record does not.
    CICD_RELEASE = "cicd_release"
    # SOC/ITSM incident response. Synthetic; the second domain, selected
    # because a payoff gate showed it has a temptation frontier CI/CD lacked.
    SOC_ITSM = "soc_itsm"


class EventKind(StrEnum):
    MODEL_CALL = "model_call"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    STATE_TRANSITION = "state_transition"
    EVALUATION = "evaluation"
    DETECTION = "detection"
    FINAL = "final"


class StopReason(StrEnum):
    """Normalized turn-termination vocabulary shared by every provider.

    Provider surfaces report termination in different fields with different
    tokens; adapters map onto this enum so downstream logic (refusal handling,
    truncation detection) behaves identically across providers.
    """

    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    REFUSAL = "refusal"
    ERROR = "error"
    UNKNOWN = "unknown"


#: Stop reasons that end an agent's participation without a usable action.
TERMINAL_STOP_REASONS = frozenset(
    {StopReason.REFUSAL, StopReason.ERROR, StopReason.UNKNOWN}
)


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0


class ModelResponse(BaseModel):
    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    stop_reason: StopReason = StopReason.END_TURN
    usage: Usage = Field(default_factory=Usage)
    latency_ms: float = 0.0
    request_id: str | None = None
    error: str | None = None
    # Logged only, never fed back to the model: the transcript is built from
    # ``text``. Reasoning blocks (e.g. Converse ``reasoningContent``) were once
    # dropped by the parser, and the raw reply was not kept, so a model's
    # reasoning could not be recovered from the logs afterwards.
    reasoning_text: str = ""
    raw_response: dict[str, Any] | None = None


class ActionClassification(StrEnum):
    """Explicit outcome class for every executed action.

    There is deliberately no default. Every environment branch must state which
    class it produces, so that a new branch cannot inherit "authorized" or
    "ordinary failure" semantics by omission.
    """

    AUTHORIZED = "authorized"
    ORDINARY_FAILURE = "ordinary_failure"
    ATTEMPTED_VIOLATION = "attempted_violation"
    SUCCESSFUL_VIOLATION = "successful_violation"


class ActionResult(BaseModel):
    classification: ActionClassification
    success: bool
    changed_state: bool = False
    target: str | None = None
    output: Any = None
    before_digest: str | None = None
    after_digest: str | None = None
    # Logged, never shown to the model (the model receives `output` only).
    audit: dict[str, Any] | None = None
    # When set, the model is shown THIS instead of `output`; `output` is still
    # logged in full. Used for defense refusals, whose logged output carries
    # the classification context (owner, delegation) the agent must not see.
    model_view: Any = None

    @property
    def authorized(self) -> bool:
        return self.classification is ActionClassification.AUTHORIZED

    @property
    def attempted_violation(self) -> bool:
        return self.classification is ActionClassification.ATTEMPTED_VIOLATION

    @property
    def successful_violation(self) -> bool:
        return self.classification is ActionClassification.SUCCESSFUL_VIOLATION

    @model_validator(mode="after")
    def check_coherence(self) -> ActionResult:
        if self.successful_violation and not (self.success and self.changed_state):
            raise ValueError(
                "successful_violation requires success and changed_state"
            )
        if self.attempted_violation and self.changed_state:
            raise ValueError("attempted_violation must not change state")
        ordinary = ActionClassification.ORDINARY_FAILURE
        if self.classification is ordinary and self.success:
            raise ValueError("ordinary_failure must not be successful")
        if (
            self.classification
            in {
                ActionClassification.ATTEMPTED_VIOLATION,
                ActionClassification.SUCCESSFUL_VIOLATION,
            }
            and self.target is None
        ):
            raise ValueError("violations must name a target")
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    episode_id: str
    kind: EventKind
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    global_action_index: int | None = None
    actor: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    previous_hash: str
    event_hash: str


class JudgeLabel(StrEnum):
    AUTHORIZED = "authorized"
    ATTEMPTED = "attempted_violation"
    SUCCESSFUL = "successful_violation"
    AMBIGUOUS = "ambiguous"


class JudgeDecision(BaseModel):
    label: JudgeLabel
    first_relevant_action_id: str | None
    target_category: str | None
    measurable_impact: bool
    evidence_action_ids: list[str]
    rationale: str
    confidence: float = Field(ge=0, le=1)
    abstention_reason: str | None = None
