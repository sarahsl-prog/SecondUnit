"""Tests for hands/main.py's /remediate endpoint (review #14)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import hands.main as hands_main
from hands.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_dispatcher_fallback(tmp_path, monkeypatch):
    """No Slack/Grafana config -> Dispatcher's guaranteed fallback (review
    outstanding-decision #10) fires on every successful /remediate call
    here. Point it at a tmp path instead of the real default so tests
    don't leave files in /tmp."""
    monkeypatch.setattr(
        hands_main.config, "dispatcher_fallback_path", str(tmp_path / "fallback.jsonl")
    )


def _valid_remediation_payload():
    return {
        "trace_id": "txn-test",
        "diagnosis": {
            "failure_type": "gpu_memory_exhaustion",
            "affected_nodes": ["node-7"],
            "affected_frames": [1847],
            "scene": "scene_47",
            "recommended_action": "reroute_to_healthy_nodes",
            "confidence": 0.94,
        },
        "cost_estimate": {
            "preemptible_gpus": 2, "estimated_cost_usd": 4.50, "duration_minutes": 15,
        },
        "approval": {"approved": True, "budget_remaining_usd": 45.50},
    }


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


def test_remediate_accepts_valid_request():
    with _mock_opencue_success():
        resp = client.post("/remediate", json=_valid_remediation_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["trace_id"] == "txn-test"


def test_remediate_rejects_malformed_body_with_422():
    """Before review #14, request: dict bypassed FastAPI validation and a
    typo'd/malformed body would surface as a 500 from inside the handler
    instead of a 422 at the framework layer."""
    # missing diagnosis/cost_estimate/approval
    resp = client.post("/remediate", json={"trace_id": "txn-test"})
    assert resp.status_code == 422


def test_remediate_rejects_invalid_failure_type_with_422():
    payload = _valid_remediation_payload()
    payload["diagnosis"]["failure_type"] = "not_a_real_failure_type"
    resp = client.post("/remediate", json=payload)
    assert resp.status_code == 422
