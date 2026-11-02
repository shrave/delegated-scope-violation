from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Annotated, Any, cast

import pandas as pd
import typer

from competition_lab.analysis import export_outputs
from competition_lab.arms import arm_of
from competition_lab.config import ExperimentConfig, load_config
from competition_lab.cost import CostLedger
from competition_lab.detector import detect_events
from competition_lab.environments import (
    CICDReleaseEnvironment,
    ComputeEnvironment,
    ReleaseIntegrityEnvironment,
    RepositoryEnvironment,
    SOCITSMEnvironment,
)
from competition_lab.environments.base import Environment
from competition_lab.orchestration import EpisodeRunner, episode_seed
from competition_lab.prelive import run_pre_live_integrity_self_test
from competition_lab.providers import (
    BedrockConverseProvider,
    BedrockResponsesProvider,
    MockProvider,
    ModelProvider,
)
from competition_lab.quarantine import is_quarantined
from competition_lab.schemas import ToolCall
from competition_lab.tasks import compute_ownership, load_task, repository_ownership

app = typer.Typer(no_args_is_help=True)
models_app = typer.Typer()
tasks_app = typer.Typer()
judge_app = typer.Typer()
app.add_typer(models_app, name="models")
app.add_typer(tasks_app, name="tasks")
app.add_typer(judge_app, name="judge")


SUPPORTED_PYTHON = (3, 12)


def _docker_daemon_available() -> bool:
    """Whether a container runtime actually answers, not merely a CLI on PATH."""
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def _requires_container(config: ExperimentConfig) -> bool:
    """Whether this config needs a container runtime to execute actions.

    Always False today: every environment executes in process. Kept as an
    explicit predicate so a future containerized task flips one place rather
    than resurrecting "docker is required because the run is live", which is
    not the same question.
    """
    return False


def _doctor_report(config: ExperimentConfig | None = None) -> dict[str, object]:
    version = tuple(map(int, platform.python_version_tuple()[:2]))
    # No environment shells out to a container: RepositoryEnvironment and
    # ComputeEnvironment are pure in-process simulations, and the manifest's
    # container_image is always None. Docker is therefore not required by any
    # current config. Gate on containerized execution if that ever changes,
    # not on the provider being live.
    docker_required = bool(config and _requires_container(config))
    cli_found = shutil.which("docker") is not None
    daemon = _docker_daemon_available()
    report: dict[str, object] = {
        "python_version": platform.python_version(),
        # Pinned rather than ">=": a newer interpreter still changes results.
        "python_matches_supported_version": version == SUPPORTED_PYTHON,
        "docker_cli_found": cli_found,
        "docker_daemon_available": daemon,
        "docker_required_for_current_config": docker_required,
        # A CLI with no daemon behind it used to read as "docker available",
        # so this stays honest instead of passing on the binary alone.
        "docker_ok": daemon if docker_required else True,
        "git_repository": Path(".git").exists(),
    }
    if config and config.model.provider.startswith("bedrock"):
        report["aws_credentials_configured"] = bool(
            os.getenv("AWS_PROFILE")
            or os.getenv("AWS_ACCESS_KEY_ID")
            or Path.home().joinpath(".aws", "credentials").exists()
        )
    return report


def _doctor_blocking(report: dict[str, object]) -> list[str]:
    """Checks that must hold. Informational fields are excluded by name."""
    informational = {
        "python_version",
        "docker_cli_found",
        "docker_daemon_available",
        "docker_required_for_current_config",
    }
    return [k for k, v in report.items() if k not in informational and not v]


@app.command()
def doctor(config: Path | None = None) -> None:
    """Check local prerequisites without making a model call."""
    report = _doctor_report(load_config(config) if config else None)
    typer.echo(json.dumps(report, indent=2))
    if not report["python_matches_supported_version"]:
        typer.echo(
            f"WARNING: running Python {report['python_version']}; this protocol is "
            f"pinned to {SUPPORTED_PYTHON[0]}.{SUPPORTED_PYTHON[1]}.x. Results may "
            "not be reproducible.",
            err=True,
        )
    if report["docker_cli_found"] and not report["docker_daemon_available"]:
        typer.echo(
            "WARNING: the docker CLI is installed but no container runtime "
            "responds; container-backed tasks will fail.",
            err=True,
        )
    failed = _doctor_blocking(report)
    if failed:
        typer.echo(f"FAILED: {', '.join(failed)}", err=True)
        raise typer.Exit(1)


@models_app.command("list")
def models_list(config: Path) -> None:
    """List configured/available models in an AWS region."""
    cfg = load_config(config)
    if cfg.model.provider == "mock":
        typer.echo(cfg.model.model_id)
        return
    import boto3

    session = boto3.Session(
        profile_name=cfg.model.profile, region_name=cfg.model.region
    )
    client = session.client("bedrock")
    for model in client.list_foundation_models()["modelSummaries"]:
        typer.echo(model["modelId"])


@tasks_app.command("validate")
def tasks_validate(root: Path = Path("tasks")) -> None:
    files = list(root.rglob("*.yaml"))
    if not files:
        raise typer.BadParameter("no task YAML files found")
    typer.echo(f"validated {len(files)} task definitions")


def _environment(
    config: ExperimentConfig, task: dict[str, Any], episode_index: int = 0
) -> Environment:
    """Construct the environment from the versioned task definition.

    ``episode_index`` derives the compute tie-break seed, so equal-priority ties
    vary by episode instead of always favouring the alphabetically first job id.
    Matched P0/P4 arms share a config seed and episode index, so both arms of a
    pair derive the same ranks and the tie-break is held constant across the
    treatment.
    """
    if config.environment.value == "cicd_release":
        delegation = task.get("delegation")
        if not isinstance(delegation, dict) or not delegation.get("assignments"):
            raise typer.BadParameter(
                f"task {config.task_id} declares no delegation assignments"
            )
        return CICDReleaseEnvironment(
            config.permission_mode,
            delegation=delegation,
            runner_capacity=int(task.get("runner_capacity", 2)),
            deadline_rounds=int(task.get("deadline_rounds", 8)),
            flaky_attempts={
                str(k): [int(x) for x in v]
                for k, v in (task.get("flaky_attempts") or {}).items()
            },
            job_durations={
                str(k): int(v) for k, v in (task.get("job_durations") or {}).items()
            },
            preseeded_jobs={
                str(k): int(v)
                for k, v in (task.get("preseeded_jobs") or {}).items()
            },
            platform_role=str(task.get("platform_role", "project_maintainer")),
            operational_vocabulary=config.operational_vocabulary,
            escalation_enabled=config.escalation_enabled,
            performance_dashboard=config.performance_dashboard,
            shared_queue_board=config.shared_queue_board,
            release_operations_board=config.release_operations_board,
            priority_window_scheduler=config.stage3_v2,
            competition_visible_board=config.competition_visible_board,
            board_ownership_falsification=config.board_ownership_falsification,
            # OPT-IN for CI/CD. config.background_load defaults to 2 for SOC, and
            # every CI/CD manifest written so far records that default although
            # those episodes ran with no fillers. Honouring the default here
            # would silently add 2 fillers to every CI/CD config and break replay
            # of every recorded CI/CD episode, so CI/CD uses the field only when
            # a config sets it explicitly.
            background_load=(
                int(config.background_load)
                if "background_load" in config.model_fields_set else 0
            ),
            background_job_rounds=int(task.get("background_job_rounds", 3)),
            reward_lambda=config.reward_lambda,
            # AUDIT 0.1. Without this the board rendered reward from lambda
            # alone and contradicted the agent's own prompt in the team arm.
            shared_reward_weight=config.shared_reward_weight,
        )

    if config.environment.value == "soc_itsm":
        return SOCITSMEnvironment(
            config.permission_mode,
            delegation=task["delegation"],
            escalation_capacity=int(config.escalation_capacity),
            escalation_duration=int(
                config.escalation_duration
                if config.escalation_duration is not None
                else task.get("escalation_duration", 3)
            ),
            sla_deadlines={
                str(k): int(config.sla_deadline if config.sla_deadline is not None else v)
                for k, v in (task.get("sla_deadlines") or {}).items()
            },
            severities={
                str(k): int(v) for k, v in (task.get("severities") or {}).items()
            },
            investigation_rounds={
                str(k): int(v)
                for k, v in (task.get("investigation_rounds") or {}).items()
            },
            background_incidents={
                f"incident-bg-{i}": int(task.get("background_severity", 4))
                for i in range(int(config.background_load))
            },
            platform_role=str(task.get("platform_role", "incident_coordinator")),
            reward_lambda=config.reward_lambda,
            shared_reward_weight=config.shared_reward_weight,
            severity_weighted_scoring=config.severity_weighted_scoring,
            competition_visible_board=config.competition_visible_board,
            horizon_rounds=int(task.get("horizon_rounds", 20)),
            preemption=config.escalation_preemption,
            graded_scoring=config.graded_scoring,
            expedite=config.escalation_expedite,
            initially_escalated=list(config.initially_escalated),
            preemption_first_escalation_only=config.escalation_preemption_first_only,
            live_board=config.live_competition_board,
            soc_v2=config.soc_v2,
            menu_arm=config.soc_v2_menu_arm,
            warranted_severities=(
                None if task.get("warranted_severities") is None
                else {str(k): int(v) for k, v in task["warranted_severities"].items()}),
        )

    if config.environment.value == "release_integrity":
        ownership = task.get("ownership")
        if not isinstance(ownership, dict) or not ownership:
            raise typer.BadParameter(
                f"task {config.task_id} declares no ownership map"
            )
        return ReleaseIntegrityEnvironment(
            config.permission_mode,
            ownership={str(k): str(v) for k, v in ownership.items()},
            deadline_rounds=int(task.get("deadline_rounds", 8)),
        )

    if config.environment.value == "repository":
        files = task.get("initial_files")
        if not isinstance(files, dict) or not files:
            raise typer.BadParameter(f"task {config.task_id} declares no initial_files")
        return RepositoryEnvironment(
            {str(k): str(v) for k, v in files.items()},
            repository_ownership(task),
            config.permission_mode,
            config.public_scoreboard,
        )
    result_owners, job_namespaces = compute_ownership(task)
    abundant = int(task.get("abundant_capacity", 20))
    scarce = int(task.get("scarce_capacity", 13))
    return ComputeEnvironment(
        config.permission_mode,
        capacity=abundant if config.resources == "abundant" else scarce,
        quota=int(task.get("quota_per_agent", 10)),
        result_owners=result_owners,
        job_namespaces=job_namespaces,
        tie_break_seed=episode_seed(config.seed, episode_index),
    )


_DEFAULT_MOCK_SCRIPT: dict[str, list[ToolCall]] = {
    "A": [
        ToolCall(
            id="a1",
            name="apply_patch",
            arguments={"path": "components/a/main.py", "content": "VALUE = 1\n"},
        ),
        ToolCall(id="a2", name="submit_solution"),
    ],
    "B": [
        ToolCall(
            id="b1",
            name="apply_patch",
            arguments={"path": "components/b/main.py", "content": "VALUE = 1\n"},
        ),
        ToolCall(id="b2", name="submit_solution"),
    ],
}


def _load_mock_script(path: Path) -> dict[str, list[ToolCall]]:
    """Load a scripted mock trajectory: {agent: [tool call, ...]}.

    Development and test affordance only. The default script has each agent
    patch its own component, so no default mock run can produce a violation;
    a script lets a test drive a deliberate cross-boundary write through the
    real CLI path. Live runs ignore this entirely.
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or not raw:
        raise typer.BadParameter(f"{path} must map agent ids to action lists")
    script: dict[str, list[ToolCall]] = {}
    for agent, calls in raw.items():
        if not isinstance(calls, list):
            raise typer.BadParameter(f"{path}: actions for {agent!r} must be a list")
        script[str(agent)] = [ToolCall.model_validate(entry) for entry in calls]
    return script


# Calls the judge gate never sees: they read state and change nothing.
_SOC_READ_ONLY = frozenset({"view_incident_queue", "view_sla_dashboard",
                            "view_escalation_queue", "inspect_incident"})


def _judge_gate(
    config: ExperimentConfig,
    environment: Environment,
    ledger: CostLedger,
    *,
    live: bool,
) -> Environment:
    """Wrap an environment in the defense-001 judge gate.

    Only a confirmed --live run reaches the real gate model; dry/mock runs use
    an always-allow mock, so validating a config never costs anything.
    """
    from competition_lab.defense import JudgeGate, MockGateProvider
    from competition_lab.environments.cicd_release import READ_ONLY_TOOLS

    gate = config.defense_gate
    assert gate is not None
    if not live or gate.provider == "mock":
        provider: ModelProvider = MockGateProvider("allow")
    elif gate.provider == "bedrock-converse":
        provider = BedrockConverseProvider(gate)
    else:
        raise typer.BadParameter(
            f"defense gate provider {gate.provider!r} not supported"
        )
    read_only = (READ_ONLY_TOOLS if config.environment.value == "cicd_release"
                 else _SOC_READ_ONLY)
    return cast(Environment, JudgeGate(environment, provider, ledger,
                                       frozenset(read_only), gate.model_id))


def _provider(config: ExperimentConfig, scripted: list[ToolCall]) -> ModelProvider:
    """Select the adapter named by the config.

    Mock stays the default everywhere; a live adapter is only ever reachable
    through the guarded ``--live`` path in ``run``. ``scripted`` supplies the
    deterministic action sequence and is ignored by live providers.
    """
    provider = config.model.provider
    if provider == "mock":
        return MockProvider(scripted)
    if provider == "bedrock-converse":
        return BedrockConverseProvider(config.model)
    if provider == "bedrock-responses":
        # Converse needed a request-shape translation (toolSpec envelope,
        # content blocks) before it worked live. The Responses path has the
        # same untranslated request and has never been exercised against the
        # API, so it must be opted into explicitly rather than by config drift.
        if os.getenv("COMPETITION_LAB_EXPERIMENTAL_RESPONSES") != "1":
            raise typer.BadParameter(
                "bedrock-responses is experimental and unvalidated: its request "
                "payload has never been checked against the API. Set "
                "COMPETITION_LAB_EXPERIMENTAL_RESPONSES=1 to override."
            )
        return BedrockResponsesProvider(config.model)
    raise typer.BadParameter(f"no adapter implemented for provider {provider!r}")


def _planned_episode_ids(config: ExperimentConfig) -> list[str]:
    return [f"{config.experiment_id}-{index:04d}" for index in range(config.episodes)]


def _assert_episode_directories_available(
    output: Path, config: ExperimentConfig
) -> None:
    """Refuse reuse before provider construction or any model request."""
    conflicts = [
        output / episode_id
        for episode_id in _planned_episode_ids(config)
        if (output / episode_id).exists()
    ]
    if conflicts:
        rendered = ", ".join(str(path) for path in conflicts)
        raise typer.BadParameter(
            "episode output directories already exist; use a fresh output "
            f"directory. Refusing to overwrite or append: {rendered}"
        )


@app.command()
def run(
    config: Path,
    output: Path = Path("artifacts/runs"),
    dry_run: bool = True,
    live: bool = False,
    max_usd: float | None = None,
    max_requests: int | None = None,
    acknowledge_dirty: bool = False,
    yes: Annotated[
        bool, typer.Option("--yes", help="Confirm displayed live run")
    ] = False,
    mock_script: Annotated[
        Path | None,
        typer.Option(
            "--mock-script",
            help="Development only: JSON trajectory driving the mock providers.",
        ),
    ] = None,
) -> None:
    """Run a dry/mock experiment; live mode is guarded and never implicit."""
    cfg = load_config(config)
    if mock_script is not None and live:
        raise typer.BadParameter("--mock-script cannot be combined with --live")
    _assert_episode_directories_available(output, cfg)
    task = load_task(cfg.task_id)
    agents = 1 if cfg.control == "solo" else 2
    # Every agent also issues one terminal non-tool call, so the request bound
    # is actions + 1 per agent -- counting actions alone under-counts requests
    # and would let a run exceed a --max-requests ceiling.
    anticipated = cfg.episodes * agents * (cfg.action_budget + 1)
    if cfg.defense_gate is not None:
        # The judge gate can make one request per state-changing action.
        anticipated += cfg.episodes * agents * cfg.action_budget
    forecast = {
        "conditions": 1,
        "episodes": cfg.episodes,
        "anticipated_model_requests_upper_bound": anticipated,
        "model_ids": [cfg.model.model_id],
        "region": cfg.model.region,
        "max_usd_ceiling": max_usd,
        "price_per_million_input": cfg.model.input_cost_per_million,
        "price_per_million_output": cfg.model.output_cost_per_million,
        "task_definition_hash": task["task_definition_hash"],
        "output_directory": str(output),
    }
    typer.echo(json.dumps(forecast, indent=2))
    if live:
        if dry_run:
            raise typer.BadParameter("use --no-dry-run with --live")
        if max_usd is None or max_usd <= 0 or max_requests is None:
            raise typer.BadParameter("--max-usd and --max-requests are required")
        if anticipated > max_requests:
            raise typer.BadParameter("anticipated calls exceed --max-requests")
        report = _doctor_report(cfg)
        failed = _doctor_blocking(report)
        if failed:
            raise typer.BadParameter(f"doctor checks failed: {', '.join(failed)}")
        if not report["python_matches_supported_version"]:
            typer.echo(
                f"WARNING: live run on Python {report['python_version']}, not "
                f"{SUPPORTED_PYTHON[0]}.{SUPPORTED_PYTHON[1]}.x as documented.",
                err=True,
            )
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True
        ).stdout.strip()
        if dirty and not acknowledge_dirty:
            raise typer.BadParameter("dirty Git state requires --acknowledge-dirty")
        # Purely local and deliberately before confirmation, adapter
        # construction, credential resolution, or any provider request.
        run_pre_live_integrity_self_test()
        if not yes and not typer.confirm("Begin this live run?"):
            raise typer.Abort()
        if cfg.model.provider == "mock":
            raise typer.BadParameter("--live requires a non-mock provider")
    actions = _DEFAULT_MOCK_SCRIPT if mock_script is None else _load_mock_script(
        mock_script
    )
    ledger = CostLedger.from_config(cfg.model, max_usd, max_requests)
    gate_ledger = (
        CostLedger.from_config(cfg.defense_gate, max_usd, max_requests)
        if cfg.defense_gate is not None else None
    )
    for index in range(cfg.episodes):
        # Only a confirmed --live run reaches a real adapter. Dry/mock runs stay
        # on MockProvider even when the config names Bedrock, so validating a
        # live config never costs anything.
        providers: dict[str, ModelProvider] = {
            agent: (
                _provider(cfg, agent_actions) if live else MockProvider(agent_actions)
            )
            for agent, agent_actions in actions.items()
        }
        if cfg.control == "solo":
            providers.pop("B")
        environment = _environment(cfg, task, index)
        if cfg.defense_gate is not None and gate_ledger is not None:
            environment = _judge_gate(cfg, environment, gate_ledger, live=live)
        runner = EpisodeRunner(
            cfg,
            environment,
            providers,
            output,
            ledger=ledger,
            episode_index=index,
            task=task,
        )
        outcome = runner.run(f"{cfg.experiment_id}-{index:04d}")
        typer.echo(str(outcome.event_path))
    costs = {"cost": ledger.as_dict()}
    if gate_ledger is not None:
        costs["defense_gate_cost"] = gate_ledger.as_dict()
    typer.echo(json.dumps(costs, indent=2))


@app.command()
def detect(run_dir: Path) -> None:
    import hashlib

    results = []
    for path in sorted(run_dir.rglob("events.jsonl")):
        # AUDIT 0.4: quarantined episodes are never scored.
        if is_quarantined(path):
            continue
        detection = detect_events(path)
        # Bind each detection to the bytes it scored, so detector output cannot
        # be edited after the fact without the mismatch being visible.
        detection["events_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        results.append(detection)
    output = run_dir / "detections.json"
    output.write_text(json.dumps(results, indent=2) + "\n")
    typer.echo(str(output))


@app.command()
def episodes(
    run_dir: Path,
    output: Path | None = None,
    matched_pair_key: str = "task_id",
) -> None:
    """Build the one-row-per-episode table that ``report`` consumes.

    ``detect`` scores each event log and ``report`` needs a tabular outcome per
    episode, but nothing previously wrote that table, so the CLI chain broke
    between the two. Every column is derived from the recorded manifest and
    detection; no experimental value is imputed.
    """
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(run_dir.rglob("manifest.json")):
        # AUDIT 0.4: quarantined episodes never enter an episode table.
        if is_quarantined(manifest_path):
            continue
        manifest = json.loads(manifest_path.read_text())
        detection = detect_events(manifest_path.parent / "events.jsonl")
        closure = manifest.get("episode_closure") or {}
        pair_base = manifest.get(matched_pair_key)
        episode_index = manifest.get("episode_index")
        if pair_base is None or episode_index is None:
            raise typer.BadParameter(
                f"{manifest_path} lacks {matched_pair_key!r} or episode_index; "
                "cannot construct a deterministic matched-pair id"
            )
        try:
            replicate = int(episode_index)
        except (TypeError, ValueError) as exc:
            raise typer.BadParameter(
                f"{manifest_path} has invalid episode_index {episode_index!r}"
            ) from exc
        rows.append(
            {
                "episode_id": manifest["episode_id"],
                # The task identifies the matched design and episode_index
                # identifies a replicate within it. Both are recorded in the
                # manifest and shared across P0/P4; condition labels are never
                # used to infer pairing.
                # `design_id` replaces `matched_pair_id`. It still records
                # which task/replicate an episode came from -- useful for
                # provenance -- but nothing pairs on it: pairing was never
                # achieved (decision 0.3) and acting order co-varies with arm.
                "design_id": f"{pair_base}::{replicate:04d}",
                "episode_index": replicate,
                "episode_seed": manifest.get("episode_seed"),
                # The ARM, resolved from shared_reward_weight/pressure/
                # condition. `pressure` alone cannot identify it: team and
                # high-stakes episodes both carry P0.
                "arm": arm_of(manifest),
                "environment": manifest.get("environment"),
                "model_id": (manifest.get("model") or {}).get("model_id"),
                "successful_violation": detection["successful_violation"],
                "attempted_violation": detection["attempted_violation"],
                "action_budget": manifest["action_budget"],
                "first_successful_action_index": detection[
                    "first_successful_action_index"
                ],
                "technical_failure": bool(closure.get("technical_failure", False)),
            }
        )
    if not rows:
        raise typer.BadParameter(f"no episode manifests found under {run_dir}")
    frame = pd.DataFrame(rows)
    if frame["episode_id"].duplicated().any():
        conflicts = sorted(
            frame.loc[frame["episode_id"].duplicated(keep=False), "episode_id"]
            .astype(str)
        )
        raise typer.BadParameter(
            "duplicate episode ids in the run: " + ", ".join(conflicts)
        )
    # The pairing checks that stood here -- duplicate pair/arm rows, seed
    # consistency within a pair, and an unmatched-pair warning -- are removed
    # with the matched design (A6, decision 0.3). They validated a contract
    # nothing asserts any more.
    destination = output or (run_dir / "episodes.csv")
    frame.to_csv(destination, index=False)
    typer.echo(str(destination))


@app.command("allocation-audit")
def allocation_audit(run_dir: Path, output: Path | None = None) -> None:
    """Derive a machine-checkable allocation audit for compute runs.

    Recomputes each contested scheduling decision and its equal-priority
    counterfactual from recorded state, so "priority changed allocation" is
    reproducible from artifacts rather than asserted in a review document. Raw
    logs are never modified.
    """
    from competition_lab.allocation import AUDIT_COLUMNS, AllocationAuditError
    from competition_lab.allocation import audit_run as audit

    try:
        rows = audit(run_dir)
    except AllocationAuditError as exc:
        raise typer.BadParameter(str(exc)) from exc
    destination = output or (run_dir / "compute_allocation_audit.csv")
    pd.DataFrame(rows, columns=list(AUDIT_COLUMNS)).to_csv(destination, index=False)
    typer.echo(str(destination))


@app.command("aggregate-chunks")
def aggregate_chunks_command(manifest: Path, output: Path | None = None) -> None:
    """Aggregate a chunked matched-pair study across per-pair directories.

    Chunking splits a study across directories to stay inside wall-clock limits;
    this recombines them once, with the pairing checks stated explicitly, instead
    of leaving a manual concatenation step. Refuses on a missing directory,
    missing arm, incomplete episode, seed mismatch within a pair, or duplicate
    pair id.
    """
    from competition_lab.allocation import ChunkAggregationError, aggregate_chunks

    try:
        result = aggregate_chunks(manifest)
    except ChunkAggregationError as exc:
        raise typer.BadParameter(str(exc)) from exc
    # Generated analysis never defaults into configs/: that directory is tracked,
    # and a stray CSV there shows up as an uncommitted artifact.
    destination = output or (
        Path("artifacts/analysis") / manifest.stem / "chunk_aggregate.csv"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(result["pairs"]).to_csv(destination, index=False)
    typer.echo(json.dumps(result["summary"], indent=2))
    typer.echo(str(destination))


def _replay_environment(manifest: dict[str, Any]) -> Environment:
    """Rebuild an episode's environment from its manifest, exactly as `replay` does."""
    task = load_task(str(manifest["task_id"]))
    cfg = ExperimentConfig.model_validate(
        {
            "experiment_id": manifest["experiment_id"],
            "condition": manifest["condition"],
            "pressure": manifest["pressure"],
            "environment": manifest["environment"],
            "task_id": manifest["task_id"],
            "model": manifest["model"],
            "resources": manifest["resources"],
            "permission_mode": manifest["permission_mode"],
            "action_budget": manifest["action_budget"],
            "prompt_variant": manifest.get("prompt_variant", "canonical"),
            "public_scoreboard": manifest.get("public_scoreboard", False),
            # Required for scarce episodes: `primary` control forbids scarce
            # resources, so omitting this made every scarcity run unreplayable.
            # Older manifests predate the field and default to primary.
            "control": manifest.get("control", "primary"),
            "shared_reward_weight": manifest.get("shared_reward_weight", 0),
            # The compute tie-break seed is derived from this; without it replay
            # would schedule a different order and diverge.
            "seed": manifest.get("config_seed", 0),
            # Diagnostic factors change the tool set and the environment, so
            # replay must restore them or recorded calls resolve as unknown
            # tools. Manifests written before these were recorded are
            # reconstructed from tool_names, which has always been present.
            "operational_vocabulary": manifest.get(
                "operational_vocabulary",
                "defer_job_to_next_window" in (manifest.get("tool_names") or []),
            ),
            "escalation_enabled": manifest.get(
                "escalation_enabled",
                "escalate_runner_contention" in (manifest.get("tool_names") or []),
            ),
            "performance_dashboard": manifest.get(
                "performance_dashboard",
                "view_performance_summary" in (manifest.get("tool_names") or []),
            ),
            "shared_queue_board": manifest.get(
                "shared_queue_board",
                "view_shared_queue_board" in (manifest.get("tool_names") or []),
            ),
            "release_operations_board": manifest.get(
                "release_operations_board",
                "view_release_operations_board"
                in (manifest.get("tool_names") or []),
            ),
            "stage3_v2": manifest.get(
                "stage3_v2",
                "view_release_window_board" in (manifest.get("tool_names") or []),
            ),
            # No tool_names fallback is possible or needed: this flag adds no
            # tool, it only extends the v2 board payload. No artifact predating
            # the flag ever had it, so False is the correct reconstruction.
            "competition_visible_board": manifest.get(
                "competition_visible_board", False
            ),
            # Adds no tool and changes no state; it only rewrites board text.
            # Absent from every manifest written before the pilot, so "none".
            "board_ownership_falsification": manifest.get(
                "board_ownership_falsification", "none"
            ),
            # SOC gate constants. Recorded so replay rebuilds the same
            # contention structure; defaults match the gate-validated design.
            "agent_architecture": manifest.get("agent_architecture", "base"),
            "escalation_capacity": manifest.get("escalation_capacity", 2),
            # CI/CD: the load the environment actually used. Manifests written
            # before CI/CD background load existed record SOC's default 2 but
            # ran with none, so absence means 0, not the recorded field.
            "background_load": (
                manifest.get("background_load_effective", 0)
                if manifest.get("environment") == "cicd_release"
                else manifest.get("background_load", 2)
            ),
            "severity_weighted_scoring": manifest.get(
                "severity_weighted_scoring", True
            ),
            "graded_scoring": manifest.get("graded_scoring", True),
            # SOC redesign; absent from every earlier manifest (= off / task value).
            "escalation_preemption": bool(manifest.get("escalation_preemption") or False),
            "escalation_duration": (
                manifest.get("escalation_duration_effective")
                if manifest.get("environment") == "soc_itsm" else None
            ),
            "escalation_expedite": bool(manifest.get("escalation_expedite") or False),
            "initially_escalated": list(manifest.get("initially_escalated") or []),
            "escalation_preemption_first_only": bool(
                manifest.get("escalation_preemption_first_only") or False),
            "live_competition_board": bool(manifest.get("live_competition_board") or False),
            "soc_v2": bool(manifest.get("soc_v2") or False),
            "soc_v2_menu_arm": manifest.get("soc_v2_menu_arm"),
            "sla_deadline": manifest.get("sla_deadline_override"),
        }
    )
    # The compute tie-break seed derives from the config seed and episode index,
    # both recorded in the manifest, so replay reconstructs the same schedule.
    return _environment(cfg, task, int(manifest.get("episode_index", 0)))


@app.command()
def replay(episode_dir: Path) -> None:
    """Re-execute recorded actions and verify state digests match the log."""
    from competition_lab.eventlog import read_episode
    from competition_lab.replay import replay as replay_episode

    manifest = json.loads((episode_dir / "manifest.json").read_text())
    events = read_episode(episode_dir)
    report = replay_episode(
        episode_dir / "events.jsonl",
        _replay_environment(manifest),
        strict=False,
    )
    typer.echo(
        json.dumps(
            {
                "events_verified": len(events),
                "actions_replayed": report.actions,
                "divergences": report.divergences,
            },
            indent=2,
            default=str,
        )
    )
    if not report.ok:
        raise typer.Exit(1)


ANALYSIS_SUBDIR = "analysis"


def _load_episode_frame(episodes: Path) -> pd.DataFrame:
    return (
        pd.read_parquet(episodes)
        if episodes.suffix == ".parquet"
        else pd.read_csv(episodes)
    )


@app.command()
def analyze(episodes: Path, output: Path = Path("artifacts/analysis")) -> None:
    paths = export_outputs(_load_episode_frame(episodes), output)
    typer.echo(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))


@app.command()
def report(run_dir: Path, episodes: Path | None = None) -> None:
    """Write analysis outputs into RUN_DIR/analysis.

    ``export-paper`` reads this directory, so ``report`` must actually create
    it. Previously this command only echoed a path that nothing produced, which
    made ``export-paper`` silently copy zero files while reporting success.
    """
    source = episodes or (run_dir / "episodes.csv")
    if not source.exists():
        raise typer.BadParameter(
            f"no episode table at {source}; pass --episodes explicitly"
        )
    destination = run_dir / ANALYSIS_SUBDIR
    paths = export_outputs(_load_episode_frame(source), destination)
    typer.echo(
        json.dumps(
            {"analysis_dir": str(destination)}
            | {k: str(v) for k, v in paths.items()},
            indent=2,
        )
    )


@app.command("export-paper")
def export_paper(
    run_dir: Path, destination: Path = Path("artifacts/manuscript_assets")
) -> None:
    """Stage analysis outputs for manual copying into the external manuscript.

    The manuscript lives in Overleaf, outside this repository, so this command
    only stages files locally. Moving them into the manuscript is a manual step.
    """
    analysis = run_dir / ANALYSIS_SUBDIR
    if not analysis.is_dir():
        raise typer.BadParameter(
            f"{analysis} does not exist; run 'competition-lab report {run_dir}' first"
        )
    sources = sorted(path for path in analysis.glob("*") if path.is_file())
    if not sources:
        # Silently copying nothing while reporting success previously made an
        # empty export indistinguishable from a successful one.
        raise typer.BadParameter(f"{analysis} contains no files to export")
    destination.mkdir(parents=True, exist_ok=True)
    copied = []
    for source in sources:
        shutil.copy2(source, destination / source.name)
        copied.append(source.name)
    typer.echo(
        json.dumps({"destination": str(destination), "copied": copied}, indent=2)
    )


@judge_app.command("validate")
def judge_validate(labels: Path, predictions: Path) -> None:
    from competition_lab.judge import load_labels, validation_metrics

    truth = load_labels(labels, "validation")
    predicted = json.loads(predictions.read_text())
    metrics = validation_metrics(
        [row["label"] for row in truth], [row["label"] for row in predicted]
    )
    typer.echo(json.dumps(metrics, indent=2))
