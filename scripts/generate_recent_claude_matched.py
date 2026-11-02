#!/usr/bin/env python3
"""Generate configs for recent-claude-matched-001: Claude Sonnet 5.5 and Opus
5.5 on the matched set, with the reasoning request ON. EXPLORATORY added
models, not pooled with any corpus.

Per model (50 episodes):
  soc_v2/<arm>   SOC-v2 affordance diagnostic, arms absent / enumerated /
                 effect_stated, n=10 each; template = run 001's GLM config for
                 the same arm and slot (as run 002 did)
  cicd_p4        Experiment 1 CI/CD P4 full, n=20; template = the Opus 5.5
                 Exp 1 P4 config for the same slot (5 per focal side x acting
                 order)
Only model block, name and seed differ from the template (asserted). Each new
seed is fresh and gives the same first actor as its template slot, so focal
side x acting order balance is preserved.

REASONING REQUEST. The model block adds additional_request_fields =
{"thinking": {"type": "adaptive", "display": "summarized"}}, which makes
Bedrock RETURN the reasoning these models already do (without it the block is
redacted). The prompt is unchanged. No GPT/Qwen/Claude 4.5 run had this
setting, so behavioural counts are comparable across models while the
reasoning text is a richer channel available only for these two.
Both models reject temperature (supports_temperature false), so they run at
the provider's default sampling, unlike the temperature-0 models.
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from generate_exp1_completion_003 import used_seeds  # noqa: E402

from competition_lab.environments.soc_itsm import MENU_ARMS  # noqa: E402
from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "recent_claude_matched"
REASONING = {"thinking": {"type": "adaptive", "display": "summarized"}}
SMOKE = ROOT / "configs" / "recent_claude_smoke"
MODELS = {
    m: {
        **yaml.safe_load(next((SMOKE / m / "cicd_p4").glob("*.yaml")).read_text())[
            "model"
        ],
        "additional_request_fields": REASONING,
    }
    for m in ("sonnet55", "opus55")
}
DESIGNS = {
    **{
        f"soc_v2/{arm}": sorted(
            (ROOT / "configs/soc_v2_diagnostic/glm" / arm).glob("*.yaml")
        )
        for arm in MENU_ARMS
    },
    "cicd_p4": sorted((ROOT / "configs/exp1_opus55/opus-5.5/p4_full").glob("*.yaml")),
}
VARIES = {"model", "condition", "experiment_id", "seed", "config_seed"}


def first_actor(seed: int) -> str:
    return acting_order(episode_seed(seed, 0), ["A", "B"])[0]


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite")
        return 1
    assert [len(v) for v in DESIGNS.values()] == [10, 10, 10, 20]
    taken = used_seeds()
    seed = 6_440_000_000
    for model, block in MODELS.items():
        for design, templates in DESIGNS.items():
            outdir = OUT / model / design
            outdir.mkdir(parents=True, exist_ok=True)
            for i, path in enumerate(templates, start=1):
                tmpl = yaml.safe_load(path.read_text())
                want = first_actor(tmpl["seed"])
                while seed in taken or first_actor(seed) != want:
                    seed += 1
                name = f"rc_{model}_{design.replace('/', '_')}_{i:03d}"
                cfg = dict(tmpl)
                cfg.update(model=block, condition=name, experiment_id=name,
                           seed=seed, config_seed=seed)
                assert {k: v for k, v in cfg.items() if k not in VARIES} == \
                    {k: v for k, v in tmpl.items() if k not in VARIES}
                text = yaml.safe_dump(cfg, sort_keys=True)
                (outdir / f"{name}.yaml").write_text(text)
                print(f"{model}/{design}/{name}: {cfg['task_id'][-1]}, first {want}, "
                      f"seed {seed}")
                taken.add(seed)
                seed += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
