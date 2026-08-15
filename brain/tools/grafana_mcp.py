from typing import Any

import httpx


class GrafanaMCPClient:
    """Wrapper for Grafana Cloud MCP tools."""
    
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )
        
    async def query_metrics(self, query: str, time_range: str = "5m") -> dict[str, Any]:
        """Query Prometheus metrics via Grafana."""
        # Stub: returns mock data for local dev
        return {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": {"node": "node-7"}, "value": [1692000000, "98.5"]}
                ]
            }
        }
        
    async def get_dashboard(self, uid: str) -> dict[str, Any]:
        return {"dashboard": {"title": "Render Farm Health"}, "status": "success"}
        
    async def list_incidents(self) -> list:
        return []
