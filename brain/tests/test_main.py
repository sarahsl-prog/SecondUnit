"""Tests for brain/main.py: /sentry/poll auth, idempotency, error handling."""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

import brain.main as brain_main
from brain.main import app, reset_dedup_cache


@pytest.fixture(autouse=True)
def _reset_state():
    reset_dedup_cache()
    yield
    reset_dedup_cache()


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
    """Local/demo runs without SECONDUNIT_SCHEDULER_TOKEN stay unauthenticated."""
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
