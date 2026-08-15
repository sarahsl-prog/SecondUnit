"""Tests for brain/main.py: /sentry/poll auth, idempotency, error handling."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

import brain.main as brain_main
from brain.main import app, reset_dedup_cache


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    reset_dedup_cache()
    # Quartermaster's nightly-spend file lives at a fixed path by default
    # (survives across requests, on purpose — see review #6). Point it at
    # a per-test tmp_path so tests don't share cumulative spend/instance
    # counts with each other or with a real /tmp file from prior runs.
    monkeypatch.setattr(brain_main.config, "budget_state_path", str(tmp_path / "budget.json"))
    yield
    reset_dedup_cache()


@pytest.fixture(autouse=True)
def _mock_simulator_get():
    """Pathologist (review #10) calls out to config.simulator_url for job/
    log context, which defaults to a compose-only hostname that hangs on
    DNS in tests. Stub it with no data — these tests only care about
    /sentry/poll's own auth/idempotency/error-handling behavior, not
    Pathologist's classification, so an empty simulator is fine."""
    async def fake_get(url, params=None, **kwargs):
        if url.endswith("/simulator/status"):
            payload = {"nodes": {}}
        elif url.endswith("/simulator/jobs"):
            payload = {"jobs": []}
        else:
            payload = {}
        return MagicMock(status_code=200, json=lambda: payload, raise_for_status=MagicMock())

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=fake_get):
        yield


@pytest.fixture
def client():
    return TestClient(app)


def _poll(client, headers=None):
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"status": "complete"},
            raise_for_status=MagicMock(),
        ),
    ):
        return client.get("/sentry/poll", headers=headers or {})


def test_poll_unauthorized_when_token_configured(client, monkeypatch):
    monkeypatch.setattr(brain_main.config, "scheduler_token", "s3cr3t")
    resp = client.get("/sentry/poll")
    assert resp.status_code == 401


def test_poll_authorized_with_matching_token(client, monkeypatch):
    monkeypatch.setattr(brain_main.config, "scheduler_token", "s3cr3t")
    resp = _poll(client, headers={"x-scheduler-token": "s3cr3t"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "remediation_sent"


def test_poll_open_when_no_token_configured(client):
    """Local/demo runs without SCHEDULER_TOKEN stay unauthenticated."""
    resp = _poll(client)
    assert resp.status_code == 200


def test_poll_dedupes_repeat_anomaly_within_cooldown(client):
    first = _poll(client)
    assert first.json()["status"] == "remediation_sent"

    second = _poll(client)
    assert second.status_code == 200
    assert second.json()["status"] == "deduped"


def test_poll_returns_structured_error_on_hands_failure(client):
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("boom"),
    ):
        resp = client.get("/sentry/poll")

    assert resp.status_code == 502
    body = resp.json()
    assert body["status"] == "error"
    assert "boom" in body["error"]
