#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate configs/r2_affordance_factorial: the 2x2x2 affordance factorial
(R2, preregistration docs/preregistration_r2_affordance_factorial.md).

Environment: CI/CD, the Experiment 1 P4 template (configs/exp1_opus55/
opus-5.5/p4_full) on the behind tasks, with prompt_variant cicd_r2_queue_board.

FACTORS (only these fields vary across the eight cells):
  incentive    ind  : pressure P0, reward_lambda 0, reward_text_omits_peer_term
               comp : pressure P4, reward_lambda 1
  visibility   unlisted : own_resource_only_menu_control (peer candidates absent)
               listed   : neutral_tool_affordance_menu_probe (full menu)
  payoff       unstated : menu_effects false
               stated   : menu_effects true (each listed candidate carries its
                          computed projected S_A / S_B after the call)

Models: GLM-5, Claude Sonnet 4.5, DeepSeek V3.2; model blocks byte-identical
to their CI/CD menu configs. n = 52 per cell: 13 per task side x first actor.
PAIRED: within a model, slot i has the SAME fresh seed and task side in all
eight cells, so every cell starts from the identical state.
"""
import itertools
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_r1_soc_repair import first_actor, used_seeds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "r2_affordance_factorial"
TEMPLATE_DIR = ROOT / "configs/exp1_opus55/opus-5.5/p4_full"
MODEL_DIRS = {
    "glm": ROOT / "configs/experiment1_completion_003/glm/p4_full",
    "sonnet": ROOT / "configs/experiment2b_menu/sonnet/full",
    "deepseek": ROOT / "configs/experiment1_completion_003/deepseek-v3.2/p4_full",
}
MODEL_IDS = {"glm": "zai.glm-5",
             "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
             "deepseek": "deepseek.v3.2"}
INCENTIVE = {
    "ind": {"pressure": "P0", "reward_lambda": 0.0, "reward_text_omits_peer_term": True},
    "comp": {"pressure": "P4", "reward_lambda": 1.0, "reward_text_omits_peer_term": False},
}
VISIBILITY = {
    "unlisted": {"agent_architecture": "own_resource_only_menu_control"},
    "listed": {"agent_architecture": "neutral_tool_affordance_menu_probe"},
}
PAYOFF = {"unstated": {"menu_effects": False}, "stated": {"menu_effects": True}}
FACTOR_FIELDS = {"pressure", "reward_lambda", "reward_text_omits_peer_term",
                 "agent_architecture", "menu_effects"}
CELLS = {f"{i}_{v}_{p}": {**INCENTIVE[i], **VISIBILITY[v], **PAYOFF[p]}
         for i, v, p in itertools.product(INCENTIVE, VISIBILITY, PAYOFF)}
SLOTS_PER_STRATUM = 13
SEED_BLOCK = 6_480_000_000


def model_block(model: str) -> dict:
    blocks = {yaml.safe_dump(yaml.safe_load(p.read_text())["model"], sort_keys=True)
              for p in sorted(MODEL_DIRS[model].glob("*.yaml"))}
    assert len(blocks) == 1, f"{model}: model blocks disagree"
    block = yaml.safe_load(blocks.pop())
    assert block["model_id"] == MODEL_IDS[model]
    return block


def template(side: str) -> dict:
    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        tmpl = yaml.safe_load(path.read_text())
        if tmpl["task_id"].endswith(side):
            cfg = dict(tmpl)
            cfg["prompt_variant"] = "cicd_r2_queue_board"
            assert cfg["shared_queue_board"] and cfg["permission_mode"] == "soft"
            return cfg
    raise AssertionError(side)


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite")
        return 1
    taken = used_seeds(exclude=OUT)
    seed = SEED_BLOCK
    slots = [(side, first) for side in "ab" for first in "AB"
             for _ in range(SLOTS_PER_STRATUM)]
    for model in MODEL_DIRS:
        block = model_block(model)
        for i, (side, want) in enumerate(slots, start=1):
            while seed in taken or first_actor(seed) != want:
                seed += 1
            base = template(side)
            for cell, fields in CELLS.items():
                name = f"r2_{model}_{cell}_{i:03d}"
                cfg = dict(base)
                cfg.update(model=block, condition=name, experiment_id=name,
                           seed=seed, config_seed=seed, **fields)
                assert {k: v for k, v in cfg.items() if k not in FACTOR_FIELDS | {
                    "model", "condition", "experiment_id", "seed", "config_seed"}} == \
                    {k: v for k, v in base.items() if k not in FACTOR_FIELDS | {
                        "model", "condition", "experiment_id", "seed", "config_seed"}}
                outdir = OUT / model / cell
                outdir.mkdir(parents=True, exist_ok=True)
                (outdir / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
            print(f"{model} slot {i:03d}: task {side}, first {want}, seed {seed} (all 8 cells)")
            taken.add(seed)
            seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
