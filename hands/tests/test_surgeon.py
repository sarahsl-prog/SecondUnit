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


def _gpu_remediation(context=None):
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
        context=context or {},
    )


def _mock_opencue_capture():
    """Like _mock_opencue_success but returns the mock so callers can
    inspect what payload was actually posted."""
    mock_post = AsyncMock(
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"status": "success", "action": "reroute"},
            raise_for_status=MagicMock(),
        )
    )
    return patch("httpx.AsyncClient.post", mock_post), mock_post


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


@pytest.mark.asyncio
async def test_surgeon_reroutes_to_healthy_node_from_context():
    """review #8: reroute must use context.healthy_nodes, excluding the
    affected node, instead of always hardcoding node-3."""
    agent = SurgeonAgent(trace_id="txn-test", gcp=None)
    remediation = _gpu_remediation(context={"healthy_nodes": ["node-7", "node-2", "node-5"]})

    patcher, mock_post = _mock_opencue_capture()
    with patcher:
        await agent.execute(remediation)

    sent_payload = mock_post.call_args.kwargs["json"]
    # node-7 is affected_nodes, so node-2 (first healthy, non-affected) wins
    assert sent_payload["target_node"] == "node-2"


@pytest.mark.asyncio
async def test_surgeon_falls_back_to_node3_without_healthy_nodes():
    """No context.healthy_nodes provided -> demo fallback stays node-3."""
    agent = SurgeonAgent(trace_id="txn-test", gcp=None)
    remediation = _gpu_remediation()  # context={}

    patcher, mock_post = _mock_opencue_capture()
    with patcher:
        await agent.execute(remediation)

    sent_payload = mock_post.call_args.kwargs["json"]
    assert sent_payload["target_node"] == "node-3"
