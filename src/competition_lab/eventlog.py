from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from competition_lab.ownership import SCHEMA_VERSION
from competition_lab.schemas import Event, EventKind

GENESIS_HASH = "0" * 64


def _canonical_value(value: Any) -> Any:
    """Convert supported values to stable JSON primitives.

    Enum values are serialized explicitly rather than relying on Python's
    representation or json's treatment of StrEnum subclasses.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    """Return the one canonical byte representation used by hash I/O paths."""
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def unsigned_event(event: Event | Mapping[str, Any]) -> dict[str, Any]:
    """Extract exactly the fields committed to by an event hash."""
    if isinstance(event, Event):
        return event.model_dump(exclude={"timestamp", "event_hash"}, mode="json")
    return {
        key: event[key]
        for key in (
            "event_id",
            "episode_id",
            "kind",
            "global_action_index",
            "actor",
            "payload",
            "previous_hash",
        )
    }


def calculate_event_hash(event: Event | Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(unsigned_event(event))).hexdigest()


class EventLog:
    def __init__(self, path: Path, episode_id: str) -> None:
        self.path = path
        self.episode_id = episode_id
        self.previous_hash = GENESIS_HASH
        self.sequence = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation makes append-to-an-old-log impossible even if a
        # caller bypasses EpisodeRunner's directory guard.
        path.touch(exist_ok=False)

    def append(
        self,
        kind: EventKind,
        payload: dict[str, Any],
        *,
        actor: str | None = None,
        global_action_index: int | None = None,
    ) -> Event:
        self.sequence += 1
        event_id = f"{self.episode_id}:{self.sequence:08d}"
        unsigned: dict[str, Any] = {
            "event_id": event_id,
            "episode_id": self.episode_id,
            "kind": kind.value,
            "global_action_index": global_action_index,
            "actor": actor,
            "payload": payload,
            "previous_hash": self.previous_hash,
        }
        digest = calculate_event_hash(unsigned)
        event = Event(
            event_id=event_id,
            episode_id=self.episode_id,
            kind=kind,
            global_action_index=global_action_index,
            actor=actor,
            payload=payload,
            previous_hash=self.previous_hash,
            event_hash=digest,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        self.previous_hash = digest
        return event


def read_events(
    path: Path, verify: bool = True, closure: dict[str, Any] | None = None
) -> list[Event]:
    events = [
        Event.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    if verify:
        final_positions = [
            position
            for position, event in enumerate(events, 1)
            if event.kind == EventKind.FINAL
        ]
        if len(final_positions) > 1:
            raise ValueError(
                f"duplicate FINAL events at positions {final_positions}"
            )
        if final_positions and final_positions[0] != len(events):
            raise ValueError("FINAL event must be the last event in the log")
        previous = GENESIS_HASH
        for position, event in enumerate(events, 1):
            # The chain alone links neighbours but does not commit to position,
            # so a dropped or reordered interior event would still verify.
            expected_id = f"{event.episode_id}:{position:08d}"
            if event.event_id != expected_id:
                raise ValueError(
                    f"event sequence restart or gap: expected {expected_id}, "
                    f"found {event.event_id}"
                )
            digest = calculate_event_hash(event)
            if event.previous_hash != previous or event.event_hash != digest:
                raise ValueError(
                    f"event hash chain invalid at position {position} "
                    f"({event.event_id})"
                )
            previous = event.event_hash
        _verify_closure(events, closure)
    return events


def _verify_closure(events: list[Event], closure: dict[str, Any] | None) -> None:
    """Check the log against the manifest's closure record.

    Without this, truncating trailing events leaves a chain that still verifies
    cleanly -- the episode simply appears to have ended earlier, silently
    erasing any late violation and shifting time-to-event.
    """
    if closure is None:
        if events and events[-1].kind != EventKind.FINAL:
            raise ValueError(
                "event log does not end with a FINAL event; it may be truncated"
            )
        return
    if not events:
        raise ValueError("event log is empty but a closure record exists")
    expected_count = int(closure["event_count"])
    if len(events) != expected_count:
        raise ValueError(
            f"event count mismatch: manifest declares {expected_count}, "
            f"log contains {len(events)}"
        )
    last = events[-1]
    if last.event_id != closure["final_event_id"]:
        raise ValueError(
            f"final event id mismatch: manifest declares "
            f"{closure['final_event_id']}, log ends at {last.event_id}"
        )
    if last.event_hash != closure["final_event_hash"]:
        raise ValueError("final event hash does not match the manifest closure record")


def read_episode(episode_dir: Path) -> list[Event]:
    """Read an episode's events, enforcing the manifest closure record."""
    manifest_path = episode_dir / "manifest.json"
    closure = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        declared = manifest.get("schema_version")
        if declared != SCHEMA_VERSION:
            raise ValueError(
                f"episode {episode_dir.name} was recorded under schema version "
                f"{declared!r}, but this code expects {SCHEMA_VERSION!r}; "
                "reanalysis across schema versions is not comparable"
            )
        closure = manifest.get("episode_closure")
    return read_events(episode_dir / "events.jsonl", closure=closure)
