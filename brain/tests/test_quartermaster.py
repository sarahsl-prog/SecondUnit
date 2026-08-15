from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from brain.agents.quartermaster import QuartermasterAgent
from shared.exceptions import HandsUnreachable
from shared.types import Diagnosis


def _make_agent(tmp_path, trace_id="txn-test"):
    return QuartermasterAgent(trace_id=trace_id, state_path=tmp_path / "budget.json")


def _gpu_diagnosis():
    return Diagnosis(
        failure_type="gpu_memory_exhaustion",
        affected_nodes=["node-7"],
        affected_frames=[1847],
        scene="scene_47",
        recommended_action="reroute_to_healthy_nodes",
        confidence=0.94,
    )


@pytest.mark.asyncio
async def test_quartermaster_approves_within_budget(tmp_path):
    agent = _make_agent(tmp_path)
    result = await agent.evaluate(_gpu_diagnosis())
    assert result["decision"] == "approve"
    assert result["cost_estimate"]["estimated_cost_usd"] == 4.50


@pytest.mark.asyncio
async def test_quartermaster_approves_zero_cost_failure_types(tmp_path):
    """corrupt_scene_file / network_timeout / license_failure estimate $0 and
    always clear the approval threshold — this exercises the non-GPU
    cost-estimation branches, not the deny path (see #25 follow-up for a
    true escalate/deny-triggering scenario)."""
    agent = _make_agent(tmp_path)
    for failure_type in ("corrupt_scene_file", "network_timeout", "license_failure"):
        diagnosis = Diagnosis(
            failure_type=failure_type,
            affected_nodes=["node-12"],
            affected_frames=[1],
            scene="scene_1",
            recommended_action="noop",
            confidence=0.5,
        )
        result = await agent.evaluate(diagnosis)
        assert result["decision"] == "approve"
        assert result["cost_estimate"]["estimated_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_quartermaster_tracks_cumulative_nightly_spend(tmp_path):
    """Two incidents that each individually clear the per-incident threshold
    must still be denied once their combined cost would exceed the nightly
    limit (review #6 — the original bug this fix addresses)."""
    agent = _make_agent(tmp_path)
    # Isolate the nightly-spend limit from the separate max_instances cap
    # (tested in test_quartermaster_enforces_max_instances) by raising it
    # for this test only.
    agent.policy["budget"]["preemptible_gpu"]["max_instances"] = 999

    # Nightly limit is $50, GPU incidents cost $4.50 each -> 11 fit ($49.50),
    # the 12th would push cumulative spend to $54.00 and must be denied.
    for _ in range(11):
        result = await agent.evaluate(_gpu_diagnosis())
        assert result["decision"] == "approve"

    twelfth = await agent.evaluate(_gpu_diagnosis())
    assert twelfth["decision"] == "deny"
    assert "nightly limit" in twelfth["reason"]


@pytest.mark.asyncio
async def test_quartermaster_enforces_max_instances(tmp_path):
    """cost_policy.yaml caps preemptible_gpu.max_instances at 4. Each GPU
    incident requests 2, so a 3rd incident (6 total) must be denied even
    though cumulative spend ($13.50) is well under the $50 nightly limit."""
    agent = _make_agent(tmp_path)

    for _ in range(2):
        result = await agent.evaluate(_gpu_diagnosis())
        assert result["decision"] == "approve"

    third = await agent.evaluate(_gpu_diagnosis())
    assert third["decision"] == "deny"
    assert "max_instances" in third["reason"]


@pytest.mark.asyncio
async def test_quartermaster_spend_persists_across_agent_instances(tmp_path):
    """Spend tracking must survive across a new QuartermasterAgent instance
    (e.g. a fresh instantiation per request in brain/main.py), not just
    within one object's lifetime."""
    state_path = tmp_path / "budget.json"
    first = QuartermasterAgent(trace_id="txn-1", state_path=state_path)
    await first.evaluate(_gpu_diagnosis())

    second = QuartermasterAgent(trace_id="txn-2", state_path=state_path)
    result = await second.evaluate(_gpu_diagnosis())
    assert result["approval"]["budget_remaining_usd"] == pytest.approx(50.0 - 4.50 * 2)


@pytest.mark.asyncio
async def test_send_to_hands_retries_then_succeeds(tmp_path):
    """review #23: a transient failure must not fail the whole remediation
    — send_to_hands should retry (design spec §3.3: max 3 attempts)."""
    agent = QuartermasterAgent(
        trace_id="txn-test", hands_url="http://hands:8080", state_path=tmp_path / "budget.json"
    )
    calls = []

    async def fake_post(url, **kwargs):
        calls.append(url)
        if len(calls) < 2:
            raise httpx.ConnectError("transient blip")
        return MagicMock(
            status_code=200, json=lambda: {"status": "complete"}, raise_for_status=MagicMock()
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post):
        result = await agent.send_to_hands({"trace_id": "txn-test"}, backoff_base_seconds=0)

    assert result == {"status": "complete"}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_send_to_hands_raises_after_exhausting_retries(tmp_path):
    agent = QuartermasterAgent(
        trace_id="txn-test", hands_url="http://hands:8080", state_path=tmp_path / "budget.json"
    )

    with (
        patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
        ) as mock_post,
        pytest.raises(HandsUnreachable),
    ):
        await agent.send_to_hands({"trace_id": "txn-test"}, backoff_base_seconds=0)

    assert mock_post.call_count == 3
