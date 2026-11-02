from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED = {
    "episode_id",
    # The experimental arm, NOT `pressure`. Every team and high-stakes
    # manifest carries pressure P0, so grouping on pressure pooled three arms
    # into one control stratum and reversed the reported effect. See
    # competition_lab.arms.
    "arm",
    "environment",
    "model_id",
    "successful_violation",
    "action_budget",
    "first_successful_action_index",
}

# `matched_pair_id` is deliberately absent. Pairing was never achieved and
# decision 0.3 dropped it; the matched pivot, discordant-pair count and sign
# test that consumed it are removed rather than left unreachable, which is how
# several other controls in this codebase became decorative.


def _wilson(events: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (math.nan, math.nan)
    p = events / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = (
        z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    )
    return center - half, center + half


_TRUE = {True, "true", "True", "TRUE", "1", "yes", "Yes"}
_FALSE = {False, "false", "False", "FALSE", "0", "no", "No"}


def normalize_outcome(series: pd.Series) -> pd.Series:
    """Coerce the binary outcome to strict booleans, refusing ambiguity.

    The marginal counts and the matched test must read the same values. Mixing
    ``.astype(bool)`` (any non-empty string is True) with ``== 1`` (a string
    never equals 1) silently produces contradictory marginal and matched
    results from the same CSV, so unrecognized encodings raise instead.
    """
    normalized = []
    for value in series:
        if isinstance(value, float) and math.isnan(value):
            normalized.append(pd.NA)
        elif value in _TRUE:
            normalized.append(True)
        elif value in _FALSE:
            normalized.append(False)
        else:
            raise ValueError(
                f"successful_violation must be boolean-like, got {value!r}; "
                "refusing to coerce an ambiguous outcome encoding"
            )
    return pd.Series(normalized, index=series.index, dtype="boolean")


def arm_contrasts(episodes: pd.DataFrame) -> list[dict[str, Any]]:
    """Every treatment-vs-P0 contrast present in the corpus, one per cell.

    -> one record per (environment, model, treatment arm), each carrying the
    episode-level counts, exact rates and the unadjusted p. Multiplicity
    correction is the REPORTING boundary's job, not this function's: the
    family a contrast belongs to is a preregistration decision, and applying
    it here would hide the count inside the statistics layer.

    Membership is structural -- a treatment arm is contrasted whenever its
    own cell has a P0 control. Nothing here depends on what the manuscript
    concludes.

    Replaces the previous `primary_analysis`, which subset on
    `pressure in {P0, P4}` and grouped by `pressure`. That was wrong on this
    corpus: team and high-stakes episodes carry pressure P0, so on GPT CI/CD
    it pooled team 7/20 with P0 0/20 and high-stakes 0/20 into a 7/60 "P0"
    stratum and compared it against P4 0/20 -- reversing the direction of the
    reported effect by placing the treatment inside the control.
    """
    from .arms import ARMS, arm_is_treatment
    from .exact_stats import clopper_pearson, fisher_exact, newcombe_diff

    missing = REQUIRED - set(episodes.columns)
    if missing:
        raise ValueError(f"missing episode-level columns: {sorted(missing)}")
    if episodes["episode_id"].duplicated().any():
        raise ValueError("primary statistics require one row per episode")

    frame = episodes.copy()
    unknown = set(frame["arm"].dropna().unique()) - set(ARMS)
    if unknown:
        raise ValueError(f"unrecognized arm value(s): {sorted(unknown)}")
    frame["successful_violation"] = normalize_outcome(frame["successful_violation"])
    if frame["successful_violation"].isna().any():
        raise ValueError(
            "successful_violation is missing for some episodes; missing "
            "outcomes are never imputed -- classify them explicitly"
        )

    cells: dict[tuple[str, str, str], tuple[int, int]] = {}
    for (env, model, arm), group in frame.groupby(
        ["environment", "model_id", "arm"], dropna=False
    ):
        cells[(str(env), str(model), str(arm))] = (
            int(group["successful_violation"].sum()), len(group))

    out: list[dict[str, Any]] = []
    for (env, model, arm), (events, total) in sorted(cells.items()):
        if not arm_is_treatment(arm):
            continue
        control = cells.get((env, model, "P0"))
        if control is None:
            # No within-cell control: not a contrast. Comparing across models
            # would compare units that were never randomized against each
            # other, which estimates the causal effect of nothing.
            continue
        c_events, c_total = control
        out.append({
            "environment": env,
            "model_id": model,
            "arm": arm,
            "contrast": f"{env}/{model}: {arm} vs P0",
            "treatment": {
                "events": events, "episodes": total,
                "rate": events / total if total else math.nan,
                "clopper_pearson_95": clopper_pearson(events, total),
            },
            "control": {
                "events": c_events, "episodes": c_total,
                "rate": c_events / c_total if c_total else math.nan,
                "clopper_pearson_95": clopper_pearson(c_events, c_total),
            },
            "absolute_percentage_point_difference": 100 * (
                events / total - c_events / c_total),
            "difference_95_newcombe": newcombe_diff(
                events, total, c_events, c_total),
            # Undefined rather than infinite when the control had no event: an
            # infinite point estimate reads as a measurement.
            "risk_ratio": (
                (events / total) / (c_events / c_total)
                if c_events else math.nan
            ),
            "p_raw": fisher_exact(
                events, total - events, c_events, c_total - c_events),
        })
    return out


def survival_table(episodes: pd.DataFrame) -> pd.DataFrame:
    """Kaplan-Meier violation-free survival by ARM. DESCRIPTIVE ONLY.

    Demoted from co-primary (A9). There are 13 events across 440 episodes,
    at indices {10,10,16,16,21,22,22,23,24,24,25,27,27}, and one arm has
    zero, so the hazard ratio is unestimable and a log-rank on <=7-vs-0 has
    essentially no power. Reported as a figure plus the raw index list; no
    test is computed from it and it enters no correction family.

    Grouped on `arm`, not `pressure`: team and high-stakes episodes carry
    pressure P0, so pressure-grouping merged three arms into one curve.
    """
    # A common horizon across strata: taking each group's own max budget would
    # produce ragged curves that are not comparable between arms.
    horizon = int(episodes["action_budget"].max())
    rows: list[dict[str, Any]] = []
    for arm, group in episodes.groupby("arm"):
        survival = 1.0
        for time in range(1, horizon + 1):
            # An episode is at risk only while its OWN budget allows an
            # action. Counting censored episodes past their budget inflates
            # the denominator and biases survival upward -- benign while every
            # episode has budget 40, live the moment budgets vary or corpora
            # pool.
            in_window = group["action_budget"] >= time
            at_risk = int(
                (
                    in_window
                    & (
                        group["first_successful_action_index"].isna()
                        | (group["first_successful_action_index"] >= time)
                    )
                ).sum()
            )
            events = int((group["first_successful_action_index"] == time).sum())
            if at_risk:
                survival *= 1 - events / at_risk
            rows.append(
                {
                    "arm": arm,
                    "action_index": time,
                    "at_risk": at_risk,
                    "events": events,
                    "violation_free_survival": survival,
                }
            )
    return pd.DataFrame(rows)


def holm(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values))
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, (len(p_values) - rank) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def export_outputs(episodes: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = pd.json_normalize(arm_contrasts(episodes), sep=".")
    primary_csv = output_dir / "primary_results.csv"
    primary.to_csv(primary_csv, index=False)
    survival = survival_table(episodes)
    survival_csv = output_dir / "survival.csv"
    survival.to_csv(survival_csv, index=False)
    parquet = output_dir / "episodes.parquet"
    episodes.to_parquet(parquet, index=False)
    latex = output_dir / "primary_results.tex"
    # List-valued diagnostic fields (excluded episode ids) belong in the CSV,
    # not in a LaTeX table cell.
    scalar = [c for c in primary.columns if not isinstance(primary.iloc[0][c], list)]
    headers = [str(column).replace("_", r"\_") for column in scalar]
    values = [
        f"{value:.3f}" if isinstance(value, float) else str(value)
        for value in (primary.iloc[0][c] for c in scalar)
    ]
    latex.write_text(
        "\n".join(
            [
                r"\begin{tabular}{" + "l" * len(headers) + "}",
                r"\hline",
                " & ".join(headers) + r" \\",
                r"\hline",
                " & ".join(values) + r" \\",
                r"\hline",
                r"\end{tabular}",
                "",
            ]
        )
    )
    figure = output_dir / "violation_free_survival.pdf"
    os.environ.setdefault("MPLCONFIGDIR", str(output_dir / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for arm, group in survival.groupby("arm"):
        plt.step(
            group["action_index"],
            group["violation_free_survival"],
            where="post",
            label=arm,
        )
    plt.xlabel("Global action index")
    plt.ylabel("Violation-free survival")
    plt.ylim(0, 1.02)
    plt.legend()
    plt.tight_layout()
    plt.savefig(figure)
    plt.close()
    return {
        "primary_csv": primary_csv,
        "survival_csv": survival_csv,
        "parquet": parquet,
        "latex": latex,
        "figure": figure,
    }
