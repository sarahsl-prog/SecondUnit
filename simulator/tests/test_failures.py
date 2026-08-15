# simulator/tests/test_failures.py
import pytest
from fastapi.testclient import TestClient

from simulator.failures import FAILURE_SCENARIOS
from simulator.main import app

client = TestClient(app)

def test_trigger_gpu_memory_exhaustion():
    response = client.post("/simulator/trigger/gpu_memory_exhaustion")
    assert response.status_code == 200
    data = response.json()
    assert data["scenario"] == "gpu_memory_exhaustion"
    assert data["applied"] is True


@pytest.mark.parametrize("scenario_name", list(FAILURE_SCENARIOS))
def test_trigger_all_five_scenarios(scenario_name):
    """review's outstanding-decision follow-up: only gpu_memory_exhaustion
    was exercised end-to-end before. All 5 documented scenarios
    (FAILURE_SCENARIOS) must at least trigger and seed a job without
    error."""
    response = client.post(f"/simulator/trigger/{scenario_name}", params={"target_node": "node-3"})
    assert response.status_code == 200
    data = response.json()
    assert data["scenario"] == scenario_name
    assert data["applied"] is True
    assert "job_id" in data

    jobs = client.get("/simulator/jobs", params={"node": "node-3"}).json()["jobs"]
    assert any(j["id"] == data["job_id"] for j in jobs)
