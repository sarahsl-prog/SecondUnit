# hands/tests/test_dispatcher.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hands.agents.dispatcher import DispatcherAgent


@pytest.mark.asyncio
async def test_dispatcher_sends_notification():
    mock_response = AsyncMock()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock()

    with patch("hands.agents.dispatcher.httpx.AsyncClient", return_value=mock_client):
        agent = DispatcherAgent(trace_id="txn-test", slack_url="http://mock")
        result = await agent.notify({
            "failure_type": "gpu_memory_exhaustion",
            "scene": "scene_47",
            "frame": 1847,
            "actions": ["reroute_job", "spin_up_preemptible"],
        })

    assert result["notification_sent"] is True
    assert "slack" in result["channels"]
    assert result["slack_message_ts"] == "mock-ts"


@pytest.mark.asyncio
async def test_dispatcher_skips_slack_when_no_url():
    agent = DispatcherAgent(trace_id="txn-test", slack_url="")
    result = await agent.notify({
        "failure_type": "gpu_memory_exhaustion",
        "scene": "scene_47",
        "frame": 1847,
        "actions": ["reroute_job"],
    })
    assert result["notification_sent"] is False
    assert result["channels"] == []


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
