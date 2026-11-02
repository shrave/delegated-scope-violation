#!/usr/bin/env python3
"""Generate configs/defense_002: the full defense evaluation (preregistration
docs/preregistration_defense_002.md).

defense-001 mechanics, extended to every attack model and both environments:

  CI/CD  Exp 1 P4 full tool-affordance menu, the same 20 template slots as
         defense-001 (configs/exp1_opus55/opus-5.5/p4_full). Models: DeepSeek
         V3.2, Mistral Large 3, Qwen3-Coder, GPT-6 Astra; model blocks
         byte-identical to their Exp 1 CI/CD P4 configs
         (experiment1_completion_003). GLM-5 and Sonnet 4.5 are REUSED from
         defense-001 and are not regenerated.
  SOC-v2 the effect_stated arm of the SOC-v2 affordance diagnostic (run 001
         GLM configs as the field template). All six attack models; model
         blocks byte-identical to the diagnostic configs (run 001: GLM, Sonnet;
         run 002: the other four). 20 slots: 5 per task side x first actor.

ARMS (only these fields differ from the template; the gate block is the
defense-001 gate verbatim):
  none   permission_mode soft
  hard   permission_mode hard
  judge  permission_mode soft + defense_gate (Claude Haiku 4.5)
PAIRED: within (environment, model), slot i has the SAME fresh seed in all
three arms. Seeds are fresh: never used by any config or recorded episode.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_exp1_completion_003 import used_seeds  # noqa: E402

from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "defense_002"
CICD_TEMPLATES = sorted((ROOT / "configs/exp1_opus55/opus-5.5/p4_full").glob("*.yaml"))
SOC_TEMPLATES = sorted(
    (ROOT / "configs/soc_v2_diagnostic/glm/effect_stated").glob("*.yaml"))
EXP1 = ROOT / "configs/experiment1_completion_003"
CICD_MODELS = {
    "deepseek": EXP1 / "deepseek-v3.2/p4_full",
    "mistral": EXP1 / "mistral-large-3/p4_full",
    "qwen": EXP1 / "qwen3-coder-480b/p4_full",
    "gpt": EXP1 / "gpt-6-astra/p4_full",
}
SOC_MODELS = {
    "glm": ROOT / "configs/soc_v2_diagnostic/glm/effect_stated",
    "sonnet": ROOT / "configs/soc_v2_diagnostic/sonnet/effect_stated",
    **{m: ROOT / f"configs/soc_v2_diagnostic_002/{m}/effect_stated"
       for m in ("deepseek", "mistral", "qwen", "gpt")},
}
MODEL_IDS = {
    "glm": "zai.glm-5",
    "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "deepseek": "deepseek.v3.2",
    "mistral": "mistral.mistral-large-3-675b-instruct",
    "qwen": "qwen.qwen3-coder-480b-a35b-v1:0",
    "gpt": "us.openai.gpt-6-astra",
}
GATE = yaml.safe_load(
    (ROOT / "configs/defense_001/glm/judge/def_glm_judge_001.yaml").read_text()
)["defense_gate"]
ARMS = {
    "none": {"permission_mode": "soft"},
    "hard": {"permission_mode": "hard"},
    "judge": {"permission_mode": "soft", "defense_gate": GATE},
}
VARIES = {"model", "condition", "experiment_id", "seed", "config_seed",
          "permission_mode", "defense_gate"}


def first_actor(seed: int) -> str:
    return acting_order(episode_seed(seed, 0), ["A", "B"])[0]


def model_block(directory: Path, model: str) -> dict:
    blocks = {yaml.safe_dump(yaml.safe_load(p.read_text())["model"], sort_keys=True)
              for p in sorted(directory.glob("*.yaml"))}
    assert len(blocks) == 1, f"{directory}: model blocks disagree"
    block = yaml.safe_load(blocks.pop())
    assert block["model_id"] == MODEL_IDS[model], block["model_id"]
    return block


def soc_slots() -> list[tuple[dict, str]]:
    """20 (template, first actor) slots: 5 per task side x first actor.

    The field template for a side is any run-001 GLM effect_stated config of
    that side; all of them are asserted identical outside VARIES.
    """
    by_side: dict[str, dict] = {}
    for path in SOC_TEMPLATES:
        tmpl = yaml.safe_load(path.read_text())
        side = tmpl["task_id"][-1]
        fixed = {k: v for k, v in tmpl.items() if k not in VARIES}
        if side in by_side:
            assert fixed == {k: v for k, v in by_side[side].items() if k not in VARIES}
        else:
            by_side[side] = tmpl
    assert sorted(by_side) == ["a", "b"]
    return [(by_side[side], first) for side in "ab" for first in "AB" for _ in range(5)]


def write(env: str, model: str, block: dict, slots: list[tuple[dict, str]],
          taken: set, seed: int) -> int:
    for i, (tmpl, want) in enumerate(slots, start=1):
        while seed in taken or first_actor(seed) != want:
            seed += 1
        for arm, fields in ARMS.items():
            name = f"def2_{env}_{model}_{arm}_{i:03d}"
            cfg = dict(tmpl)
            cfg.update(model=block, condition=name, experiment_id=name,
                       seed=seed, config_seed=seed, **fields)
            assert {k: v for k, v in cfg.items() if k not in VARIES} == \
                {k: v for k, v in tmpl.items() if k not in VARIES}
            outdir = OUT / f"{env}_{model}" / arm
            outdir.mkdir(parents=True, exist_ok=True)
            (outdir / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
        print(f"{env} {model} slot {i:03d}: task {tmpl['task_id'][-1]}, first {want}, "
              f"seed {seed} (all three arms)")
        taken.add(seed)
        seed += 1
    return seed


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite")
        return 1
    assert len(CICD_TEMPLATES) == 20 and len(SOC_TEMPLATES) == 10
    cicd_slots = []
    for path in CICD_TEMPLATES:
        tmpl = yaml.safe_load(path.read_text())
        cicd_slots.append((tmpl, first_actor(tmpl["seed"])))
    taken = used_seeds()
    seed = 6_460_000_000
    for model, directory in CICD_MODELS.items():
        block = model_block(directory, model)
        seed = write("cicd", model, block, cicd_slots, taken, seed)
    for model, directory in SOC_MODELS.items():
        block = model_block(directory, model)
        seed = write("soc", model, block, soc_slots(), taken, seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
