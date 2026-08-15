from typing import Any

import httpx

from shared.logger import get_logger

logger = get_logger(agent_name="GrafanaMCPClient")


class GrafanaMCPClient:
    """Wrapper for Grafana Cloud MCP tools.

    When `url` is configured, makes real HTTP calls against a
    Prometheus-compatible query API (review #18 — this used to always
    return static mock data regardless of the query, url, or api_key).
    When `url` is unset (the local/demo default — see .env.example),
    falls back to the previous static mock so the documented
    quick-start keeps working without a live Grafana stack.

    NOT verified against a live Grafana Cloud instance — this assumes
    `{url}/api/v1/query` is a Prometheus-compatible query endpoint,
    matching Grafana Cloud's hosted-Prometheus URL shape. Validate that
    against your actual stack before demo day; if the shape is wrong,
    every call degrades to the same safe "no anomaly" response
    SentryAgent already handles rather than raising, so a mismatch
    fails closed instead of crashing the poll loop.
    """

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/") if url else ""
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    async def query_metrics(self, query: str, time_range: str = "5m") -> dict[str, Any]:
        """Query Prometheus-compatible metrics via Grafana."""
        if not self.url:
            return self._mock_query_response()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api/v1/query", params={"query": query}, headers=self._headers()
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error("grafana_query_failed", query=query, error=str(e))
            return self._empty_query_response()
        except ValueError as e:
            logger.error("grafana_query_bad_response", query=query, error=str(e))
            return self._empty_query_response()

    @staticmethod
    def _mock_query_response() -> dict[str, Any]:
        """Static demo data — kept from before #18 so local dev without
        GRAFANA_URL configured still works."""
        return {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"node": "node-7"}, "value": [1692000000, "98.5"]}
                ]
            }
        }

    @staticmethod
    def _empty_query_response() -> dict[str, Any]:
        """Safe degraded response on a real-call failure — an empty
        result reads as "no anomaly" to SentryAgent, not a crash."""
        return {"status": "error", "data": {"resultType": "vector", "result": []}}

    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        if not self.url:
            return {"dashboard": {"title": "Render Farm Health"}, "status": "success"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.url}/api/dashboards/uid/{uid}", headers=self._headers()
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            logger.error("grafana_dashboard_fetch_failed", uid=uid, error=str(e))
            return {"dashboard": None, "status": "error"}
        except ValueError as e:
            logger.error("grafana_dashboard_bad_response", uid=uid, error=str(e))
            return {"dashboard": None, "status": "error"}

    async def list_incidents(self) -> list:
        if not self.url:
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.url}/api/annotations", headers=self._headers())
                resp.raise_for_status()
                result = resp.json()
                return result if isinstance(result, list) else []
        except httpx.HTTPError as e:
            logger.error("grafana_incidents_fetch_failed", error=str(e))
            return []
        except ValueError as e:
            logger.error("grafana_incidents_bad_response", error=str(e))
            return []
