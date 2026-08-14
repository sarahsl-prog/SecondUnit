import pytest
from brain.agents.quartermaster import QuartermasterAgent
from shared.types import Diagnosis, CostEstimate

@pytest.mark.asyncio
async def test_quartermaster_approves_within_budget():
    agent = QuartermasterAgent(trace_id="txn-test")
    diagnosis = Diagnosis(
        failure_type="gpu_memory_exhaustion",
        affected_nodes=["node-7"],
        affected_frames=[1847],
        scene="scene_47",
        recommended_action="reroute_to_healthy_nodes",
        confidence=0.94,
    )
    result = await agent.evaluate(diagnosis)
    assert result["decision"] == "approve"
    assert result["cost_estimate"]["estimated_cost_usd"] == 4.50
