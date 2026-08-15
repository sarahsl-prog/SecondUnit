# hands/agents/dispatcher.py
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from shared.logger import get_logger

# Guaranteed local fallback surface (outstanding-decision #10) for when
# Slack and Grafana are both unconfigured or both fail — a remediation
# must never go completely unnotified. Cloud Run's /tmp is ephemeral, but
# combined with the ERROR-severity log line (which Cloud Logging always
# captures from stdout/stderr regardless of this file), an operator has
# at least one guaranteed way to see it.
DEFAULT_FALLBACK_PATH = Path("/tmp/secondunit-unnotified-incidents.jsonl")


class DispatcherAgent:
    """Communicates outcomes to humans and logs to Grafana annotations."""

    def __init__(
        self,
        trace_id: str = "",
        slack_url: str = "",
        grafana_url: str = "",
        grafana_key: str = "",
        fallback_path: Path | str | None = None,
    ):
        self.trace_id = trace_id
        self.slack_url = slack_url
        self.grafana_url = grafana_url
        self.grafana_key = grafana_key
        self.fallback_path = Path(fallback_path) if fallback_path else DEFAULT_FALLBACK_PATH
        self.logger = get_logger(trace_id=trace_id, agent_name="Dispatcher")

    async def notify(self, context: dict[str, Any]) -> dict[str, Any]:
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

        if not channels:
            # Neither channel is configured, or both attempts failed — a
            # remediation must never go completely unnotified (review's
            # outstanding-decision #10, stronger than just logging a
            # warning). Log at ERROR (always visible in Cloud Logging) and
            # append to a local fallback file an operator can check.
            self._write_unnotified_fallback(context, summary)

        self.logger.info("dispatcher_complete", channels=channels)
        return {
            "notification_sent": len(channels) > 0,
            "channels": channels,
            "slack_message_ts": slack_ts,
            "grafana_annotation_id": grafana_ann,
            "summary": summary,
        }

    def _write_unnotified_fallback(self, context: dict, summary: str) -> None:
        self.logger.error(
            "remediation_unnotified",
            trace_id=self.trace_id,
            failure_type=context.get("failure_type"),
        )
        record = {
            "trace_id": self.trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "context": context,
            "summary": summary,
        }
        try:
            self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
            with self.fallback_path.open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError as e:
            self.logger.error("unnotified_fallback_write_failed", error=str(e))

    def _build_summary(self, context: dict) -> str:
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

    async def _send_slack(self, summary: str, context: dict) -> dict:
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
            except httpx.HTTPError as e:
                self.logger.error("slack_send_failed", error=str(e))
                return {}

        try:
            body = resp.json()
        except ValueError:
            # Slack Incoming Webhooks (the SLACK_WEBHOOK_URL shape used
            # here) return the plain text "ok", not JSON — a message
            # timestamp is only available from the chat.postMessage Web
            # API, which needs a bot token rather than a webhook URL. The
            # message still sent successfully; there's just no ts to
            # report back.
            body = {}

        return {"ok": True, "ts": body.get("ts")}

    async def _add_grafana_annotation(self, summary: str, context: dict) -> dict:
        # Stub: would call Grafana annotation API
        return {"id": "ann-mock-123", "status": "created"}
