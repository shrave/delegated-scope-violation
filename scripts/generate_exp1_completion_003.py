#!/usr/bin/env python3
"""Generate configs/experiment1_completion_003 (replaces defective 002).

Each config copies an existing cell template and replaces exactly five keys:
model (verified block), condition/experiment_id (== filename stem), task_id
(focal a/b), and `seed` -- the key the runner actually reads -- chosen fresh
(unused in any manifest or config) and so that the derived acting order is
balanced: 5/5 focal-first/peer-first within each focal side for 20-episode
cells; for top-ups, chosen to bring the cell to 10a/10b and 10 focal-first /
10 peer-first given the already-run originals. `config_seed` is set equal to
`seed` so the two keys can never disagree again.
"""
import glob
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from competition_lab.orchestration import acting_order, episode_seed  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "configs" / "experiment1_completion_003"
SRC = ROOT / "configs" / "experiment1_completion"
MODEL_BLOCKS = {
    "glm": {"concurrency": 1, "input_cost_per_million": 0.6, "max_retries": 2, "max_tokens": 2048, "model_id": "zai.glm-5", "output_cost_per_million": 2.2, "provider": "bedrock-converse", "region": "us-west-2", "temperature": 0.0, "timeout_seconds": 60},
    "deepseek-v3.2": {"concurrency": 1, "input_cost_per_million": 0.28, "max_retries": 2, "max_tokens": 2048, "model_id": "deepseek.v3.2", "output_cost_per_million": 0.42, "provider": "bedrock-converse", "region": "us-west-2", "temperature": 0.0, "timeout_seconds": 60},
    "mistral-large-3": {"concurrency": 1, "input_cost_per_million": 2.0, "max_retries": 2, "max_tokens": 2048, "model_id": "mistral.mistral-large-3-675b-instruct", "output_cost_per_million": 6.0, "provider": "bedrock-converse", "region": "us-west-2", "temperature": 0.0, "timeout_seconds": 60},
    "qwen3-coder-480b": {"concurrency": 1, "input_cost_per_million": 0.22, "max_retries": 2, "max_tokens": 2048, "model_id": "qwen.qwen3-coder-480b-a35b-v1:0", "output_cost_per_million": 0.88, "provider": "bedrock-converse", "region": "us-west-2", "temperature": 0.0, "timeout_seconds": 60},
    "gpt-6-astra": {"concurrency": 1, "input_cost_per_million": 1.25, "max_retries": 2, "max_tokens": 2048, "model_id": "us.openai.gpt-6-astra", "output_cost_per_million": 10.0, "provider": "bedrock-converse", "region": "us-west-2", "supports_temperature": False, "temperature": 0.0, "timeout_seconds": 180},
}
SHORT = {"glm": "glm", "deepseek-v3.2": "deepseek", "mistral-large-3": "mistral", "qwen3-coder-480b": "qwen", "gpt-6-astra": "gpt"}
TASK = {"a": "cicd-release-pair-001-v2-behind-a", "b": "cicd-release-pair-001-v2-behind-b"}

# (model, cell) -> (first config number, list of (focal, order) slots); order ff = focal acts first
FULL20 = [("a", "ff")] * 5 + [("a", "pf")] * 5 + [("b", "ff")] * 5 + [("b", "pf")] * 5
PLAN = {}
for m in ["deepseek-v3.2", "mistral-large-3", "qwen3-coder-480b"]:
    for cell in ["p0_full", "p0_padded", "p0_own", "p0_null", "p4_padded", "p4_null"]:
        PLAN[(m, cell)] = (1, FULL20)
# Top-ups: slots chosen from the originals' (focal, order) strata so the cell
# ends at 10a/10b and 10ff/10pf. Originals measured from manifests 2026-09-29.
TOPUP = {
    ("deepseek-v3.2", "p4_full"): (16, [("a", "pf")] * 3 + [("b", "ff"), ("b", "pf")]),          # orig a 5ff/2pf, b 4ff/4pf
    ("deepseek-v3.2", "p4_own"):  (11, [("a", "ff")] * 3 + [("a", "pf")] * 2 + [("b", "ff")] * 3 + [("b", "pf")] * 2),  # orig 2/3,2/3
    ("glm", "p4_full"):           (16, [("a", "ff")] * 3 + [("b", "ff")] * 2),                    # orig a 3ff/4pf, b 2ff/6pf -> 6/4,4/6
    ("glm", "p4_own"):            (11, [("a", "ff")] * 2 + [("a", "pf")] * 3 + [("b", "ff")] * 2 + [("b", "pf")] * 3),  # orig 3/2,3/2
    ("gpt-6-astra", "p4_full"):   (16, [("a", "ff")] * 3 + [("b", "ff")] * 2),                    # orig a 3ff/4pf, b 2ff/6pf -> 6/4,4/6
    ("gpt-6-astra", "p4_own"):    (11, [("a", "ff")] * 2 + [("a", "pf")] * 3 + [("b", "ff")] * 2 + [("b", "pf")] * 3),  # orig 3/2,3/2
    ("mistral-large-3", "p4_full"): (16, [("a", "ff")] * 2 + [("a", "pf")] + [("b", "ff")] * 2),  # orig a 3ff/4pf, b 3ff/5pf
    ("qwen3-coder-480b", "p4_full"): (16, [("a", "pf")] * 3 + [("b", "ff")] * 2),                 # orig a 5ff/2pf, b 3ff/5pf
    ("qwen3-coder-480b", "p4_own"):  (11, [("a", "ff")] + [("a", "pf")] * 4 + [("b", "ff")] * 3 + [("b", "pf")] * 2),  # orig a 4ff/1pf, b 2ff/3pf
}
PLAN.update(TOPUP)


def template_for(cell: str) -> dict:
    src_model = "glm" if cell.startswith("p0_") else "deepseek-v3.2"
    return yaml.safe_load(sorted((SRC / src_model / cell).glob("*.yaml"))[0].read_text())


def used_seeds() -> set:
    seeds = set()
    for p in glob.glob(str(ROOT / "artifacts/runs/**/manifest.json"), recursive=True):
        seeds.add(json.load(open(p)).get("config_seed"))
    for p in glob.glob(str(ROOT / "configs/**/*.yaml"), recursive=True):
        if OUT in Path(p).parents:
            continue
        try:
            d = yaml.safe_load(open(p)); seeds.add(d.get("seed")); seeds.add(d.get("config_seed"))
        except Exception:
            pass
    return seeds


def main() -> int:
    if OUT.exists() and any(OUT.rglob("*.yaml")):
        print(f"{OUT} already has configs; refusing to overwrite"); return 1
    taken = used_seeds()
    print(f"seeds already used anywhere (manifest config_seed, config seed/config_seed): {len(taken)}")
    seed = 3_000_000_000
    written = 0
    for (model, cell), (start, slots) in sorted(PLAN.items()):
        tmpl = template_for(cell)
        outdir = OUT / model / cell; outdir.mkdir(parents=True, exist_ok=True)
        for i, (focal, order) in enumerate(slots):
            want_first = focal.upper() if order == "ff" else ("B" if focal == "a" else "A")
            while seed in taken or acting_order(episode_seed(seed, 0), ["A", "B"])[0] != want_first:
                seed += 1
            cfg = dict(tmpl)
            name = f"e2b_{SHORT[model]}_{cell}_{start + i:03d}"
            cfg["model"] = dict(MODEL_BLOCKS[model]); cfg["condition"] = name; cfg["experiment_id"] = name
            cfg["task_id"] = TASK[focal]; cfg["seed"] = seed; cfg["config_seed"] = seed
            (outdir / f"{name}.yaml").write_text(yaml.safe_dump(cfg, sort_keys=True))
            taken.add(seed); seed += 1; written += 1
        c = {k: sum(1 for s in slots if s == k) for k in [("a","ff"),("a","pf"),("b","ff"),("b","pf")]}
        print(f"  {model:17s} {cell:10s} +{len(slots):2d}  a_ff={c[('a','ff')]} a_pf={c[('a','pf')]} b_ff={c[('b','ff')]} b_pf={c[('b','pf')]}  #{start:03d}-{start+len(slots)-1:03d}")
    print(f"wrote {written} configs to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
