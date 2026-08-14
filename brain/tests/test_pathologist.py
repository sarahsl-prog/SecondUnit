import pytest
from brain.agents.pathologist import PathologistAgent
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.types import AnomalyReport

@pytest.fixture
def mock_grafana():
    return GrafanaMCPClient(url="http://mock", api_key="test")

@pytest.mark.asyncio
async def test_pathologist_diagnoses_gpu_failure(mock_grafana):
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    anomaly = AnomalyReport(
        anomaly_detected=True,
        anomaly_type="queue_depth_spike",
        severity="high",
        affected_nodes=["node-7"],
    )
    diagnosis = await agent.run(anomaly)
    assert diagnosis.failure_type == "gpu_memory_exhaustion"
    assert diagnosis.confidence > 0.8
