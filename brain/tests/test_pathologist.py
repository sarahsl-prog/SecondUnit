import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from brain.agents.pathologist import PathologistAgent
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.types import AnomalyReport


@pytest.fixture
def mock_grafana():
    return GrafanaMCPClient(url="http://mock", api_key="test")


def _anomaly(nodes):
    return AnomalyReport(
        anomaly_detected=True,
        anomaly_type="queue_depth_spike",
        severity="high",
        affected_nodes=nodes,
    )


def _mock_simulator(node_logs: dict, jobs: list):
    """node_logs: {node_id: error_log}. jobs: list of job dicts shaped like
    /simulator/jobs's response. Stands in for a live simulator so
    PathologistAgent's classification/frame-lookup logic can be tested
    without docker-compose running."""
    status_nodes = {nid: {"error_log": log} for nid, log in node_logs.items()}

    async def fake_get(url, params=None, **kwargs):
        if url.endswith("/simulator/status"):
            return MagicMock(
                status_code=200, json=lambda: {"nodes": status_nodes}, raise_for_status=MagicMock()
            )
        if url.endswith("/simulator/jobs"):
            filtered = jobs
            if params and params.get("status"):
                filtered = [j for j in filtered if j["status"] == params["status"]]
            return MagicMock(
                status_code=200, json=lambda: {"jobs": filtered}, raise_for_status=MagicMock()
            )
        raise AssertionError(f"unexpected simulator URL: {url}")

    return patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_get)


@pytest.mark.asyncio
async def test_pathologist_diagnoses_gpu_failure(mock_grafana):
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    jobs = [{"id": "job-1", "frame": 101, "scene": "scene_12", "assigned_node": "node-7", "status": "failed"}]
    with _mock_simulator({"node-7": "CUDA out of memory at frame 101"}, jobs):
        diagnosis = await agent.run(_anomaly(["node-7"]))

    assert diagnosis.failure_type == "gpu_memory_exhaustion"
    assert diagnosis.confidence > 0.8
    assert diagnosis.affected_frames == [101]
    assert diagnosis.scene == "scene_12"


@pytest.mark.asyncio
async def test_pathologist_diagnoses_corrupt_scene_file(mock_grafana):
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    jobs = [{"id": "job-1", "frame": 5, "scene": "scene_47", "assigned_node": "node-2", "status": "failed"}]
    with _mock_simulator({"node-2": "Scene file malformed at line 4821"}, jobs):
        diagnosis = await agent.run(_anomaly(["node-2"]))
    assert diagnosis.failure_type == "corrupt_scene_file"


@pytest.mark.asyncio
async def test_pathologist_diagnoses_network_timeout(mock_grafana):
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    jobs = [{"id": "job-1", "frame": 9, "scene": "scene_47", "assigned_node": "node-4", "status": "failed"}]
    with _mock_simulator({"node-4": "Connection timed out to storage bucket"}, jobs):
        diagnosis = await agent.run(_anomaly(["node-4"]))
    assert diagnosis.failure_type == "network_timeout"


@pytest.mark.asyncio
async def test_pathologist_diagnoses_license_failure(mock_grafana):
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    jobs = [{"id": "job-1", "frame": 3, "scene": "scene_47", "assigned_node": "node-9", "status": "failed"}]
    with _mock_simulator({"node-9": "Arnold license server unreachable"}, jobs):
        diagnosis = await agent.run(_anomaly(["node-9"]))
    assert diagnosis.failure_type == "license_failure"


@pytest.mark.asyncio
async def test_pathologist_diagnoses_node12_gpu_failure(mock_grafana):
    """Generalizes past the original node-7-only hardcoding (review #10)."""
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    jobs = [{"id": "job-1", "frame": 200, "scene": "scene_12", "assigned_node": "node-12", "status": "failed"}]
    with _mock_simulator({"node-12": "CUDA out of memory"}, jobs):
        diagnosis = await agent.run(_anomaly(["node-12"]))
    assert diagnosis.failure_type == "gpu_memory_exhaustion"
    assert diagnosis.affected_frames == [200]
    assert diagnosis.scene == "scene_12"


@pytest.mark.asyncio
async def test_pathologist_falls_back_to_default_frames_when_no_job_data(mock_grafana):
    """No matching failed job in the simulator (e.g. anomaly not sourced
    from /simulator/trigger) -> deterministic demo default, not an error."""
    agent = PathologistAgent(grafana=mock_grafana, trace_id="txn-test")
    with _mock_simulator({}, []):
        diagnosis = await agent.run(_anomaly(["node-99"]))
    assert diagnosis.affected_frames == [1847, 1848]
    assert diagnosis.scene == "scene_47"
    assert diagnosis.failure_type == "unknown"
