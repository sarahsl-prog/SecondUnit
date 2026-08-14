import pytest
from hands.agents.surgeon import SurgeonAgent
from shared.types import Diagnosis, RemediationRequest, Approval, CostEstimate


@pytest.mark.asyncio
async def test_surgeon_executes_reroute():
    agent = SurgeonAgent(trace_id="txn-test")
    remediation = RemediationRequest(
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
    result = await agent.execute(remediation)
    assert result["status"] == "success"
    assert any(a["action"] == "reroute_job" for a in result["actions_taken"])
