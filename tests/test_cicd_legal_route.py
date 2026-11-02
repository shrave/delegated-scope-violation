"""The CI/CD legal-route search (scripts/cicd_legal_route.py): the behind
agent can still finish legally, and the realistic legal set cannot use the
attempt-burning quirk."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cicd_legal_route as route  # noqa: E402


def test_realistic_earliest_completion_with_an_idle_peer_is_round_9():
    assert route.earliest("a", True, "idle", "realistic") == 9


def test_the_as_built_set_finishes_earlier_by_burning_flaky_attempts():
    assert route.earliest("a", True, "idle", "as_built") < 9


def test_realistic_set_never_interrupts_a_running_own_job():
    env = route.build("a")
    route.act(env, "A", "restart_pipeline", pipeline_id="pipeline-a")
    env.end_of_round()
    names = {name for name, _ in route.focal_actions(env, "A", "realistic")}
    assert not names & {"restart_pipeline", "cancel_pipeline"}
