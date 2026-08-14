# simulator/tests/test_failures.py
from fastapi.testclient import TestClient
from simulator.main import app

client = TestClient(app)

def test_trigger_gpu_memory_exhaustion():
    response = client.post("/simulator/trigger/gpu_memory_exhaustion")
    assert response.status_code == 200
    data = response.json()
    assert data["scenario"] == "gpu_memory_exhaustion"
    assert data["applied"] is True
