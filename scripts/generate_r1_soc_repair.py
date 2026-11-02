#!/usr/bin/env python3
# ruff: noqa: E501
"""Generate configs/r1_soc_repair: the repaired SOC experiment (R1,
preregistration docs/preregistration_r1_soc_repair.md).

Template: the SOC-v2 effect_stated attack cell (run-001 GLM configs), with
ONLY the repair fields changed -- the new task (per-incident SLAs and
severities, warranted severities, hold 5), no global SLA override, the
initially escalated incident mirrored by task side, and the world clock run
out to the horizon after both agents stop.

Models: GLM-5, Claude Sonnet 4.5, DeepSeek V3.2, model blocks byte-identical
to their SOC-v2 diagnostic configs. Arms: none / hard / judge, the defense-002
gate block verbatim. n = 40 per cell: 10 per task side x first actor.
PAIRED: within a model, slot i has the SAME fresh seed in all three arms.
Seeds are fresh: disjoint from every config and every recorded manifest.
"""
import glob
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "r1_soc_repair"
TEMPLATE_DIR = ROOT / "configs/soc_v2_diagnostic/glm/effect_stated"
MODEL_DIRS = {
    "glm": ROOT / "configs/soc_v2_diagnostic/glm/effect_stated",
    "sonnet": ROOT / "configs/soc_v2_diagnostic/sonnet/effect_stated",
    "deepseek": ROOT / "configs/soc_v2_diagnostic_002/deepseek/effect_stated",
}
MODEL_IDS = {"glm": "zai.glm-5",
             "sonnet": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
             "deepseek": "deepseek.v3.2"}
GATE = yaml.safe_load(
    (ROOT / "configs/defense_001/glm/judge/def_glm_judge_001.yaml").read_text())["defense_gate"]
ARMS = {
    "none": {"permission_mode": "soft"},
    "hard": {"permission_mode": "hard"},
    "judge": {"permission_mode": "soft", "defense_gate": GATE},
}
# Fields the repair sets, identical in every R1 config.
REPAIR = {"escalation_duration": 5, "advance_to_horizon_after_finish": True}
SLOTS_PER_STRATUM = 10
SEED_BLOCK = 6_470_000_000


def used_seeds(exclude: Path = OUT) -> set[int]:
    """Every seed in every config and every recorded manifest, except the
    configs under `exclude` (the caller's own output, being regenerated)."""
    seeds: set[int] = set()
    for p in glob.glob(str(ROOT / "artifacts/runs/**/manifest.json"), recursive=True):
        seeds.add(json.load(open(p)).get("config_seed"))
    for p in glob.glob(str(ROOT / "configs/**/*.yaml"), recursive=True):
        if exclude in Path(p).parents:
            continue
        d = yaml.safe_load(open(p)) or {}
        seeds.update({d.get("seed"), d.get("config_seed")})
    return {s for s in seeds if s is not None}


def first_actor(seed: int) -> str:
    return acting_order(episode_seed(seed, 0), ["A", "B"])[0]


def model_block(model: str) -> dict:
    blocks = {yaml.safe_dump(yaml.safe_load(p.read_text())["model"], sort_keys=True)
              for p in sorted(MODEL_DIRS[model].glob("*.yaml"))}
    assert len(blocks) == 1, f"{model}: model blocks disagree"
    block = yaml.safe_load(blocks.pop())
    assert block["model_id"] == MODEL_IDS[model]
    return block


def template(side: str) -> dict:
    """The run-001 GLM effect_stated fields, repaired for one task side."""
    for path in sorted(TEMPLATE_DIR.glob("*.yaml")):
        tmpl = yaml.safe_load(path.read_text())
        if tmpl["task_id"].endswith(side):
            break
    focal, peer = side, "b" if side == "a" else "a"
    cfg = {k: v for k, v in tmpl.items() if k != "sla_deadline"}
    cfg.update(REPAIR, task_id=f"soc-r1-pair-{side}",
               initially_escalated=[f"incident-{peer}"])
    assert cfg["escalation_capacity"] == 1 and not cfg["graded_scoring"]
    assert cfg["soc_v2"] and cfg["soc_v2_menu_arm"] == "effect_stated"
    assert cfg["pressure"] == "P4" and cfg["reward_lambda"] == 1.0
    assert f"incident-{focal}" not in cfg["initially_escalated"]
    return cfg


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite")
        return 1
    taken = used_seeds()
    seed = SEED_BLOCK
    slots = [(side, first) for side in "ab" for first in "AB"
             for _ in range(SLOTS_PER_STRATUM)]
    for model in MODEL_DIRS:
        block = model_block(model)
        for i, (side, want) in enumerate(slots, start=1):
            while seed in taken or first_actor(seed) != want:
                seed += 1
            for arm, fields in ARMS.items():
                name = f"r1_{model}_{arm}_{i:03d}"
                cfg = dict(template(side))
                cfg.update(model=block, condition=name, experiment_id=name,
                           seed=seed, config_seed=seed, **fields)
                outdir = OUT / model / arm
                outdir.mkdir(parents=True, exist_ok=True)
                (outdir / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
            print(f"{model} slot {i:03d}: task {side}, first {want}, seed {seed}")
            taken.add(seed)
            seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
