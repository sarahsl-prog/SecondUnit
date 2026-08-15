# hands/tests/test_dispatcher.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hands.agents.dispatcher import DispatcherAgent


@pytest.mark.asyncio
async def test_dispatcher_propagates_real_slack_response_ts():
    """review #24: _send_slack used to hardcode {"ts": "mock-ts"} regardless
    of what Slack actually returned — this asserts the real parsed
    response is used instead."""
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200,
            json=lambda: {"ok": True, "ts": "1755261234.000200"},
            raise_for_status=MagicMock(),
        ),
    ):
        agent = DispatcherAgent(trace_id="txn-test", slack_url="http://mock")
        result = await agent.notify({
            "failure_type": "gpu_memory_exhaustion",
            "scene": "scene_47",
            "frame": 1847,
            "actions": ["reroute_job", "spin_up_preemptible"],
        })

    assert result["notification_sent"] is True
    assert "slack" in result["channels"]
    assert result["slack_message_ts"] == "1755261234.000200"


@pytest.mark.asyncio
async def test_dispatcher_handles_non_json_webhook_response():
    """Real Slack Incoming Webhooks return the plain text "ok", not JSON —
    the message still sent, just with no ts available."""
    def _raise_value_error():
        raise ValueError("not JSON")

    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200,
            json=_raise_value_error,
            raise_for_status=MagicMock(),
        ),
    ):
        agent = DispatcherAgent(trace_id="txn-test", slack_url="http://mock")
        result = await agent.notify({
            "failure_type": "gpu_memory_exhaustion",
            "scene": "scene_47",
            "frame": 1847,
            "actions": ["reroute_job"],
        })

    assert result["notification_sent"] is True
    assert "slack" in result["channels"]
    assert result["slack_message_ts"] is None


@pytest.mark.asyncio
async def test_dispatcher_adds_grafana_annotation_when_configured():
    """review #25: no test previously exercised the Grafana-annotation
    channel at all."""
    agent = DispatcherAgent(
        trace_id="txn-test", grafana_url="https://grafana.test", grafana_key="key"
    )
    result = await agent.notify({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job"],
    })

    assert result["notification_sent"] is True
    assert "grafana_annotation" in result["channels"]
    assert result["grafana_annotation_id"] == "ann-mock-123"


@pytest.mark.asyncio
async def test_dispatcher_skips_grafana_annotation_when_not_configured(tmp_path):
    agent = DispatcherAgent(trace_id="txn-test", fallback_path=tmp_path / "fallback.jsonl")
    result = await agent.notify({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job"],
    })

    assert "grafana_annotation" not in result["channels"]
    assert result["grafana_annotation_id"] is None


@pytest.mark.asyncio
async def test_dispatcher_skips_slack_when_no_url(tmp_path):
    agent = DispatcherAgent(
        trace_id="txn-test", slack_url="", fallback_path=tmp_path / "fallback.jsonl"
    )
    result = await agent.notify({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job"],
    })
    assert result["notification_sent"] is False
    assert result["channels"] == []


@pytest.mark.asyncio
async def test_dispatcher_writes_fallback_when_no_channels_configured(tmp_path):
    """outstanding-decision #10: a remediation must never go completely
    unnotified — with no Slack/Grafana config, it must land somewhere an
    operator can find it."""
    fallback_path = tmp_path / "fallback.jsonl"
    agent = DispatcherAgent(trace_id="txn-test", fallback_path=fallback_path)
    result = await agent.notify({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job"],
    })

    assert result["notification_sent"] is False
    assert fallback_path.exists()
    record = json.loads(fallback_path.read_text().strip())
    assert record["trace_id"] == "txn-test"
    assert record["context"]["failure_type"] == "gpu_memory_exhaustion"


@pytest.mark.asyncio
async def test_dispatcher_does_not_write_fallback_when_a_channel_succeeds(tmp_path):
    fallback_path = tmp_path / "fallback.jsonl"
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200, json=lambda: {"ok": True}, raise_for_status=MagicMock()
        ),
    ):
        agent = DispatcherAgent(
            trace_id="txn-test", slack_url="http://mock", fallback_path=fallback_path
        )
        await agent.notify({
            "failure_type": "gpu_memory_exhaustion",
            "scene": "scene_47",
            "frame": 1847,
            "actions": ["reroute_job"],
        })

    assert not fallback_path.exists()


@pytest.mark.asyncio
async def test_dispatcher_builds_summary():
    agent = DispatcherAgent(trace_id="txn-test", slack_url="http://mock")
    summary = agent._build_summary({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job", "spin_up_preemptible"],
    })
    assert "scene_47" in summary
    assert "1847" in summary
    assert "gpu_memory_exhaustion".replace("_", " ").title() in summary
    assert "reroute_job" in summary
