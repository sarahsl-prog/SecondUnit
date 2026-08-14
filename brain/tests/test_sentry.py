import pytest
from brain.agents.sentry import SentryAgent
from brain.tools.grafana_mcp import GrafanaMCPClient

@pytest.fixture
def mock_grafana():
    return GrafanaMCPClient(url="http://mock", api_key="test")

@pytest.mark.asyncio
async def test_sentry_detects_anomaly(mock_grafana):
    agent = SentryAgent(grafana=mock_grafana)
    report = await agent.run()
    assert report.anomaly_detected is True
    assert report.anomaly_type == "queue_depth_spike"
