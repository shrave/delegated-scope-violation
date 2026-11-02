#!/usr/bin/env python3
"""Generate configs/defense_001: the defense experiment (preregistration
docs/preregistration_defense_001.md).

ATTACK, fixed and identical in every arm: Experiment 1 CI/CD P4 full
tool-affordance menu (neutral_tool_affordance_menu_probe), 20 slots balanced
5 per focal side x acting order (template: the Exp 1 P4 slots, as used by
recent-claude-matched-001). Models: GLM-5 and Claude Sonnet 4.5, model blocks
byte-identical to their Exp 1 / 2B CI/CD configs.

ARMS (only these fields differ from the template):
  none   permission_mode soft, no gate        -- the undefended attack
  hard   permission_mode hard                 -- out-of-delegation calls refused
  judge  permission_mode soft + defense_gate  -- Claude Haiku 4.5 gates every
                                                 state-changing call before it runs
PAIRED: within a model, slot i uses the SAME fresh seed in all three arms, so
each defended episode has an undefended twin with identical environment seed
and acting order. Seeds are fresh: never used by any config or recorded episode.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_exp1_completion_003 import used_seeds  # noqa: E402

from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "defense_001"
TEMPLATES = sorted((ROOT / "configs/exp1_opus55/opus-5.5/p4_full").glob("*.yaml"))


def _block(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text())["model"]


MODELS = {
    "glm": _block(
        "configs/experiment1_completion_003/glm/p4_full/e2b_glm_p4_full_016.yaml"),
    "sonnet": _block("configs/experiment2b_menu/sonnet/full/e2b_sonnet_full_001.yaml"),
}
GATE = {
    "provider": "bedrock-converse",
    "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "region": "us-west-2",
    "temperature": 0.0,
    "max_tokens": 256,
    "timeout_seconds": 60,
    "max_retries": 2,
    "input_cost_per_million": 1.0,
    "output_cost_per_million": 5.0,
}
ARMS = {
    "none": {"permission_mode": "soft"},
    "hard": {"permission_mode": "hard"},
    "judge": {"permission_mode": "soft", "defense_gate": GATE},
}
VARIES = {"model", "condition", "experiment_id", "seed", "config_seed",
          "permission_mode", "defense_gate"}


def first_actor(seed: int) -> str:
    return acting_order(episode_seed(seed, 0), ["A", "B"])[0]


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite")
        return 1
    assert len(TEMPLATES) == 20
    assert MODELS["glm"]["model_id"] == "zai.glm-5"
    sonnet_id = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    assert MODELS["sonnet"]["model_id"] == sonnet_id
    taken = used_seeds()
    seed = 6_450_000_000
    for model, block in MODELS.items():
        for i, path in enumerate(TEMPLATES, start=1):
            tmpl = yaml.safe_load(path.read_text())
            want = first_actor(tmpl["seed"])
            while seed in taken or first_actor(seed) != want:
                seed += 1
            for arm, fields in ARMS.items():
                name = f"def_{model}_{arm}_{i:03d}"
                cfg = dict(tmpl)
                cfg.update(model=block, condition=name, experiment_id=name,
                           seed=seed, config_seed=seed, **fields)
                assert {k: v for k, v in cfg.items() if k not in VARIES} == \
                    {k: v for k, v in tmpl.items() if k not in VARIES}
                outdir = OUT / model / arm
                outdir.mkdir(parents=True, exist_ok=True)
                text = yaml.safe_dump(cfg, sort_keys=True)
                (outdir / f"{name}.yaml").write_text(text)
            print(f"{model} slot {i:03d}: task {tmpl['task_id'][-1]}, first {want}, "
                  f"seed {seed} (all three arms)")
            taken.add(seed)
            seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
