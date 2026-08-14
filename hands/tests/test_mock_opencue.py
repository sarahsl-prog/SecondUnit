from fastapi.testclient import TestClient
from hands.main import app

client = TestClient(app)


def test_reroute_job():
    response = client.post("/opencue/reroute", json={
        "job_id": "job-1847",
        "target_node": "node-3",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["job_id"] == "job-1847"


def test_requeue_job():
    response = client.post("/opencue/requeue", json={
        "job_id": "job-1847",
        "frame": 42,
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["job_id"] == "job-1847"
    assert data["frame"] == 42


def test_kill_job():
    response = client.post("/opencue/kill", json={
        "job_id": "job-1847",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["job_id"] == "job-1847"
    assert data["action"] == "kill"
