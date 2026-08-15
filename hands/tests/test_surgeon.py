import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from hands.agents.surgeon import SurgeonAgent
from shared.types import Diagnosis, RemediationRequest, Approval, CostEstimate


def _mock_opencue_success():
    return patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "action": "reroute"},
            raise_for_status=MagicMock(),
        ),
    )


def _gpu_remediation():
    return RemediationRequest(
        trace_id="txn-test",
        diagnosis=Diagnosis(
            failure_type="gpu_memory_exhaustion",
            affected_nodes=["node-7"],
            affected_frames=[1847],
            scene="scene_47",
            recommended_action="reroute_to_healthy_nodes",
            confidence=0.94,
        ),
        cost_estimate=CostEstimate(preemptible_gpus=2, estimated_cost_usd=4.50, duration_minutes=15),
        approval=Approval(approved=True, budget_remaining_usd=245.50),
    )


@pytest.mark.asyncio
async def test_surgeon_executes_reroute():
    agent = SurgeonAgent(trace_id="txn-test", gcp=None)
    with _mock_opencue_success():
        result = await agent.execute(_gpu_remediation())
    assert result["status"] == "success"
    assert any(a["action"] == "reroute_job" for a in result["actions_taken"])


@pytest.mark.asyncio
async def test_surgeon_reports_partial_failure_when_opencue_fails():
    """gpu_memory_exhaustion runs reroute_job (via OpenCue) and
    spin_up_preemptible (gcp=None here -> skipped_no_gcp, not a failure).
    A failed OpenCue call must surface as partial_failure, not success."""
    agent = SurgeonAgent(trace_id="txn-test", gcp=None)
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("opencue unreachable"),
    ):
        result = await agent.execute(_gpu_remediation())

    assert result["status"] == "partial_failure"
    reroute = next(a for a in result["actions_taken"] if a["action"] == "reroute_job")
    assert reroute["status"] == "failed"


@pytest.mark.asyncio
async def test_surgeon_reports_failure_when_all_actions_fail():
    """Both OpenCue and the GCP call failing must report status: failure,
    not success — this was the bug in review #7."""
    gcp = AsyncMock()
    gcp.start_preemptible_instances.side_effect = RuntimeError("quota exceeded")
    agent = SurgeonAgent(trace_id="txn-test", gcp=gcp)

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("opencue unreachable"),
    ):
        result = await agent.execute(_gpu_remediation())

    assert result["status"] == "failure"
    assert all(a["status"] == "failed" for a in result["actions_taken"])


@pytest.mark.asyncio
async def test_surgeon_skips_gcp_gracefully_when_not_configured():
    """gcp=None must not be treated as a failure — it's an intentional
    demo/dev-mode skip (review #25's missing-coverage note)."""
    agent = SurgeonAgent(trace_id="txn-test", gcp=None)
    with _mock_opencue_success():
        result = await agent.execute(_gpu_remediation())

    assert result["status"] == "success"
    spin_up = next(a for a in result["actions_taken"] if a["action"] == "spin_up_preemptible")
    assert spin_up["status"] == "skipped_no_gcp"
