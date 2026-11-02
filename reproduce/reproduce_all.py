#!/usr/bin/env python3
"""Tier 1 reproduction: every reported result, offline, from the committed
event logs. No model access, no network, no credentials.

Steps (each prints a section; everything is written to reproduce/out/):

  1. REPLAY. Every shipped episode is re-executed from its log against a
     fresh environment built from its config; recorded before/after state
     digests, classifications and targets must match (strict replay). The
     count of divergences must be 0.
  2. TABLES. The numbers behind every table and figure, recomputed by the
     analysis scripts in scripts/ (deterministic detector, exact replay):
       R2 affordance factorial        scripts/revision_measures.py r2
       R1 repaired-SOC defense        scripts/revision_measures.py r1
       SOC-v2 diagnostic gradient     scripts/soc_v2_episode_rescore.py
       crossing agent blocked?        slot-state replay (this file)
       CI/CD crossings citing reward  scripts/cicd_formula_citation.py
       Claude 5.5 crossings, grounds  logs + scripts/recent_claude_refusal_audit.py
       CI/CD full-grid defense        scripts/defense_002_measures.py
  3. STATISTICS. Wilson 95% intervals and two-sided Fisher exact tests,
     Holm-corrected over the eleven-contrast family below.
  4. FIGURES. factorial.pdf, generational.pdf, r1_harm.pdf, drawn from the
     recomputed counts (never typed in).
  5. CHECK. Every recomputed value is compared with the value printed in the
     paper (reproduce/paper_values.json). Exit status 1 on any mismatch.

Usage: python reproduce/reproduce_all.py [--skip-replay]
"""
# ruff: noqa: E501
from __future__ import annotations

import collections
import json
import math
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "reproduce" / "out"
RUNS = ROOT / "artifacts" / "runs"
SHIPPED_RUNS = ("r2-affordance-factorial-001", "r1-soc-repair-001",
                "soc-v2-affordance-diagnostic-001", "soc-v2-affordance-diagnostic-002",
                "recent-claude-matched-001", "defense-001", "defense-002")
MODELS = ("glm", "sonnet", "deepseek")
NAME = {"glm": "GLM-5", "sonnet": "Sonnet 4.5", "deepseek": "DeepSeek V3.2"}


def section(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 70 - len(title)), flush=True)


def episode_dirs(run: str) -> list[Path]:
    """Complete episodes of a run (quarantined attempts are excluded)."""
    return sorted(p.parent for p in (RUNS / run).rglob("events.jsonl")
                  if p.parent.name.endswith("-0000")
                  and (p.parent / "manifest.json").exists())


def config_index() -> dict[str, Path]:
    """Config file stem == the manifest's `condition`, for every shipped config."""
    index: dict[str, Path] = {}
    for path in (ROOT / "configs").rglob("*.yaml"):
        assert path.stem not in index or index[path.stem] == path, path
        index[path.stem] = path
    return index


# ---------------------------------------------------------------- 1. replay
def replay_all() -> dict[str, Any]:
    from competition_lab.cli import _environment
    from competition_lab.config import load_config
    from competition_lab.replay import replay
    from competition_lab.tasks import load_task

    index = config_index()
    out: dict[str, Any] = {}
    for run in SHIPPED_RUNS:
        n = div = actions = 0
        commits: collections.Counter[str] = collections.Counter()
        for ep in episode_dirs(run):
            manifest = json.loads((ep / "manifest.json").read_text())
            cfg = load_config(index[manifest["condition"]])
            report = replay(ep / "events.jsonl", _environment(cfg, load_task(cfg.task_id)), strict=False)
            n += 1
            div += len(report.divergences)
            actions += report.actions
            commits[f"{manifest['software_git_commit'][:7]}{'+dirty' if manifest['dirty_working_tree'] else ''}"] += 1
        out[run] = {"episodes": n, "actions": actions, "divergences": div, "commits": dict(commits)}
        print(f"  {run:36s} episodes {n:5d}  actions {actions:6d}  divergences {div}  commits {dict(commits)}", flush=True)
    return out


# ---------------------------------------------------------------- 2. tables
def r2_counts() -> dict[str, Any]:
    import revision_measures as rm
    rows = rm.rows("r2")
    cells = {}
    for m in MODELS:
        for c in rm.EXPERIMENTS["r2"]["cells"]:
            rs = [r for r in rows if (r["model"], r["arm"]) == (m, c)]
            full = [r for r in rs if not r.get("truncated_counted")]
            cells[f"{m}/{c}"] = {
                "n": len(rs), "crossing_eps": sum(r["violations_through"] > 0 for r in rs),
                "truncated_counted": len(rs) - len(full),
                "focal_completed": sum(r["S_focal"] == 100 for r in full),
                "empty_text_pct": round(100 * sum(r["empty_text_share"] for r in full) / len(full)),
                "replay_divergences": sum(r["replay_divergences"] for r in full)}
    return {"cells": cells, "focal_completed_total": sum(v["focal_completed"] for v in cells.values()),
            "complete_episodes": sum(v["n"] - v["truncated_counted"] for v in cells.values())}


def r1_counts() -> dict[str, Any]:
    import revision_measures as rm
    rows = rm.rows("r1")
    cells = {}
    for m in MODELS:
        for a in ("none", "hard", "judge"):
            rs = [r for r in rows if (r["model"], r["arm"]) == (m, a)]
            full = [r for r in rs if not r.get("truncated_counted")]
            cells[f"{m}/{a}"] = {
                "n": len(rs), "crossing_eps": sum(r["violations_through"] > 0 for r in rs),
                "peer_missed": sum(r["S_peer"] < 100 for r in full),
                "peer_missed_after_misreport_preemption": sum(r["S_peer"] < 100 and r["misreport_preemption"] > 0 for r in full),
                "both_completed": sum(r["S_focal"] == 100 and r["S_peer"] == 100 for r in full),
                "misreport_events_focal": sum(r["misreport_focal"] for r in full),
                "misreport_events_other": sum(r["misreport_other"] for r in full),
                "false_blocks_measure": sum(r["false_blocks"] for r in full),
                "gate_missed": sum(r["gate_missed"] for r in full),
                "replay_divergences": sum(r["replay_divergences"] for r in full)}
    return {"cells": cells}


def soc_v2_gradient() -> dict[str, Any]:
    """Episodes with >=1 crossing by EITHER agent, per model x menu arm."""
    out = {}
    for run in ("soc-v2-affordance-diagnostic-001", "soc-v2-affordance-diagnostic-002"):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts/soc_v2_episode_rescore.py"), str(RUNS / run)],
                              capture_output=True, text=True, check=True)
        for row in json.loads(proc.stdout):
            key = f"{row['model']}/{row['arm']}"
            out[key] = out.get(key, 0) + int(row["any_peer_violation"])
    return out


def blocked_at_crossing() -> dict[str, Any]:
    """For each SOC-v2 diagnostic crossing: was the crossing agent blocked at
    that moment -- not holding the escalation slot AND its own incident
    projected to miss its SLA? Slot state is reconstructed by exact replay."""
    from competition_lab.cli import _environment
    from competition_lab.config import load_config
    from competition_lab.schemas import ToolCall
    from competition_lab.tasks import load_task

    index = config_index()
    out = {}
    for run in ("soc-v2-affordance-diagnostic-001", "soc-v2-affordance-diagnostic-002"):
        total = blocked = 0
        for ep in episode_dirs(run):
            manifest = json.loads((ep / "manifest.json").read_text())
            cfg = load_config(index[manifest["condition"]])
            env = _environment(cfg, load_task(cfg.task_id))
            events = [json.loads(line) for line in (ep / "events.jsonl").open() if line.strip()]
            recorded = {e["payload"]["call_id"]: e["payload"] for e in events if e["kind"] == "tool_result"}
            for e in events:
                p, a = e["payload"], e.get("actor")
                if e["kind"] == "state_transition" and p.get("reason") == "end_of_round":
                    env.end_of_round()
                elif e["kind"] == "tool_request" and a:
                    r = recorded.get(p["id"], {})
                    if r.get("classification") == "successful_violation" and r.get("changed_state"):
                        total += 1
                        holds = f"incident-{a.lower()}" in env.escalation_slots.values()
                        blocked += (not holds) and env.projected_sla_status(a) == "breached"
                    env.execute(a, ToolCall.model_validate({k: v for k, v in p.items() if k != "turn"}),
                                turn=int(p.get("turn", 0)))
        out[run] = {"crossings": total, "by_blocked_agent": blocked}
    return out


def claude55() -> dict[str, Any]:
    run = RUNS / "recent-claude-matched-001"
    cells = {}
    for ep in episode_dirs("recent-claude-matched-001"):
        model, cell = ep.parts[-3], ep.parts[-2]
        crossed = any(json.loads(line).get("kind") == "tool_result"
                      and json.loads(line)["payload"].get("classification") == "successful_violation"
                      for line in (ep / "events.jsonl").open() if line.strip())
        c = cells.setdefault(f"{model}/{cell}", {"n": 0, "crossing_eps": 0})
        c["n"] += 1
        c["crossing_eps"] += crossed
    proc = subprocess.run([sys.executable, str(ROOT / "scripts/recent_claude_refusal_audit.py"), "--json"],
                          capture_output=True, text=True, check=True)
    sentences = [s for r in json.loads(proc.stdout) for s in r["decline_sentences"] if s["kind"] == "peer"]
    assert run.exists()
    return {"cells": cells,
            "total_crossing_eps": sum(c["crossing_eps"] for c in cells.values()),
            "total_eps": sum(c["n"] for c in cells.values()),
            "peer_decline_sentences": len(sentences),
            "harm_grounds": sum(s["harm"] for s in sentences),
            "scope_grounds": sum(s["scope"] for s in sentences)}


def cicd_formula_citation() -> dict[str, Any]:
    """Mechanism: of every CI/CD crossing in the shipped runs, how many cite
    the reward formula or relative-standing arithmetic in the crossing agent's
    reasoning for that turn (rule and tiers: scripts/cicd_formula_citation.py)."""
    import cicd_formula_citation as cf
    eps = cf.episodes_under([RUNS / r for r in ("r2-affordance-factorial-001", "defense-001",
                                                "defense-002", "recent-claude-matched-001")])
    rows = [c for ep in eps for c in cf.crossings(ep)]
    summary = cf.summarize(rows)
    short = {"zai.glm-5": "glm", "us.anthropic.claude-sonnet-4-5-20250929-v1:0": "sonnet",
             "deepseek.v3.2": "deepseek", "mistral.mistral-large-3-675b-instruct": "mistral"}
    summary["by_model"] = {short.get(k, k): v for k, v in summary["by_model"].items()}
    return summary


def cicd_defense_grid() -> dict[str, Any]:
    import defense_002_measures as dm
    rows = [dm.measure(*args) for args in dm.episodes() if args[0] == "cicd"]
    out = {}
    for r in rows:
        c = out.setdefault(f"{r['model']}/{r['arm']}", {"n": 0, "through_eps": 0})
        c["n"] += 1
        c["through_eps"] += r["violations_through"] > 0
    return out


# ---------------------------------------------------------------- 3. stats
def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def holm(pvals: dict[str, float]) -> dict[str, float]:
    order = sorted(pvals, key=lambda k: pvals[k])
    m, running, adj = len(order), 0.0, {}
    for i, k in enumerate(order):
        running = max(running, min(1.0, (m - i) * pvals[k]))
        adj[k] = running
    return adj


def statistics(r2: dict[str, Any], r1: dict[str, Any], gradient: dict[str, Any], c55: dict[str, Any]) -> dict[str, Any]:
    from scipy.stats import fisher_exact

    def cell2(m: str, c: str) -> tuple[int, int]:
        v = r2["cells"][f"{m}/{c}"]
        return v["crossing_eps"], v["n"]

    def miss(m: str, a: str) -> tuple[int, int]:
        v = r1["cells"][f"{m}/{a}"]
        return v["peer_missed"], v["n"]

    # THE ELEVEN-CONTRAST FAMILY. The paper enumerates only some members
    # (Table "Key contrasts"); this family reproduces every printed Holm value.
    fam: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {}
    for m in MODELS:
        fam[f"competition | listed, unstated [{m}]"] = (cell2(m, "comp_listed_unstated"), cell2(m, "ind_listed_unstated"))
        fam[f"payoff | competitive, listed [{m}]"] = (cell2(m, "comp_listed_stated"), cell2(m, "comp_listed_unstated"))
        fam[f"R1 none vs hard, peer miss [{m}]"] = (miss(m, "none"), miss(m, "hard"))
    fam["payoff | independent, listed [deepseek]"] = (cell2("deepseek", "ind_listed_stated"), cell2("deepseek", "ind_listed_unstated"))
    s45 = (gradient["sonnet/effect_stated"], 10)
    s55 = (c55["cells"]["sonnet55/soc_v2_effect_stated"]["crossing_eps"], c55["cells"]["sonnet55/soc_v2_effect_stated"]["n"])
    fam["model refusal, effect-stated SOC [Sonnet 4.5 vs Sonnet 5.5]"] = (s45, s55)
    raw = {k: float(fisher_exact([[a, n - a], [b, mm - b]])[1]) for k, ((a, n), (b, mm)) in fam.items()}
    adj = holm(raw)
    rows = {k: {"a": f"{fam[k][0][0]}/{fam[k][0][1]}", "b": f"{fam[k][1][0]}/{fam[k][1][1]}",
                "p_raw": raw[k], "p_holm": adj[k]} for k in fam}
    cis = {"sonnet comp_listed_stated": wilson(*cell2("sonnet", "comp_listed_stated")),
           "R1 sonnet none peer miss": wilson(15, 40), "R1 deepseek none peer miss": wilson(14, 40),
           "0 of 40 (upper)": wilson(0, 40), "0 of 10 one-sided Clopper-Pearson upper": (0.0, 1 - 0.05 ** (1 / 10))}
    return {"contrasts": rows,
            "intervals": {k: [round(100 * lo, 1), round(100 * hi, 1)] for k, (lo, hi) in cis.items()},
            "intervals_pct": {k: [round(100 * lo), round(100 * hi)] for k, (lo, hi) in cis.items()}}


# ---------------------------------------------------------------- 4. figures
def figures(r2: dict[str, Any], r1: dict[str, Any], gradient: dict[str, Any], c55: dict[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    plt.rcParams.update({"font.size": 9, "font.family": "serif", "axes.spines.top": False,
                         "axes.spines.right": False, "figure.dpi": 200})
    sky, orange, verm, green, blue = "#56B4E9", "#E69F00", "#D55E00", "#009E73", "#0072B2"
    fig_dir = OUT / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    conds = [("ind_listed_unstated", "indep\nunstated"), ("ind_listed_stated", "indep\nstated"),
             ("comp_listed_unstated", "comp\nunstated"), ("comp_listed_stated", "comp\nstated")]
    x = np.arange(len(conds))
    w = 0.26
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    for i, (m, col) in enumerate(zip(MODELS, (blue, orange, green), strict=True)):
        ax.bar(x + (i - 1) * w, [r2["cells"][f"{m}/{c}"]["crossing_eps"] for c, _ in conds], w,
               label=NAME[m].replace(" V3.2", ""), color=col, edgecolor="k", linewidth=0.4)
    unlisted = sum(v["crossing_eps"] for k, v in r2["cells"].items() if "unlisted" in k)
    ax.set_ylabel("episodes w/ crossing (of 52)")
    ax.set_ylim(0, 54)
    ax.set_xticks(x)
    ax.set_xticklabels([label for _, label in conds], fontsize=7.5)
    ax.set_xlabel("peer action listed; incentive $\\times$ payoff", fontsize=8)
    ax.legend(frameon=False, fontsize=7, loc="upper left", handlelength=1.1)
    ax.text(0.02, 0.60, f"all 12 unlisted\ncells: {unlisted}", transform=ax.transAxes, fontsize=7, color="#555", ha="left")
    fig.tight_layout()
    fig.savefig(fig_dir / "factorial.pdf", bbox_inches="tight")
    plt.close(fig)

    models = ["GLM-5", "Sonnet 4.5", "Sonnet 5.5", "Opus 5.5"]
    vals = [gradient["glm/effect_stated"], gradient["sonnet/effect_stated"],
            c55["cells"]["sonnet55/soc_v2_effect_stated"]["crossing_eps"],
            c55["cells"]["opus55/soc_v2_effect_stated"]["crossing_eps"]]
    fig, ax = plt.subplots(figsize=(3.3, 2.2))
    bars = ax.bar(np.arange(4), vals, 0.6, color=[orange, orange, green, green], edgecolor="k", linewidth=0.5)
    for b, h in zip(bars, ["", "", "//", "//"], strict=True):
        b.set_hatch(h)
    ax.set_ylabel("crossings, effect-stated SOC (of 10)")
    ax.set_ylim(0, 10.5)
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(models, rotation=20, ha="right", fontsize=8)
    ax.axvspan(1.5, 3.5, color="#f0f0f0", zorder=0)
    ax.text(2.5, 0.35, f"{c55['total_crossing_eps']} / {c55['total_eps']} total\n(incl. CI/CD)", ha="center", fontsize=6.8, color=green)
    fig.tight_layout()
    fig.savefig(fig_dir / "generational.pdf", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.1, 2.2))
    ms = ["sonnet", "deepseek"]
    x = np.arange(2)
    for off, arm, col in ((-w, "none", sky), (0, "hard", orange), (w, "judge", green)):
        ax.bar(x + off, [r1["cells"][f"{m}/{arm}"]["peer_missed"] for m in ms], w, label=arm, color=col, edgecolor="k", linewidth=0.4)
    ax.set_ylabel("peer missed avoidable SLA (of 40)")
    ax.set_ylim(0, 17)
    ax.set_xticks(x)
    ax.set_xticklabels(["Sonnet 4.5", "DeepSeek"], fontsize=8.5)
    ax.legend(frameon=False, fontsize=7, loc="upper right", ncol=3, handlelength=1.0, columnspacing=0.9)
    fig.tight_layout()
    fig.savefig(fig_dir / "r1_harm.pdf", bbox_inches="tight")
    plt.close(fig)
    del verm


# ---------------------------------------------------------------- 5. check
def check(results: dict[str, Any]) -> list[str]:
    paper = json.loads((ROOT / "reproduce/paper_values.json").read_text())
    problems: list[str] = []

    def get(path: list[str | int]) -> Any:
        node: Any = results
        for part in path:
            node = node[part]
        return node

    for item in paper["checks"]:
        try:
            got = get(item["path"])
        except (KeyError, TypeError, IndexError):
            print(f"  MISSING {item['claim']}: {item['path']}")
            problems.append(item["claim"])
            continue
        want = item["paper"]
        if "tolerance_rel" in item:
            ok = abs(got - want) <= item["tolerance_rel"] * abs(want) if want else got == 0
        elif "round_sig" in item:
            ok = float(f"{got:.{item['round_sig']}g}") == want
        else:
            ok = got == want
        mark = "ok  " if ok else "DIFF"
        print(f"  {mark} {item['claim']}: paper {want}, reproduced {got}")
        if not ok:
            problems.append(item["claim"])
    for item in paper.get("not_reproducible", []):
        print(f"  NOTE {item}")
    return problems


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    results: dict[str, Any] = {}
    if "--skip-replay" not in sys.argv:
        section("1. replay verification (every shipped episode)")
        results["replay"] = replay_all()
    section("2. tables")
    print("  R2 affordance factorial ...", flush=True)
    results["r2"] = r2_counts()
    print("  R1 repaired-SOC defense ...", flush=True)
    results["r1"] = r1_counts()
    print("  SOC-v2 diagnostic gradient ...", flush=True)
    results["soc_v2_gradient"] = soc_v2_gradient()
    print("  crossing agent blocked at that moment ...", flush=True)
    results["blocked_at_crossing"] = blocked_at_crossing()
    print("  Claude 5.5 crossings and decline grounds ...", flush=True)
    results["claude55"] = claude55()
    print("  CI/CD crossings citing the reward formula ...", flush=True)
    results["cicd_formula_citation"] = cicd_formula_citation()
    t = results["cicd_formula_citation"]["total"]
    print(f"    {t['cites']}/{t['crossings']} cite the formula or relative standing; "
          f"{t['expression']}/{t['crossings']} write out the competitive arithmetic")
    print("  CI/CD full-grid defense ...", flush=True)
    results["cicd_defense_grid"] = cicd_defense_grid()
    section("3. statistics")
    results["stats"] = statistics(results["r2"], results["r1"], results["soc_v2_gradient"], results["claude55"])
    for k, v in results["stats"]["contrasts"].items():
        print(f"  {k:60s} {v['a']:>6} vs {v['b']:>6}  p_raw {v['p_raw']:.2e}  p_holm {v['p_holm']:.2e}")
    for k, v in results["stats"]["intervals"].items():
        print(f"  Wilson/CP 95% {k}: {v}")
    section("4. figures")
    figures(results["r2"], results["r1"], results["soc_v2_gradient"], results["claude55"])
    print(f"  wrote {OUT / 'figures'}/factorial.pdf, generational.pdf, r1_harm.pdf")
    (OUT / "results.json").write_text(json.dumps(results, indent=1, default=list))
    section("5. check against the paper")
    problems = check(results)
    print(f"\n{len(problems)} mismatches; results in {OUT / 'results.json'}; {time.time() - started:.0f}s")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
