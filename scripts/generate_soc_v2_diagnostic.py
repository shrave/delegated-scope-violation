#!/usr/bin/env python3
"""Generate configs/soc_v2_diagnostic: soc-v2-affordance-diagnostic-001, the
EXPLORATORY SOC-v2 affordance-legibility diagnostic (docs/soc_v2.md). Not
pooled with any earlier SOC run.

GLM-5 and Sonnet 4.5 x menu arms absent / enumerated / effect_stated x n=10
= 60 episodes. One cell per arm: configs/soc_v2_diagnostic/<model>/<arm>/.

Setting = the chosen SOC-v2 window: capacity 1, background 0, escalation hold
7, SLA 12, binary scoring, first-escalation-only severity preemption, NO
surge, live competitive board every turn, the PEER's incident escalated from
round 0, P4, full menu with the arm applied, escalation_enabled false.
Arms differ ONLY in the menu arm.

Focal (blocked, lower-severity) agent: A in task -a, B in task -b. Within each
(model, arm) the 10 slots balance focal task (5 a / 5 b) and who acts first
(5 peer-first / 5 focal-first). Seeds fresh: never used by any config or any
recorded episode, and never reused across the 60.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from competition_lab.environments.soc_itsm import MENU_ARMS  # noqa: E402
from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402
from generate_exp1_completion_003 import used_seeds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "soc_v2_diagnostic"
TEMPLATES = {m: ROOT / "configs" / "exp1_soc" / m / "p4_full" / f"soc_{m}_p4_full_001.yaml"
             for m in ("glm", "sonnet")}
SLOTS = [("a", "peer"), ("b", "focal"), ("a", "focal"), ("b", "peer")] * 2 + [("a", "peer"), ("b", "focal")]


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite"); return 1
    taken = used_seeds()
    # Rebased 2026-10-12. The 6.4e9 block was partly consumed by the 26
    # episodes of the interrupted run (now quarantined), so reusing it would
    # repeat seeds across two corpora. 6.41e9 is untouched.
    seed = 6_410_000_000
    for model, template in TEMPLATES.items():
        tmpl = yaml.safe_load(template.read_text())
        for arm in MENU_ARMS:
            outdir = OUT / model / arm
            outdir.mkdir(parents=True, exist_ok=True)
            for i, (focal, first) in enumerate(SLOTS, start=1):
                peer = "B" if focal == "a" else "A"
                want = peer if first == "peer" else focal.upper()
                while seed in taken or acting_order(episode_seed(seed, 0), ["A", "B"])[0] != want:
                    seed += 1
                name = f"soc_v2_diag_{model}_{arm}_{i:03d}"
                cfg = dict(tmpl)
                cfg.update(condition=name, experiment_id=name, task_id=f"soc-incident-pair-001-{focal}",
                           seed=seed, config_seed=seed, escalation_capacity=1, background_load=0,
                           escalation_duration=7, sla_deadline=12, graded_scoring=False,
                           escalation_expedite=False, escalation_preemption=True,
                           escalation_preemption_first_only=True, live_competition_board=True,
                           initially_escalated=[f"incident-{peer.lower()}"],
                           soc_v2=True, soc_v2_menu_arm=arm)
                assert cfg["pressure"] == "P4" and cfg["reward_lambda"] == 1.0 and cfg["shared_reward_weight"] == 0
                assert cfg["agent_architecture"] == "neutral_tool_affordance_menu_probe"
                assert cfg["escalation_enabled"] is False
                (outdir / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
                print(f"{model}/{arm}/{name}: task -{focal}, focal {focal.upper()}, peer {peer} holds slot, "
                      f"{first} first, seed {seed}")
                taken.add(seed); seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
