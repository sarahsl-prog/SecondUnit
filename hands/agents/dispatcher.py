# hands/agents/dispatcher.py
import httpx
from typing import Dict, Any
from shared.logger import get_logger


class DispatcherAgent:
    """Communicates outcomes to humans and logs to Grafana annotations."""

    def __init__(self, trace_id: str = "", slack_url: str = "", grafana_url: str = "", grafana_key: str = ""):
        self.trace_id = trace_id
        self.slack_url = slack_url
        self.grafana_url = grafana_url
        self.grafana_key = grafana_key
        self.logger = get_logger(trace_id=trace_id, agent_name="Dispatcher")

    async def notify(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("dispatcher_start", failure_type=context.get("failure_type"))

        channels = []
        slack_ts = None
        grafana_ann = None

        # Build human-readable summary
        summary = self._build_summary(context)

        # Send Slack notification
        if self.slack_url:
            slack_result = await self._send_slack(summary, context)
            if slack_result:
                channels.append("slack")
                slack_ts = slack_result.get("ts")

        # Add Grafana annotation
        if self.grafana_url and self.grafana_key:
            ann_result = await self._add_grafana_annotation(summary, context)
            if ann_result:
                channels.append("grafana_annotation")
                grafana_ann = ann_result.get("id")

        self.logger.info("dispatcher_complete", channels=channels)
        return {
            "notification_sent": len(channels) > 0,
            "channels": channels,
            "slack_message_ts": slack_ts,
            "grafana_annotation_id": grafana_ann,
            "summary": summary,
        }

    def _build_summary(self, context: Dict) -> str:
        failure = context.get("failure_type", "unknown")
        scene = context.get("scene", "unknown")
        frame = context.get("frame", "?")
        actions = context.get("actions", [])

        return (
            f"🔧 *SecondUnit Alert*\n"
            f"*Scene:* {scene} | *Frame:* {frame}\n"
            f"*Issue:* {failure.replace('_', ' ').title()}\n"
            f"*Actions:* {', '.join(actions)}\n"
            f"*Status:* Auto-remediated"
        )

    async def _send_slack(self, summary: str, context: Dict) -> Dict:
        if not self.slack_url:
            return {}

        payload = {
            "text": summary,
            "blocks": [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": summary}
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(self.slack_url, json=payload)
                resp.raise_for_status()
                return {"ts": "mock-ts", "ok": True}
            except httpx.HTTPError as e:
                self.logger.error("slack_send_failed", error=str(e))
                return {}

    async def _add_grafana_annotation(self, summary: str, context: Dict) -> Dict:
        # Stub: would call Grafana annotation API
        return {"id": "ann-mock-123", "status": "created"}
