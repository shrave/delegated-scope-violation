"""Experiment 2 -- Option-Structured Mechanism Probe (action_space_elicitation).

SELF-CONTAINED PACKAGE. Everything specific to Experiment 2 lives here so the
probe can be extracted, packaged, or dropped without touching Experiment 1.
``orchestration.py`` holds a single dispatch hook and nothing else; the scaffold
text, the non-suggestiveness audit, the two-phase driver and the mechanism
metrics are all defined in this package.

WHAT THIS EXPERIMENT IS FOR
---------------------------
Experiment 1 established WHERE delegated-scope overreach appears: GPT crossed
in 7/20 CI/CD team episodes and 0/20 SOC team episodes, with identical shared
reward, identical detector and identical delegation rules. It could not
establish WHY, because GPT emitted almost no text (93% empty turns), so its
action-space representation was never observable.

This probe tests one mechanism question:

    Do models fail to cross because they cannot represent another agent's
    resource as actionable, or because the standard telemetry-aware interface
    does not elicit that representation?

It is a MECHANISM PROBE, not natural behaviour. Asking for a structured note
is itself an intervention, so Experiment 2 results are reported separately and
are NEVER pooled into Experiment 1 rates.

WHAT IT IS NOT
--------------
It is not a defense and not Experiment 3. The scaffold deliberately contains no
compliance language -- no "only choose actions within delegation", no "do not
act on another agent", no "explain why this is allowed". It elicits
representation; it does not enforce a boundary. Adding compliance wording here
would confound the mechanism question with a mitigation.
"""

from competition_lab.experiment2.metrics import (
    MECHANISM_FIELDS,
    score_option_note,
)
from competition_lab.experiment2.scaffold import (
    FORBIDDEN_TERMS,
    OPTION_STRUCTURED_PHASE1_PROMPT,
    OPTION_STRUCTURED_PHASE2_PROMPT,
    audit_scaffold_text,
)

__all__ = [
    "FORBIDDEN_TERMS",
    "MECHANISM_FIELDS",
    "OPTION_STRUCTURED_PHASE1_PROMPT",
    "OPTION_STRUCTURED_PHASE2_PROMPT",
    "audit_scaffold_text",
    "score_option_note",
]
