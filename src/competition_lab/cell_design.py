"""DECLARED cell composition. Hand-authored from the preregistrations and
run plans. This file is UPSTREAM of the resolver and of the artifacts.

WHY IT IS NOT DERIVED. An allow-list generated from the resolver's own
output is a description of what happened, not a constraint on it. It cannot
catch the resolver: if an episode lands in an unexpected run directory, the
derived list absorbs it and the partition test still passes, because the
episode is assigned to SOME cell. The same defect shape as the abundance
validator that checked the wrong field, the Holm correction that was never
called, and the re-derivation test that derived from the rule it checked --
in each, the declared source sat downstream of the thing it was checking.

Every entry below is typed from the design documents, and the check in
`validate_against_resolver` fails in BOTH directions: a run directory the
resolver assigns but the design did not declare, and a directory the design
declares that the resolver finds empty.

reward_text_omits_peer_term: the P0 text-clean cell is DECLARED here before
it has produced episodes, which is the point -- the declaration is what the
run will be checked against, not a record of it.
"""

from __future__ import annotations

# DO NOT "IMPROVE" THIS INTO A GLOB OR A DERIVED LIST.
#
# It is hand-authored on purpose. The reason is not that deriving it is
# impossible -- `--run-name` being launch-time-only is a secondary detail.
# The reason is that A DECLARED LIST IS STRICTLY BETTER THAN A DERIVED ONE
# EVEN WHERE DERIVING IS POSSIBLE, because only a declared list can catch
# the resolver.
#
# A derived list restates what the resolver found. If the resolver
# misattributes an episode, or a run lands somewhere unplanned, the derived
# list absorbs it and every check still passes -- the episode is assigned to
# SOME cell, and the partition still sums. The error becomes invisible at
# exactly the moment it matters.
#
# A list typed from the preregistration is an independent statement of what
# the experiment was supposed to contain. Disagreement with the resolver is
# then a real signal, in both directions.
#
# Cost of maintaining it by hand: a few lines per new block.
# Cost of the defect it prevents: six silent denominator errors in one week,
# including one that merged a competitive cell with a cooperative one and so
# summed `cancel_job` with `restart_pipeline`.
#
# (model, architecture, pressure, shared_reward_weight, text_clean, family)
#   -> run directories the DESIGN says contribute, and the planned n.
#
# Sources:
#   experiment2b-menu-papergrade-completion-001  docs/menu_scaffold_findings.md
#   exploratory-*-quicktest-001                  exploratory tranche 1
#   experiment2b-menu-mechanism-controls-001     prereg 088a682
#   experiment2b-sonnet-null-p0-surface-form-001 prereg 653fec0 (this block)
_BASE_DECLARED: dict[tuple, dict] = {
    # --- Sonnet menu ladder (mechanism controls, prereg 088a682) ---
    ("sonnet", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("sonnet", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("sonnet", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("sonnet", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},

    # --- Sonnet null P0, surface-form block (prereg 653fec0) ---
    ("sonnet", "null_menu_control", "P0", 0.0, False, "behind"):
        {"runs": ("experiment2b-sonnet-null-p0-surface-form-001",), "n": 20},
    ("sonnet", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment2b-sonnet-null-p0-surface-form-001",), "n": 20},

    # --- GLM menu cells at P0, text-clean (prereg 7399fba) ---
    ("glm", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment2b-glm-p0-menu-001",), "n": 20},
    ("glm", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment2b-glm-p0-menu-001",), "n": 20},

    # --- GLM menu ladder ---
    ("glm", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-nonsonnet-cicd-p4-tool-menu-quicktest-001",
                  "experiment1-completion-003"), "n": 20},
    ("glm", "neutral_tool_affordance_menu_probe", "P4", 1.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("glm", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("glm", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-own-resource-menu-control-001",
                  "experiment1-completion-003"), "n": 20},
    ("glm", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},
    ("glm", "labelled_owner_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-mechanism-controls-001",), "n": 20},

    # --- Cross-model menu screen ---
    ("deepseek-v3.2", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-nonsonnet-cicd-p4-tool-menu-quicktest-001",
                  "experiment1-completion-003"), "n": 20},
    ("deepseek-v3.2", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-own-resource-menu-control-001",
                  "experiment1-completion-003"), "n": 20},
    ("mistral-large-3", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-nonsonnet-cicd-p4-tool-menu-quicktest-001",
                  "experiment1-completion-003"), "n": 20},
    ("mistral-large-3", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",), "n": 20},
    ("qwen3-coder-480b", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-qwen-cicd-p4-elicitation-quicktest-001",
                  "experiment1-completion-003"), "n": 20},
    ("qwen3-coder-480b", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment2b-menu-papergrade-completion-001",
                  "exploratory-own-resource-menu-control-001",
                  "experiment1-completion-003"), "n": 20},

    # --- Experiment 1 completion (prereg docs/preregistration_exp1.md) ---
    # experiment1-completion-001: ONLY the VALID cells of
    # docs/exp1_completion_001_status.md. Its other cells and all of -002 are
    # listed in EXCLUDED below and never reach a declared cell.
    # experiment1-completion-003: fresh-seed, order-balanced replacement of -002.
    ("glm", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("glm", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("sonnet", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("sonnet", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("sonnet", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "neutral_tool_affordance_menu_probe", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-001",
                  "experiment1-completion-003",), "n": 20},
    ("gpt", "own_resource_only_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-001",
                  "experiment1-completion-003",), "n": 20},
    ("gpt", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("gpt", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-001",), "n": 20},
    ("deepseek-v3.2", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("deepseek-v3.2", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("deepseek-v3.2", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("deepseek-v3.2", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("deepseek-v3.2", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("deepseek-v3.2", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("mistral-large-3", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "neutral_tool_affordance_menu_probe", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "own_resource_only_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "padded_own_resource_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "null_menu_control", "P0", 0.0, True, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "padded_own_resource_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},
    ("qwen3-coder-480b", "null_menu_control", "P4", 0.0, False, "behind"):
        {"runs": ("experiment1-completion-003",), "n": 20},

    # --- Experiment 1 replication in SOC/ITSM (prereg docs/preregistration_exp1_soc.md,
    #     tag prereg-exp1-soc-v1). Capacity 2, background load 1. Declared before
    #     any episode; P0 cells are a payoff control. ---
    ('glm', 'neutral_tool_affordance_menu_probe', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'padded_own_resource_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'own_resource_only_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'null_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'neutral_tool_affordance_menu_probe', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'padded_own_resource_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'own_resource_only_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('glm', 'null_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'neutral_tool_affordance_menu_probe', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'padded_own_resource_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'own_resource_only_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'null_menu_control', 'P0', 0.0, True, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'neutral_tool_affordance_menu_probe', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'padded_own_resource_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'own_resource_only_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},
    ('sonnet', 'null_menu_control', 'P4', 0.0, False, '-'):
        {"runs": ("exp1-soc-001",), "n": 20},

    # --- Claude Opus 5.5 on the Experiment 1 CI/CD design. EXPLORATORY added
    #     model: not under the Exp 1 prereg, not pooled. Runs at default
    #     sampling (rejects temperature). scripts/generate_exp1_opus55.py ---
    **{("opus-5.5", arch, p, 0.0, p == "P0", "behind"): {"runs": ("exp1-opus55-001",), "n": 20}
       for arch in ("neutral_tool_affordance_menu_probe", "padded_own_resource_menu_control",
                    "own_resource_only_menu_control", "null_menu_control")
       for p in ("P0", "P4")},
}


def full_key(
    base: tuple, defense: str = "none", background_load: int | None = None
) -> tuple:
    """A declared cell key with the defense-001 components appended.

    The cells above are written as six-tuples (model, architecture, pressure,
    shared_reward_weight, reward_text_omits_peer_term, task_family). Every one
    of them is UNDEFENDED, at the background load its design used: 2 for the
    CI/CD menu designs, 1 for the Exp 1 SOC design (task family "-").
    """
    if background_load is None:
        background_load = 1 if base[5] == "-" else 2
    return (*base, defense, background_load)


DECLARED: dict[tuple, dict] = {full_key(k): v for k, v in _BASE_DECLARED.items()}


# EXCLUDED episodes, by run directory and (for -001) by the run's own
# <model>/<cell> folder. Declared here, upstream of the resolver, with the
# reason; `excluded_reason` is applied BEFORE comparison with DECLARED, so an
# excluded episode can never satisfy or pad a declared cell.
EXCLUDED_RUNS: dict[str, str] = {
    "pilot-board-mislabel-001": "exploratory pilot, not preregistered: the shared queue board "
        "mislabels peer job owners; docs/pilot_board_mislabel_001_status.md",
    "pilot-soc-window-001": "exploratory pilot, not preregistered, not pooled: SOC pressure "
        "window (capacity 1, load 0, SLA 8, peer first); docs/pilot_soc_window_001_status.md",
    "pilot-soc-redesign-001": "exploratory pilot, not preregistered, not pooled: SOC redesign 2 "
        "window (expedite, peer escalated from round 0, hold 5, SLA 8, binary); "
        "docs/pilot_soc_redesign_001_status.md",
    "pilot-soc-feelloss-001": "exploratory pilot, not preregistered, not pooled: final SOC "
        "redesign (contestable first-escalation preemption, live board, no surge, hold 5, SLA 8); "
        "docs/pilot_soc_feelloss_001_status.md",
    "pilot-soc-feelloss-sonnet-001": "exploratory pilot, not preregistered, not pooled: final SOC "
        "redesign, frozen, Sonnet 4.5; docs/pilot_soc_feelloss_sonnet_001_status.md",
    "soc-v2-affordance-diagnostic-001": "exploratory, not preregistered, not pooled with any "
        "earlier SOC run: SOC-v2 affordance-legibility diagnostic (menu arms absent / enumerated / "
        "effect_stated; hold 7, SLA 12); docs/soc_v2.md",
    "soc-v2-affordance-diagnostic-002": "exploratory, not preregistered, not pooled: run 001's "
        "frozen SOC-v2 diagnostic extended to DeepSeek, Mistral, Qwen, GPT; "
        "docs/soc_v2_diagnostic_002_results.md",
    "exploratory-recent-claude-smoke-001": "exploratory smoke, not pooled: one CI/CD P4 and one "
        "SOC-v2 effect_stated episode each for Claude Sonnet 5.5 and Opus 5.5",
    "exploratory-recent-claude-reasoning-ab-001": "exploratory check, not pooled: reasoning "
        "request on vs off on the smoke seeds, Claude Sonnet 5.5 and Opus 5.5",
    "recent-claude-matched-001": "exploratory added models, not pooled: Claude Sonnet 5.5 and "
        "Opus 5.5, SOC-v2 a/b/c n=10 + CI/CD Exp 1 P4 full n=20, reasoning returned; "
        "docs/recent_claude_matched_001_results.md",
    "defense-001": "defense experiment, not pooled: GLM-5 and Sonnet 4.5 CI/CD Exp 1 P4 full "
        "under none / hard / judge gate; docs/preregistration_defense_001.md, "
        "docs/defense_001_results.md",
    "defense-002": "defense experiment, not pooled: CI/CD Exp 1 P4 full (DeepSeek, Mistral, "
        "Qwen, GPT) and SOC-v2 effect_stated (all six attack models) under none / hard / "
        "judge gate; docs/preregistration_defense_002.md, docs/defense_002_results.md",
    "r1-soc-repair-001": "revision R1, not pooled: repaired SOC (feasible sequential schedule, "
        "warranted severity), GLM/Sonnet 4.5/DeepSeek x none/hard/judge; "
        "docs/preregistration_r1_soc_repair.md, docs/r1_soc_repair_results.md",
    "r2-affordance-factorial-001": "revision R2, not pooled: CI/CD 2x2x2 incentive x "
        "visibility x payoff information, GLM/Sonnet 4.5/DeepSeek; "
        "docs/preregistration_r2_affordance_factorial.md, docs/r2_affordance_factorial_results.md",
    "experiment1-completion-002": "defective seeding: every config in a cell shared one `seed` "
        "(fixed acting order; top-ups re-ran an original's seed); docs/exp1_completion_002_status.md",
}
_WRONG_MODEL = "WRONG-MODEL: model block not replaced; docs/exp1_completion_001_status.md"
_DUP_SEED = "DUPLICATE-SEED: re-ran earlier seeds instead of topping up; docs/exp1_completion_001_status.md"
EXCLUDED_CELLS: dict[tuple[str, str, str], str] = {
    **{("experiment1-completion-001", m, c): _WRONG_MODEL
       for m in ("deepseek-v3.2", "mistral-large-3", "qwen3-coder-480b")
       for c in ("p0_full", "p0_null", "p0_own", "p0_padded", "p4_null", "p4_padded")},
    **{("experiment1-completion-001", m, c): _DUP_SEED
       for m in ("deepseek-v3.2", "mistral-large-3", "qwen3-coder-480b")
       for c in ("p4_full", "p4_own")},
    ("experiment1-completion-001", "glm", "p0_full"): _DUP_SEED,
    ("experiment1-completion-001", "glm", "p0_own"): _DUP_SEED,
    ("experiment1-completion-001", "sonnet", "p0_null"): _DUP_SEED,
}


def excluded_reason(directory, root) -> str | None:
    """Why an episode directory is excluded from the declared design, or None."""
    from pathlib import Path
    parts = Path(directory).relative_to(root).parts
    if parts[0] in EXCLUDED_RUNS:
        return EXCLUDED_RUNS[parts[0]]
    if len(parts) >= 3:
        return EXCLUDED_CELLS.get((parts[0], parts[1], parts[2]))
    return None


class DesignMismatchError(AssertionError):
    """Resolver output and declared design disagree."""


def validate_against_resolver(observed: dict[tuple, set[str]],
                              *, incomplete_ok: frozenset = frozenset()) -> dict:
    """Fail in BOTH directions.

    `observed` maps a declared cell tuple to the run directories the
    resolver actually assigned to it. `incomplete_ok` names cells that are
    mid-run, for which a short n is expected but an UNDECLARED RUN DIRECTORY
    is still a failure.
    """
    problems = []
    for key, spec in DECLARED.items():
        declared = set(spec["runs"])
        actual = observed.get(key, set())
        for extra in sorted(actual - declared):
            problems.append(
                f"{key}: resolver assigned run {extra!r}, which the design "
                "does not declare")
        if key in incomplete_ok:
            continue
        for missing in sorted(declared - actual):
            problems.append(
                f"{key}: design declares run {missing!r}, resolver found it "
                "empty")
    undeclared = set(observed) - set(DECLARED)
    for key in sorted(undeclared, key=str):
        problems.append(f"{key}: cell exists in artifacts but is not declared")
    if problems:
        raise DesignMismatchError(
            "declared design and resolver disagree:\n  " + "\n  ".join(problems))
    return {"cells_declared": len(DECLARED)}
