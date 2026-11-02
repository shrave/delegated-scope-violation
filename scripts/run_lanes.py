#!/usr/bin/env python3
"""Tier 2: regenerate episodes from the shipped configs on AWS Bedrock.

Runs every config under configs/CONFIG_SUBDIR (optionally one slice of them)
through `competition-lab run --live`, writing each episode to
artifacts/regenerated/RUN_NAME/<same relative path>/<config stem>-0000.

  * Skips episodes that are already complete (exactly one final event, no
    duplicate event ids), so an interrupted lane can simply be restarted.
  * NEVER deletes. A failed attempt (no final event) is renamed
    `<episode>-retryN-INCOMPLETE-QUARANTINE` before the next attempt, so the
    asymmetric-censoring rule can still inspect it: a truncated episode that
    already crossed is a counted positive, not something to replace
    (docs/counted_truncated_episodes.json).
  * Retries only crash-level failures (no final event), at most 3 attempts.
    An episode is never rerun because of what the model did.

Credentials come from the standard AWS environment (e.g. AWS_PROFILE); model
ids and regions are pinned in each config. Run lanes in parallel by starting
several processes with different --part K N.

Usage:
  python scripts/run_lanes.py RUN_NAME CONFIG_SUBDIR [--part K N] [--max-usd 25] [--max-requests 170]
Example:
  python scripts/run_lanes.py r1-soc-repair-regen r1_soc_repair/glm/none
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def is_complete(episode: Path) -> bool:
    if not (episode / "manifest.json").exists() or not (episode / "events.jsonl").exists():
        return False
    events = [json.loads(line) for line in (episode / "events.jsonl").open() if line.strip()]
    ids = collections.Counter(e["event_id"] for e in events)
    return sum(e["kind"] == "final" for e in events) == 1 and all(v == 1 for v in ids.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name")
    ap.add_argument("config_subdir")
    ap.add_argument("--part", nargs=2, type=int, default=(0, 1), metavar=("K", "N"))
    ap.add_argument("--max-usd", default="25.00")
    ap.add_argument("--max-requests", default="170")
    args = ap.parse_args()
    k, n = args.part
    cfg_root = ROOT / "configs"
    configs = [c for i, c in enumerate(sorted((cfg_root / args.config_subdir).rglob("*.yaml"))) if i % n == k]
    # Written OUTSIDE the tracked artifacts/runs/ (gitignored), so new episodes
    # never dirty the working tree that every manifest records.
    run_root = ROOT / "artifacts" / "regenerated" / args.run_name
    for cfg in configs:
        episode = run_root / cfg.parent.relative_to(cfg_root) / f"{cfg.stem}-0000"
        episode.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(3):
            if is_complete(episode):
                break
            if episode.exists():
                episode.rename(episode.with_name(f"{episode.name}-retry{attempt}-INCOMPLETE-QUARANTINE"))
            proc = subprocess.run(
                [sys.executable, "-m", "competition_lab", "run", str(cfg.relative_to(ROOT)),
                 "--output", str(episode.parent), "--live", "--no-dry-run", "--yes",
                 "--max-usd", args.max_usd, "--max-requests", args.max_requests],
                cwd=ROOT, capture_output=True, text=True)
            if not is_complete(episode):
                sys.stderr.write(f"attempt {attempt} failed for {cfg.stem}:\n{proc.stderr[-2000:]}\n")
        print(f"{'OK  ' if is_complete(episode) else 'FAIL'} {episode.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
