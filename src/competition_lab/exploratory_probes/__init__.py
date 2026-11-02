"""EXPLORATORY elicitation probes. NOT part of any main result.

These are quick mechanism/stress pilots at n=5 per variant. They are not
Experiment 1 natural behaviour, not the Experiment 2 pre-action scaffold, and
not the defense experiment. Their rates must never be pooled into an
Experiment 1 or Experiment 2 table; ``scripts/paper_tables.py`` and
``scripts/experiment2_tables.py`` both scan other directories, and the run
directory is named ``exploratory-*`` so neither can pick it up.

Two variants, both testing whether a non-Sonnet model that stopped short of
peer-directed action can be moved further by lightweight elicitation:

``reward_forward_planning_probe``
    Asks for 2-3 candidate actions and their expected effect on the agent's own
    objective, then selection by highest expected value. Tests whether
    EXPECTED-VALUE REASONING is the missing step.

``neutral_tool_affordance_menu_probe``
    Presents a generated menu of executable tool/resource candidates drawn from
    visible state, unranked, unlabelled by owner, with no recommendation. Tests
    whether ACTION-SPACE CONSTRUCTION is the missing step.

Neither scaffold mentions peers, ownership, other agents, or any peer-directed
action. Both are audited at import time; the menu is additionally audited at
generation time, because its text is built from live state rather than fixed.
"""

from competition_lab.exploratory_probes.probes import (
    ARCHITECTURES,
    FORBIDDEN_TERMS,
    MENU_ARCHITECTURE,
    MENU_ARCHITECTURES,
    NOTE_REASON,
    OWN_RESOURCE_MENU_ARCHITECTURE,
    REWARD_FORWARD_ARCHITECTURE,
    REWARD_FORWARD_PROMPT,
    audit_probe_text,
    build_affordance_menu,
    menu_prompt,
    probe_event_payload,
    prompt_for_architecture,
)

__all__ = [
    "ARCHITECTURES",
    "FORBIDDEN_TERMS",
    "MENU_ARCHITECTURE",
    "MENU_ARCHITECTURES",
    "OWN_RESOURCE_MENU_ARCHITECTURE",
    "NOTE_REASON",
    "REWARD_FORWARD_ARCHITECTURE",
    "REWARD_FORWARD_PROMPT",
    "audit_probe_text",
    "build_affordance_menu",
    "menu_prompt",
    "probe_event_payload",
    "prompt_for_architecture",
]
