import time

import httpx

from shared.logger import get_logger

logger = get_logger(agent_name="LogEmitter")


class LogEmitter:
    """Pushes node error logs to Loki (review #19 — previously a no-op
    stub, and never instantiated anywhere in the codebase).

    NOT verified against a live Loki/Grafana Cloud instance — this uses
    Loki's standard push API shape
    (POST {grafana_url}/loki/api/v1/push with a "streams" payload).
    No-ops when grafana_url is unset, matching the previous stub
    behavior for local/demo runs without a live Grafana stack.
    """

    def __init__(self, grafana_url: str = "", api_key: str = ""):
        self.grafana_url = grafana_url.rstrip("/") if grafana_url else ""
        self.api_key = api_key

    async def emit_log(self, node_id: str, message: str, level: str = "error") -> None:
        """Push a log line to Loki. Stub (no-op) when grafana_url is unset."""
        if not self.grafana_url:
            return

        payload = {
            "streams": [
                {
                    "stream": {
                        "node_id": node_id,
                        "level": level,
                        "service": "secondunit-simulator",
                    },
                    "values": [[str(time.time_ns()), message]],
                }
            ]
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{self.grafana_url}/loki/api/v1/push", json=payload, headers=headers
                )
                resp.raise_for_status()
        except httpx.HTTPError as e:
            # Log push failing must never break the simulator's own
            # failure-injection flow — just note it and move on.
            logger.error("loki_push_failed", node_id=node_id, error=str(e))
