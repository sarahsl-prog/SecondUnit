"""LogEmitter real Loki push vs no-op fallback (review #19)."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from simulator.logs import LogEmitter


@pytest.mark.asyncio
async def test_emit_log_noop_when_grafana_url_unset():
    emitter = LogEmitter(grafana_url="")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        await emitter.emit_log("node-7", "CUDA out of memory")

    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_emit_log_pushes_to_loki_when_configured():
    with patch(
        "httpx.AsyncClient.post",
        new_callable=AsyncMock,
        return_value=MagicMock(status_code=204, raise_for_status=MagicMock()),
    ) as mock_post:
        emitter = LogEmitter(grafana_url="https://my-stack.grafana.net", api_key="secret")
        await emitter.emit_log("node-7", "CUDA out of memory", level="error")

    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://my-stack.grafana.net/loki/api/v1/push"
    payload = mock_post.call_args.kwargs["json"]
    stream = payload["streams"][0]
    assert stream["stream"] == {
        "node_id": "node-7",
        "level": "error",
        "service": "secondunit-simulator",
    }
    assert stream["values"][0][1] == "CUDA out of memory"
    assert mock_post.call_args.kwargs["headers"] == {"Authorization": "Bearer secret"}


@pytest.mark.asyncio
async def test_emit_log_swallows_push_failure():
    """A Loki outage must never break the simulator's failure-injection
    flow — emit_log logs and returns, doesn't raise."""
    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    ):
        emitter = LogEmitter(grafana_url="https://my-stack.grafana.net", api_key="secret")
        await emitter.emit_log("node-7", "CUDA out of memory")  # must not raise
