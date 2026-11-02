"""Single definition of "this episode is quarantined".

AUDIT 0.4. The rule lived in three script-local copies
(``scripts/paper_tables.py``, ``scripts/experiment2_tables.py``,
``scripts/experiment2b_tables.py``) and was ABSENT from the CLI's ``episodes``
and ``detect`` commands, which used bare ``rglob``. 25 quarantined
``manifest.json`` and 41 quarantined ``events.jsonl`` files were reachable that
way. Keeping one definition here means the CLI and the table builders cannot
disagree about what counts as retained data.

The match is anchored to a directory-name SUFFIX. The previous form tested
``marker in part`` for every path component, so a legitimately named directory
-- ``incomplete-data-study``, ``invalid-input-robustness`` -- would have been
silently excluded from the corpus, and a silent exclusion is indistinguishable
from a null.
"""

from __future__ import annotations

from pathlib import Path

QUARANTINE_MARKERS: tuple[str, ...] = (
    "QUARANTINE",
    "INCOMPLETE",
    "INVALID",
    "DISCARDED",
)


def is_quarantined(path: Path) -> bool:
    """True when any component of ``path`` is a quarantine-marked directory.

    A component counts as marked when a marker appears as a HYPHEN-DELIMITED
    TOKEN within it, so ``ep-001-CONCATENATED-INVALID-QUARANTINE``,
    ``run-QUARANTINE`` and ``...-DISCARDED-pair-005-incomplete`` (marker
    infixed) all match, while ``incomplete-data-study`` does not.

    Token matching rather than suffix matching is deliberate: one existing
    directory carries the marker in the middle of its name, and a suffix-only
    rule would have silently re-admitted a discarded episode.

    Markers are upper-case by convention and the comparison is case-sensitive:
    a lower-case ``invalid`` in an ordinary name must not quarantine a run.
    """
    for part in path.parts:
        tokens = set(part.split("-"))
        if tokens & set(QUARANTINE_MARKERS):
            return True
    return False
