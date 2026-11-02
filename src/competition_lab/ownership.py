from __future__ import annotations

from pathlib import PurePosixPath

# Bumped whenever the event/manifest or ActionResult schema changes in a way
# that makes previously recorded episodes non-comparable. Recorded in every
# manifest so that stale artifacts fail loudly instead of being reanalyzed.
SCHEMA_VERSION = "2"


def normalize_prefix(prefix: str) -> str:
    """Normalize an ownership prefix to a trailing-slash directory form.

    Ownership prefixes are authored in task YAML (``writable:``) and may or may
    not carry a trailing slash. Comparing with a bare ``str.startswith`` would
    make ``components/a`` authorize ``components/ab/x.py``, so every prefix is
    normalized here and compared component-wise by :func:`is_authorized`.
    """
    path = PurePosixPath(prefix)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"ownership prefix must be relative and normal: {prefix!r}")
    if not path.parts:
        raise ValueError("ownership prefix must not be empty")
    return "/".join(path.parts) + "/"


class OwnershipMap:
    """Immutable actor -> owned path prefixes map with component-wise matching."""

    def __init__(self, mapping: dict[str, tuple[str, ...]]) -> None:
        self._prefixes: dict[str, tuple[tuple[str, ...], ...]] = {}
        for actor, prefixes in mapping.items():
            self._prefixes[actor] = tuple(
                tuple(normalize_prefix(p).rstrip("/").split("/")) for p in prefixes
            )

    def is_authorized(self, actor: str, target: str) -> bool:
        parts = PurePosixPath(target).parts
        return any(
            parts[: len(prefix)] == prefix
            for prefix in self._prefixes.get(actor, ())
        )

    def owner_of(self, target: str) -> str | None:
        """Return the single declared owner of a target, or None if unowned."""
        owners = [a for a in self._prefixes if self.is_authorized(a, target)]
        if len(owners) > 1:
            raise ValueError(f"target {target!r} has multiple declared owners")
        return owners[0] if owners else None

    def as_dict(self) -> dict[str, list[str]]:
        return {
            actor: ["/".join(prefix) + "/" for prefix in prefixes]
            for actor, prefixes in sorted(self._prefixes.items())
        }
