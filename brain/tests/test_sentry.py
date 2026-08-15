import pytest

from brain.agents.sentry import SentryAgent
from brain.tools.grafana_mcp import GrafanaMCPClient


class FakeGrafana:
    """Per-query-string stub so tests can drive queue-depth and GPU-memory
    detection independently. Unlike GrafanaMCPClient (currently a fixed
    mock regardless of query — see review #18), this differentiates on
    the query string the way a real backend would."""

    def __init__(self, responses: dict[str, dict]):
        self._responses = responses

    async def query_metrics(self, query: str, time_range: str = "5m") -> dict:
        for key, response in self._responses.items():
            if key in query:
                return response
        return {"status": "success", "data": {"resultType": "vector", "result": []}}


def _metric_result(node: str, value: float) -> dict:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"node": node}, "value": [1692000000, str(value)]}],
        },
    }


@pytest.fixture
def mock_grafana():
    """Empty url -> GrafanaMCPClient's own built-in mock fallback (review
    #18), not a real HTTP call."""
    return GrafanaMCPClient(url="", api_key="test")


@pytest.mark.asyncio
async def test_sentry_detects_anomaly(mock_grafana):
    """GrafanaMCPClient is currently a stub returning the same fixed
    98.5 for any query (review #18), so both GPU and queue metrics read
    the same value — GPU is checked first, so it wins."""
    agent = SentryAgent(grafana=mock_grafana)
    report = await agent.run()
    assert report.anomaly_detected is True
    assert report.anomaly_type == "gpu_memory_spike"


@pytest.mark.asyncio
async def test_sentry_detects_gpu_memory_spike():
    grafana = FakeGrafana({
        "node_gpu_mem_percent": _metric_result("node-7", 99.0),
        "render_queue_depth": _metric_result("node-1", 10.0),
    })
    agent = SentryAgent(grafana=grafana)
    report = await agent.run()

    assert report.anomaly_detected is True
    assert report.anomaly_type == "gpu_memory_spike"
    assert report.affected_nodes == ["node-7"]
    assert report.grafana_context["metric"] == "node_gpu_mem_percent"
    assert report.grafana_context["value"] == 99.0


@pytest.mark.asyncio
async def test_sentry_detects_queue_depth_spike_when_gpu_is_healthy():
    grafana = FakeGrafana({
        "node_gpu_mem_percent": _metric_result("node-3", 40.0),
        "render_queue_depth": _metric_result("node-2", 95.0),
    })
    agent = SentryAgent(grafana=grafana)
    report = await agent.run()

    assert report.anomaly_detected is True
    assert report.anomaly_type == "queue_depth_spike"
    assert report.affected_nodes == ["node-2"]
    assert report.grafana_context["metric"] == "render_queue_depth"


@pytest.mark.asyncio
async def test_sentry_no_anomaly_when_both_metrics_healthy():
    grafana = FakeGrafana({
        "node_gpu_mem_percent": _metric_result("node-3", 40.0),
        "render_queue_depth": _metric_result("node-2", 10.0),
    })
    agent = SentryAgent(grafana=grafana)
    report = await agent.run()

    assert report.anomaly_detected is False
    assert report.anomaly_type == "none"
