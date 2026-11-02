from __future__ import annotations

import base64
import json
import time
from collections.abc import Sequence
from typing import Any

from competition_lab.config import ModelConfig
from competition_lab.providers.base import ModelProvider
from competition_lab.providers.retry import bounded_retry
from competition_lab.schemas import ModelResponse, StopReason, ToolCall, Usage

# Provider-specific stop vocabularies mapped onto one normalized enum. The two
# Bedrock surfaces report termination in different fields with different token
# sets (Converse: "stopReason"; OpenAI-on-Bedrock Responses: "status" plus
# "incomplete_details.reason"). Leaving them unnormalized meant the
# orchestrator's refusal check matched at most one provider, so an agent that
# refused on one surface was recorded as having simply finished.
CONVERSE_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": StopReason.END_TURN,
    "tool_use": StopReason.TOOL_USE,
    "max_tokens": StopReason.MAX_TOKENS,
    "stop_sequence": StopReason.END_TURN,
    "content_filtered": StopReason.REFUSAL,
    "guardrail_intervened": StopReason.REFUSAL,
}

RESPONSES_STATUSES: dict[str, StopReason] = {
    "completed": StopReason.END_TURN,
    "requires_action": StopReason.TOOL_USE,
    "failed": StopReason.ERROR,
    "cancelled": StopReason.ERROR,
    "in_progress": StopReason.ERROR,
    "queued": StopReason.ERROR,
}

RESPONSES_INCOMPLETE_REASONS: dict[str, StopReason] = {
    "max_output_tokens": StopReason.MAX_TOKENS,
    "content_filter": StopReason.REFUSAL,
}


def normalize_converse_stop(
    stop_reason: str | None, *, has_tool_calls: bool
) -> StopReason:
    """Map a Bedrock Converse ``stopReason`` onto the normalized vocabulary."""
    if stop_reason is None:
        return StopReason.UNKNOWN
    mapped = CONVERSE_STOP_REASONS.get(stop_reason)
    if mapped is not None:
        return mapped
    # An unrecognized token must not silently read as a normal end_turn.
    return StopReason.TOOL_USE if has_tool_calls else StopReason.UNKNOWN


def normalize_responses_stop(
    status: str | None,
    incomplete_reason: str | None = None,
    *,
    has_tool_calls: bool,
) -> StopReason:
    """Map an OpenAI-on-Bedrock Responses ``status`` onto the same vocabulary.

    ``incomplete`` carries the real cause in ``incomplete_details.reason``, so a
    truncated or filtered response is distinguished from an ordinary finish.
    """
    if status == "incomplete":
        if incomplete_reason is None:
            return StopReason.UNKNOWN
        return RESPONSES_INCOMPLETE_REASONS.get(incomplete_reason, StopReason.UNKNOWN)
    if status is None:
        return StopReason.UNKNOWN
    mapped = RESPONSES_STATUSES.get(status)
    if mapped is None:
        return StopReason.TOOL_USE if has_tool_calls else StopReason.UNKNOWN
    # A completed response that carries tool calls is a tool-use turn.
    if mapped is StopReason.END_TURN and has_tool_calls:
        return StopReason.TOOL_USE
    return mapped


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _loggable(value: Any) -> Any:
    """Copy a provider reply into JSON-safe form for the event log.

    Converse can return ``bytes`` (e.g. ``reasoningContent.redactedContent``),
    which JSON cannot hold; those are base64-encoded rather than dropped.
    """
    if isinstance(value, bytes):
        return {"base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _loggable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_loggable(v) for v in value]
    return value


def _raw_for_log(raw: dict[str, Any]) -> dict[str, Any]:
    # ResponseMetadata is HTTP transport detail; the request id is kept in its
    # own field.
    return dict(_loggable({k: v for k, v in raw.items() if k != "ResponseMetadata"}))


def parse_converse_response(
    raw: dict[str, Any], *, latency_ms: float = 0.0
) -> ModelResponse:
    """Normalize a Bedrock Converse (Claude-on-Bedrock) reply.

    Pure function over the parsed payload so normalization is testable from
    fixtures without a client or any network call.
    """
    message = raw.get("output", {}).get("message", {})
    content = message.get("content", []) or []
    calls = [
        ToolCall(
            id=item["toolUse"]["toolUseId"],
            name=item["toolUse"]["name"],
            arguments=item["toolUse"].get("input", {}) or {},
        )
        for item in content
        if "toolUse" in item
    ]
    text = "".join(item.get("text", "") for item in content)
    # Reasoning arrives in its own block type, which the text join above does
    # not see. It is logged, not added to ``text``, so the transcript the model
    # is shown is unchanged.
    reasoning = "".join(
        ((item.get("reasoningContent") or {}).get("reasoningText") or {}).get(
            "text", ""
        )
        for item in content
    )
    usage = raw.get("usage", {}) or {}
    stop = normalize_converse_stop(raw.get("stopReason"), has_tool_calls=bool(calls))
    # A truncated turn carries no complete action, so surface it as an error
    # rather than letting a half-emitted tool call reach the environment.
    error = None
    if stop is StopReason.MAX_TOKENS:
        error = "response truncated at max_tokens"
    elif stop is StopReason.REFUSAL:
        error = "provider refused or filtered the response"
    elif stop is StopReason.UNKNOWN:
        error = f"unrecognized stopReason: {raw.get('stopReason')!r}"
    return ModelResponse(
        text=text,
        tool_calls=[] if stop is StopReason.MAX_TOKENS else calls,
        stop_reason=stop,
        usage=Usage(
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
        ),
        latency_ms=latency_ms,
        request_id=raw.get("ResponseMetadata", {}).get("RequestId"),
        error=error,
        reasoning_text=reasoning,
        raw_response=_raw_for_log(raw),
    )


def parse_responses_response(
    payload: dict[str, Any],
    *,
    request_id: str | None = None,
    latency_ms: float = 0.0,
) -> ModelResponse:
    """Normalize an OpenAI-on-Bedrock Responses reply onto the same shape."""
    output = payload.get("output", []) or []
    calls = []
    for item in output:
        if item.get("type") != "function_call":
            continue
        try:
            arguments = json.loads(item.get("arguments") or "{}")
        except json.JSONDecodeError:
            # Malformed arguments are a provider-side defect, not an agent
            # action; drop the call and report it rather than guessing.
            return ModelResponse(
                text=payload.get("output_text", ""),
                stop_reason=StopReason.ERROR,
                latency_ms=latency_ms,
                request_id=request_id,
                error=f"unparseable tool arguments for {item.get('name')!r}",
            )
        calls.append(
            ToolCall(id=item["call_id"], name=item["name"], arguments=arguments)
        )
    incomplete = (payload.get("incomplete_details") or {}).get("reason")
    stop = normalize_responses_stop(
        payload.get("status"), incomplete, has_tool_calls=bool(calls)
    )
    usage = payload.get("usage", {}) or {}
    error = None
    if stop is StopReason.MAX_TOKENS:
        error = "response truncated at max_output_tokens"
    elif stop is StopReason.REFUSAL:
        error = "provider refused or filtered the response"
    elif stop is StopReason.ERROR:
        error = (payload.get("error") or {}).get("message") or (
            f"provider reported status {payload.get('status')!r}"
        )
    elif stop is StopReason.UNKNOWN:
        error = f"unrecognized status: {payload.get('status')!r}"
    reasoning = "".join(
        part.get("text", "")
        for item in output
        if item.get("type") == "reasoning"
        for part in (item.get("summary") or []) + (item.get("content") or [])
        if isinstance(part, dict)
    )
    return ModelResponse(
        text=payload.get("output_text", ""),
        tool_calls=[] if stop is StopReason.MAX_TOKENS else calls,
        stop_reason=stop,
        usage=Usage(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        ),
        latency_ms=latency_ms,
        request_id=request_id,
        error=error,
        reasoning_text=reasoning,
        raw_response=_raw_for_log(payload),
    )


def _client(config: ModelConfig) -> Any:
    import boto3

    session = boto3.Session(profile_name=config.profile, region_name=config.region)
    return session.client(
        "bedrock-runtime",
        config=__import__("botocore.config", fromlist=["Config"]).Config(
            read_timeout=config.timeout_seconds,
            connect_timeout=config.timeout_seconds,
            retries={"max_attempts": 0},
        ),
    )


def _retryable(exc: Exception) -> bool:
    text = type(exc).__name__ + str(exc)
    return any(x in text for x in ("Throttl", "Timeout", "ServiceUnavailable"))


def to_converse_tools(tools: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Wrap canonical tool definitions in Bedrock Converse's ``toolSpec`` shape.

    ``tools.py`` is provider-neutral and its output is hashed into the manifest,
    so the Converse-specific envelope (and its camelCase ``inputSchema.json``)
    is applied here rather than at the source. Already-wrapped entries pass
    through untouched.
    """
    wrapped: list[dict[str, Any]] = []
    for tool in tools:
        if "toolSpec" in tool:
            wrapped.append(dict(tool))
            continue
        wrapped.append(
            {
                "toolSpec": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "inputSchema": {"json": tool["input_schema"]},
                }
            }
        )
    return wrapped


def to_converse_messages(
    messages: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Translate the neutral message log into Converse content blocks.

    ``orchestration.py`` keeps an Anthropic-native transcript: string content,
    an assistant ``tool_calls`` list, and ``role: "tool"`` results. Converse
    instead wants every ``content`` to be a block list, tool calls expressed as
    ``toolUse`` blocks, and tool results returned in a *user* turn as
    ``toolResult`` blocks. Converting here keeps the orchestrator neutral.

    Consecutive tool results merge into one user turn because Converse requires
    strictly alternating user/assistant roles.
    """
    converted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "tool":
            block = {
                "toolResult": {
                    "toolUseId": message["tool_call_id"],
                    "content": [{"text": str(content)}],
                }
            }
            if converted and converted[-1]["role"] == "user":
                converted[-1]["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
            continue

        blocks: list[dict[str, Any]] = []
        if isinstance(content, list):
            blocks.extend(content)
        elif content:
            blocks.append({"text": str(content)})
        for call in message.get("tool_calls") or []:
            blocks.append(
                {
                    "toolUse": {
                        "toolUseId": call["id"],
                        "name": call["name"],
                        "input": call.get("arguments") or {},
                    }
                }
            )
        # An assistant turn with no text and no tool call is not representable;
        # Converse rejects an empty content list.
        if not blocks:
            blocks.append({"text": ""})
        converted.append({"role": role, "content": blocks})
    return converted


class BedrockConverseProvider(ModelProvider):
    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.client = _client(config)

    def complete(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelResponse:
        started = time.monotonic()

        # Models that reject the temperature field fail the whole request, so
        # it is omitted rather than sent-and-ignored. See
        # ModelConfig.supports_temperature.
        inference_config: dict[str, Any] = {"maxTokens": self.config.max_tokens}
        if self.config.supports_temperature:
            inference_config["temperature"] = self.config.temperature

        # Bedrock rejects an EMPTY toolConfig.tools ("valid min length: 1")
        # before the request is sent, so "no tools" must be expressed by
        # OMITTING toolConfig rather than passing an empty list. Experiment 2's
        # phase 1 depends on this: it withholds tools so the model cannot
        # answer the note request with a tool call.
        request: dict[str, Any] = {
            "modelId": self.config.model_id,
            "messages": to_converse_messages(messages),
            "inferenceConfig": inference_config,
        }
        converted_tools = to_converse_tools(tools)
        if converted_tools:
            request["toolConfig"] = {"tools": converted_tools}
        # Omitted entirely when unset, so every earlier config sends exactly
        # the request it always did.
        if self.config.additional_request_fields:
            request["additionalModelRequestFields"] = (
                self.config.additional_request_fields
            )

        def invoke() -> Any:
            return self.client.converse(**request)

        raw = bounded_retry(
            invoke, retries=self.config.max_retries, retryable=_retryable
        )
        return parse_converse_response(raw, latency_ms=_elapsed_ms(started))


class BedrockResponsesProvider(ModelProvider):
    """Adapter for Bedrock's OpenAI-compatible Responses endpoint."""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config
        self.client = _client(config)

    def complete(
        self, messages: Sequence[dict[str, Any]], tools: Sequence[dict[str, Any]]
    ) -> ModelResponse:
        started = time.monotonic()
        body = {
            "model": self.config.model_id,
            "input": list(messages),
            "tools": list(tools),
            "temperature": self.config.temperature,
            "max_output_tokens": self.config.max_tokens,
        }
        raw = bounded_retry(
            lambda: self.client.invoke_model(
                modelId=self.config.model_id, body=json.dumps(body)
            ),
            retries=self.config.max_retries,
            retryable=_retryable,
        )
        payload = json.loads(raw["body"].read())
        return parse_responses_response(
            payload,
            request_id=raw.get("ResponseMetadata", {}).get("RequestId"),
            latency_ms=_elapsed_ms(started),
        )
