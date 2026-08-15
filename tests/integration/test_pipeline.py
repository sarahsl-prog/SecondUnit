# tests/integration/test_pipeline.py
"""End-to-end pipeline integration test: Simulator → Brain → Hands.

Uses FastAPI TestClient for in-process HTTP calls, with httpx mocked
for the Brain→Hands call so the full Sentry → Pathologist → Quartermaster
chain can be verified without a live Hands service.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

import brain.main as brain_main
from brain.main import app as brain_app, reset_dedup_cache
from simulator.main import app as simulator_app


@pytest.fixture(autouse=True)
def _reset_sentry_state(tmp_path, monkeypatch):
    """/sentry/poll's idempotency cache and Quartermaster's nightly-spend
    file are both module/disk-level state; reset them between tests so
    cross-file test order can't cause a spurious dedup or budget denial."""
    reset_dedup_cache()
    monkeypatch.setattr(brain_main.config, "budget_state_path", str(tmp_path / "budget.json"))
    yield
    reset_dedup_cache()


@pytest.fixture
def brain_client():
    return TestClient(brain_app)


@pytest.fixture
def simulator_client():
    return TestClient(simulator_app)


@pytest.fixture
def mock_hands_response():
    """Fake Hands /remediate response."""
    return {
        "status": "complete",
        "trace_id": "txn-mocked",
        "surgeon_result": {
            "trace_id": "txn-mocked",
            "status": "success",
            "actions_taken": [
                {"action": "reroute_job", "status": "ok"},
                {"action": "spin_up_preemptible", "status": "ok"},
            ],
            "gcp_resources_created": [],
        },
        "dispatch_result": {
            "status": "notified",
            "channels": [],
        },
    }


def test_full_pipeline(brain_client, simulator_client, mock_hands_response):
    """Trigger GPU memory exhaustion via Simulator, verify Brain detects and responds."""

    # 1. Reset simulator
    reset_resp = simulator_client.post("/simulator/reset")
    assert reset_resp.status_code == 200

    # 2. Trigger failure
    trigger_resp = simulator_client.post(
        "/simulator/trigger/gpu_memory_exhaustion"
    )
    assert trigger_resp.status_code == 200

    # 3. Poll Brain — Sentry → Pathologist → Quartermaster chain.
    # Mock the Hands call so we test only Brain logic in-process. Pathologist
    # now calls out to the simulator (review #10) for job/log context — proxy
    # those GETs to the in-process simulator_client instead of hitting the
    # real network (config.simulator_url resolves to a compose-only hostname
    # in tests, which would otherwise hang on DNS for every run).
    async def _proxy_get_to_simulator(url, params=None, **kwargs):
        path = "/" + url.split("/", 3)[-1]  # strip scheme+host, keep /simulator/...
        resp = simulator_client.get(path, params=params)
        return MagicMock(status_code=resp.status_code, json=resp.json, raise_for_status=MagicMock())

    with (
        patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            return_value=MagicMock(
                status_code=200,
                json=lambda: mock_hands_response,
                raise_for_status=MagicMock(),
            ),
        ),
        patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=_proxy_get_to_simulator),
    ):
        brain_resp = brain_client.get("/sentry/poll")

    assert brain_resp.status_code == 200
    brain_data = brain_resp.json()

    # Verify the chain reached remediation_sent
    assert brain_data["status"] == "remediation_sent", (
        f"Expected remediation_sent, got {brain_data}"
    )

    # Verify Hands result structure
    result = brain_data["result"]
    assert result["status"] == "complete"
    assert "trace_id" in result
    assert result["surgeon_result"]["status"] == "success"

    # 4. Health endpoints still work
    health_resp = brain_client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
