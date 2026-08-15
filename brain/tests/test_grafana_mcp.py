"""GrafanaMCPClient real-call vs mock-fallback behavior (review #18)."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from brain.tools.grafana_mcp import GrafanaMCPClient


@pytest.mark.asyncio
async def test_query_metrics_uses_mock_when_url_unset():
    client = GrafanaMCPClient(url="", api_key="")
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        result = await client.query_metrics('node_gpu_mem_percent{job="render_farm"}')

    mock_get.assert_not_called()
    assert result["status"] == "success"
    assert result["data"]["result"][0]["metric"]["node"] == "node-7"


@pytest.mark.asyncio
async def test_query_metrics_makes_real_call_when_url_configured():
    real_response = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"node": "node-12"}, "value": [1700000000, "42.0"]}],
        },
    }
    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200, json=lambda: real_response, raise_for_status=MagicMock()
        ),
    ) as mock_get:
        client = GrafanaMCPClient(url="https://my-stack.grafana.net", api_key="secret")
        result = await client.query_metrics('render_queue_depth{job="render_farm"}')

    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"] == {"query": 'render_queue_depth{job="render_farm"}'}
    assert call_kwargs["headers"] == {"Authorization": "Bearer secret"}
    assert mock_get.call_args.args[0] == "https://my-stack.grafana.net/api/v1/query"
    assert result == real_response


@pytest.mark.asyncio
async def test_query_metrics_degrades_safely_on_http_error():
    """A real-call failure must never crash SentryAgent's poll loop —
    degrade to an empty result, which reads as "no anomaly"."""
    with patch(
        "httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("down")
    ):
        client = GrafanaMCPClient(url="https://my-stack.grafana.net", api_key="secret")
        result = await client.query_metrics("some_query")

    assert result["data"]["result"] == []


@pytest.mark.asyncio
async def test_get_dashboard_uses_mock_when_url_unset():
    client = GrafanaMCPClient(url="", api_key="")
    result = await client.get_dashboard("render-farm-health")
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_get_dashboard_makes_real_call_when_url_configured():
    real_response = {"dashboard": {"title": "Real Dashboard"}, "status": "success"}
    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200, json=lambda: real_response, raise_for_status=MagicMock()
        ),
    ) as mock_get:
        client = GrafanaMCPClient(url="https://my-stack.grafana.net", api_key="secret")
        result = await client.get_dashboard("abc123")

    assert mock_get.call_args.args[0] == "https://my-stack.grafana.net/api/dashboards/uid/abc123"
    assert result == real_response


@pytest.mark.asyncio
async def test_list_incidents_uses_mock_when_url_unset():
    client = GrafanaMCPClient(url="", api_key="")
    assert await client.list_incidents() == []


@pytest.mark.asyncio
async def test_list_incidents_makes_real_call_when_url_configured():
    real_response = [{"id": "ann-1", "text": "GPU spike"}]
    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=MagicMock(
            status_code=200, json=lambda: real_response, raise_for_status=MagicMock()
        ),
    ):
        client = GrafanaMCPClient(url="https://my-stack.grafana.net", api_key="secret")
        result = await client.list_incidents()

    assert result == real_response
