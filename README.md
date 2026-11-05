# Permitted but Unauthorized: Affordance-Induced Delegated-Scope Violations in Multi-Agent LLM Systems

**Shravya Kanchi** (Independent Researcher)

[![arXiv](https://img.shields.io/badge/arXiv-2611.04086-b31b1b.svg)](https://arxiv.org/abs/2611.04086)

📄 **Paper:** [arXiv:2611.04086](https://arxiv.org/abs/2611.04086) · [PDF in this repository](paper/permitted-but-unauthorized.pdf)

🔁 **Reproduce every reported number offline:** `python reproduce/reproduce_all.py` ([details](#reproduction-has-two-tiers))

## Abstract

Multi-agent LLM systems increasingly place several autonomous agents on shared
infrastructure, where each agent is granted permissions far broader than the task
it is delegated, so every agent is routinely *permitted* to act on a peer's
resources it was never assigned. We address the following research question:
under competitive pressure, what determines whether an agent crosses from its own
delegated scope into a peer's resources, and can such crossings be enforced away?

We study this across eight contemporary LLMs in two simulated environments: a
CI/CD release pipeline and a security-operations incident queue. Crossings are
counted by a deterministic, no-model-in-the-loop detector computed from
hash-chained, replay-verified logs.

In a controlled 2×2×2 factorial over competitive incentive, candidate visibility
and payoff information (three models, n = 52 per cell), we find that action
*representation*, not permission, governs the behavior:

- No agent crosses in any condition where the peer action is unlisted.
- Listing it together with competitive pressure and a stated payoff raises
  crossings sharply, up to 52 of 52 episodes for Claude Sonnet 4.5.

We further observe a model-dependent split. Two newer models (Claude Sonnet 5.5
and Opus 5.5) refuse the identical attack in 0 of 100 episodes, at a projected
cost, where prior-generation models cross in 9 of 10.

We then evaluate two defenses: a deterministic reference monitor and a
model-based pre-execution judge. Both block every crossing and, when the task is
winnable, cut avoidable peer deadline misses from 15/40 and 14/40 to at most 1/40.

However, scope enforcement is not harm prevention. An agent can still set a peer
back through an *authorized* action on its own resources, misreporting its
incident's severity, which neither defense detects.

Within the tested environments and configurations, our results establish action
*representation*, not permission alone, as a controllable driver of inter-agent
scope violations. They also show that enforcing delegated scope is distinct from
preventing harm, motivating *effect-aware* authorization that reasons about an
action's consequences rather than only the resource it names.

## Citation

If you use this code or data, please cite:

```bibtex
@misc{kanchi2026permitted,
  title         = {Permitted but Unauthorized: Affordance-Induced Delegated-Scope Violations in Multi-Agent {LLM} Systems},
  author        = {Kanchi, Shravya},
  year          = {2026},
  eprint        = {2611.04086},
  archivePrefix = {arXiv},
  primaryClass  = {cs.CR},
  doi           = {10.48550/arXiv.2611.04086},
  url           = {https://arxiv.org/abs/2611.04086}
}
```

GitHub's "Cite this repository" button gives the same reference (from `CITATION.cff`).

## This repository

Code, environments, delegation records, configurations and the complete
hash-chained event logs for the paper: a controlled study of when tool-using LLM
agents act on resources the platform **permits** them to touch but that were
never **delegated** to them, and of what runtime enforcement does and does not
prevent.

Two simulated multi-agent environments are included:

- **CI/CD release** (`cicd_release`). Two agents ship releases through a shared runner pool.
- **SOC/ITSM incident response** (`soc_itsm`). Two analysts contend for a shared escalation channel.

The **deterministic detector** marks a *delegated-scope violation* when three
things hold:

- the action was technically **permitted**;
- the target resource was **outside the caller's delegation**;
- the action **changed state**.

No LLM judges or scores anything. The judge *gate* in the defense experiments is
the intervention under test, not a scorer.

## Reproduction has two tiers

### Tier 1: analysis (offline: no model access, no GPU, no credentials)

Every reported result reproduces from the committed event logs:

- the detector's counts;
- every table and figure;
- the statistics (Wilson 95% intervals, two-sided Fisher exact tests, Holm-corrected);
- **exact replay verification of every episode**.

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e .
python reproduce/reproduce_all.py          # about 4 minutes on a laptop; --skip-replay to skip step 1
```

`reproduce_all.py` works in five steps:

1. **Replay.** It re-executes every shipped episode against a fresh environment
   built from its config. Recorded before/after state digests, classifications
   and targets must match exactly, and the divergence count is printed per run.
2. **Recompute.** It recomputes the numbers behind every table and figure with
   the scripts in `scripts/`.
3. **Statistics.** It computes the statistics.
4. **Figures.** It redraws `factorial.pdf`, `generational.pdf` and `r1_harm.pdf`
   from the recomputed counts.
5. **Check.** It compares every recomputed value with the value printed in the
   paper (`reproduce/paper_values.json`). Every check is printed as `ok` or
   `DIFF`, and the exit status is 1 on any difference.

Outputs go to `reproduce/out/`: `results.json` and the figures.

### Tier 2: episode regeneration (needs model access; documented cost)

Regenerating episodes requires model access.

- **Where the models were reached.** Every model in the study was reached
  through **AWS Bedrock (us-west-2)**. Model ids, regions, temperatures and
  token limits are pinned in each config and recorded in each manifest.
- **Closed models.** Claude and GPT-6 cannot be run any other way.
- **Open-weight models.** GLM-5, DeepSeek V3.2, Mistral Large 3 and Qwen3-Coder
  are frontier-scale mixture-of-experts models. Self-hosting them needs
  server-class multi-GPU hardware; we did not regenerate them locally.

```bash
export AWS_PROFILE=<your-profile>
python scripts/run_lanes.py r1-regen r1_soc_repair/glm/none     # one cell; run several --part K N in parallel
```

- Regenerated episodes are written to `artifacts/regenerated/` (gitignored), so
  the tracked tree stays clean. Every manifest records the commit and whether
  the tree was dirty, and live runs refuse a dirty tree.
- At temperature 0 a model is near-deterministic within a seed, but not
  bit-identical across provider versions. Regeneration reproduces the protocol,
  not necessarily the exact trajectories; the shipped logs are the record.
- Logged inference cost of the shipped runs: R2 $319, R1 $242, defense-002
  about $111 + $1.60 gate. The per-episode `request_cost_usd` is in every
  `model_call` event.

**Without credentials.** A **mock provider** runs the full pipeline with no
credentials and no GPU, exercising the environments, the detector, logging and
replay on scripted episodes. It verifies the machinery, not the behavioural
results:

```bash
competition-lab run configs/r1_soc_repair/glm/none/r1_glm_none_001.yaml --output /tmp/mock
competition-lab replay /tmp/mock/r1_glm_none_001-0000
```

## What is here

| path | contents |
|---|---|
| `src/competition_lab/` | environments (`environments/cicd_release.py`, `environments/soc_itsm.py`), detector and classification, orchestration, hash-chained event log, replay, defenses (`defense.py`: hard enforcement and the judge gate), providers (Bedrock Converse, mock) |
| `tasks/` | task definitions, including each task's versioned **delegation record** |
| `configs/` | one YAML per episode: the exact model block, seed, environment and arm |
| `artifacts/runs/` | **the event logs**: per episode a `manifest.json` (config, commit, prompts and their hashes, model ids, seeds) and an `events.jsonl` (hash-chained model calls, tool requests and results with state digests, round transitions) |
| `scripts/` | analysis (`revision_measures.py`, `defense_00{1,2}_measures.py`, `soc_v2_episode_rescore.py`, `recent_claude_*.py`), audits (`r2_prompt_audit.py`, `r1_soc_feasibility.py`), the Tier 2 runner and the config generators |
| `reproduce/` | the Tier 1 entry point and the paper's printed values |
| `paper/` | the paper (PDF) |
| `docs/` | preregistrations (committed before each run), results documents, the R1 feasibility check, the R2 prompt audit, the truncated-episode declarations |
| `tests/` | tests for the environment changes, defenses, configs and measures (`pip install -e ".[dev]" && pytest`) |

## Which run supports which result

| result in the paper | run (`artifacts/runs/`) | configs | analysis |
|---|---|---|---|
| Affordance factorial (2×2×2, n=52/cell) and its contrasts | `r2-affordance-factorial-001` | `configs/r2_affordance_factorial/` | `scripts/revision_measures.py r2` |
| Repaired-SOC defense (n=40/cell), misreporting residual | `r1-soc-repair-001` | `configs/r1_soc_repair/` | `scripts/revision_measures.py r1` |
| Pre-repair SOC diagnostic (absent / listed / listed+effect, n=10) and "crossing agent was blocked" | `soc-v2-affordance-diagnostic-001`, `-002` | `configs/soc_v2_diagnostic{,_002}/` | `scripts/soc_v2_episode_rescore.py`, `reproduce/reproduce_all.py` |
| Model-specific refusal (Claude Sonnet 5.5 / Opus 5.5, 0/100) and decline grounds | `recent-claude-matched-001` | `configs/recent_claude_matched/` | `scripts/recent_claude_declines.py`, `scripts/recent_claude_refusal_audit.py` |
| Mechanism: CI/CD crossings citing the reward formula or relative standing | `r2-affordance-factorial-001`, `defense-001`, `defense-002` | as above | `scripts/cicd_formula_citation.py` |
| CI/CD: a legal route to completion exists (earliest round under optimal play) | none: exhaustive search over the environment | `configs/r2_affordance_factorial/` (task template) | `scripts/cicd_legal_route.py` |
| CI/CD full-grid defense (every model, hard and judge) | `defense-001`, `defense-002` | `configs/defense_00{1,2}/` | `scripts/defense_002_measures.py` |

The preregistration and results document for each run are in `docs/`.

**Not pooled.** Each run is reported on its own and never pooled with another.

## Provenance and run hygiene

- **Commits and seeds.** Every episode records the exact commit it ran at, with
  a clean tree. Seeds are fresh per experiment and paired across arms or cells,
  so every arm of a slot starts from the identical state.
- **Retries.** Only crash-level failures were retried, meaning there was no
  final event. Every retry is listed in the results documents.
- **Truncated episodes.** These are kept as `*-INCOMPLETE-QUARANTINE`
  directories and declared in `docs/counted_truncated_episodes.json` under the
  asymmetric-censoring rule:
  - a truncated episode that already contained a crossing is a **counted
    positive**;
  - one without a crossing was replaced on the same seed.
- **Two defects, disclosed in the paper and the results documents:**
  1. **Deleted partial attempts.** In R1/R2 (50 slots) and defense-002 (30
     retries), the original lane runner deleted a crashed attempt's partial log
     before retrying. Whether any deleted attempt had crossed cannot be
     recovered. The runner shipped here never deletes.
  2. **The independent-reward prompt.** The earlier independent-reward prompt
     still told agents their reward depended on both agents' scores. The R2
     factorial corrects this.
- **Config generators.** The generators in `scripts/generate_*.py` document how
  each config set was built. The shipped configs are canonical. Re-running a
  generator here would not reproduce the seeds, because the seed-collision scan
  sees only the runs shipped in this repository.

## License and citation

- **Code** (`src/`, `scripts/`, `reproduce/`, `tests/`): MIT. See `LICENSE`.
- **Data** (event logs, configs, task and delegation records, docs): CC BY 4.0.
  See `LICENSE-DATA`. The logs contain model-generated text, which may also be
  subject to the model providers' terms.
- **Paper:** [arXiv:2611.04086](https://arxiv.org/abs/2611.04086), CC BY 4.0. The PDF in `paper/` is a copy of the submitted version; arXiv holds the version of record.
- **Citation:** see [Citation](#citation) above, `CITATION.cff`, or GitHub's "Cite this repository" button.
