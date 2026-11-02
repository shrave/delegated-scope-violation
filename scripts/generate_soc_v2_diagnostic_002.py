#!/usr/bin/env python3
"""Generate the configs for soc-v2-affordance-diagnostic-002: the EXPLORATORY
SOC-v2 affordance-legibility diagnostic extended to the four remaining models
(DeepSeek V3.2, Mistral Large 3, Qwen3-Coder, GPT-6 Astra). Not pooled with
any other corpus.

The design is frozen at run 001 (scripts/generate_soc_v2_diagnostic.py). Each
config here is the run-001 GLM config for the same arm and slot with ONLY the
model block, the name and the seed replaced; every other field is asserted
equal. Model blocks are copied verbatim from the CI/CD experiment1_completion_003
P4 configs, whose model ids match the final-paper CI/CD manifests.

Configs are written OUTSIDE the tracked tree (argv[1]) as well as to
configs/soc_v2_diagnostic_002, because the run executes in a worktree checked
out at 930bf2d (run 001's commit), where these files do not exist as tracked
files. Seeds are fresh: never used by any config or recorded episode.

Usage: generate_soc_v2_diagnostic_002.py [EXTRA_OUT_DIR]
"""
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from competition_lab.environments.soc_itsm import MENU_ARMS  # noqa: E402
from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402
from generate_exp1_completion_003 import used_seeds  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "soc_v2_diagnostic_002"
BASE = ROOT / "configs" / "soc_v2_diagnostic" / "glm"
CICD = ROOT / "configs" / "experiment1_completion_003"
MODELS = {
    "deepseek": CICD / "deepseek-v3.2" / "p4_full",
    "mistral": CICD / "mistral-large-3" / "p4_full",
    "qwen": CICD / "qwen3-coder-480b" / "p4_full",
    "gpt": CICD / "gpt-6-astra" / "p4_full",
}
MODEL_IDS = {
    "deepseek": "deepseek.v3.2",
    "mistral": "mistral.mistral-large-3-675b-instruct",
    "qwen": "qwen.qwen3-coder-480b-a35b-v1:0",
    "gpt": "us.openai.gpt-6-astra",
}
VARIES = {"model", "condition", "experiment_id", "seed", "config_seed"}


def model_block(model: str) -> dict:
    blocks = {
        yaml.safe_dump(yaml.safe_load(p.read_text())["model"], sort_keys=True)
        for p in sorted(MODELS[model].glob("*.yaml"))
    }
    assert len(blocks) == 1, f"{model}: CI/CD model blocks disagree"
    block = yaml.safe_load(blocks.pop())
    assert block["model_id"] == MODEL_IDS[model], block["model_id"]
    return block


def main(argv: list[str]) -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite"); return 1
    extra = Path(argv[1]) if len(argv) > 1 else None
    taken = used_seeds()
    seed = 6_420_000_000
    for model in MODELS:
        block = model_block(model)
        for arm in MENU_ARMS:
            outdir = OUT / model / arm
            outdir.mkdir(parents=True, exist_ok=True)
            for base in sorted((BASE / arm).glob("*.yaml")):
                tmpl = yaml.safe_load(base.read_text())
                want = acting_order(episode_seed(tmpl["seed"], 0), ["A", "B"])[0]
                while seed in taken or acting_order(episode_seed(seed, 0), ["A", "B"])[0] != want:
                    seed += 1
                name = base.stem.replace("_glm_", f"_{model}_")
                cfg = dict(tmpl)
                cfg.update(model=block, condition=name, experiment_id=name,
                           seed=seed, config_seed=seed)
                assert {k: v for k, v in cfg.items() if k not in VARIES} == \
                    {k: v for k, v in tmpl.items() if k not in VARIES}
                path = outdir / f"{name}.yaml"
                path.write_text(yaml.safe_dump(cfg, sort_keys=True))
                if extra is not None:
                    dest = extra / model / arm / path.name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, dest)
                print(f"{model}/{arm}/{name}: {cfg['task_id'][-1]}, first {want}, seed {seed}")
                taken.add(seed); seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
