from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from competition_lab.environments import RepositoryEnvironment
from competition_lab.eventlog import (
    EventLog,
    calculate_event_hash,
    canonical_json_bytes,
    read_events,
)
from competition_lab.replay import replay
from competition_lab.schemas import EventKind, PermissionMode, ToolCall


class PreLiveIntegrityError(RuntimeError):
    """Raised when local event integrity cannot be established."""


def run_pre_live_integrity_self_test() -> None:
    """Exercise event write, verify, and replay locally without any network."""
    try:
        enum_form = {"kind": EventKind.TOOL_REQUEST}
        string_form = {"kind": EventKind.TOOL_REQUEST.value}
        if canonical_json_bytes(enum_form) != canonical_json_bytes(string_form):
            raise PreLiveIntegrityError("EventKind canonicalization differs")

        with TemporaryDirectory(prefix="competition-lab-prelive-") as temporary:
            path = Path(temporary) / "events.jsonl"
            ownership: dict[str, tuple[str, ...]] = {
                "A": ("components/a/", "submissions/a/"),
                "B": ("components/b/", "submissions/b/"),
            }
            initial = {
                "components/a/main.py": "VALUE = 0\n",
                "components/b/main.py": "VALUE = 0\n",
            }
            environment = RepositoryEnvironment(
                initial, ownership, PermissionMode.SOFT
            )
            call = ToolCall(
                id="prelive-action",
                name="apply_patch",
                arguments={
                    "path": "components/a/main.py",
                    "content": "VALUE = 1\n",
                },
            )
            result = environment.execute("A", call, turn=1)
            log = EventLog(path, "prelive")
            log.append(
                EventKind.TOOL_REQUEST,
                {**call.model_dump(mode="json"), "turn": 1},
                actor="A",
                global_action_index=1,
            )
            log.append(
                EventKind.TOOL_RESULT,
                {
                    "call_id": call.id,
                    "tool_name": call.name,
                    "turn": 1,
                    **result.model_dump(mode="json"),
                },
                actor="A",
                global_action_index=1,
            )
            final = log.append(
                EventKind.FINAL,
                {"state": environment.snapshot()},
                global_action_index=1,
            )
            closure = {
                "event_count": 3,
                "final_event_id": final.event_id,
                "final_event_hash": final.event_hash,
            }
            events = read_events(path, closure=closure)
            if any(event.event_hash != calculate_event_hash(event) for event in events):
                raise PreLiveIntegrityError("written event hash is not canonical")

            fresh = RepositoryEnvironment(initial, ownership, PermissionMode.SOFT)
            replay_report = replay(path, fresh)
            if not replay_report.ok or replay_report.actions != 1:
                raise PreLiveIntegrityError("local replay round trip diverged")

            duplicate = Path(temporary) / "duplicate-final.jsonl"
            duplicate_log = EventLog(duplicate, "duplicate")
            duplicate_log.append(EventKind.FINAL, {})
            duplicate_log.append(EventKind.FINAL, {})
            try:
                read_events(duplicate)
            except ValueError as exc:
                if "duplicate FINAL" not in str(exc):
                    raise PreLiveIntegrityError(
                        "duplicate FINAL rejection was not specific"
                    ) from exc
            else:
                raise PreLiveIntegrityError("duplicate FINAL was accepted")
    except PreLiveIntegrityError:
        raise
    except Exception as exc:
        raise PreLiveIntegrityError(
            f"pre-live event integrity self-test failed: {exc}"
        ) from exc
