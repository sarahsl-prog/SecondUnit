"""Brain service."""
import time

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from brain.agents.pathologist import PathologistAgent
from brain.agents.quartermaster import QuartermasterAgent
from brain.agents.sentry import SentryAgent
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.config import Config
from shared.logger import get_logger
from shared.types import AnomalyReport, CostEstimate, RemediationRequest

app = FastAPI(title="SecondUnit Brain")
config = Config()
logger = get_logger(agent_name="Brain")

# In-memory idempotency cache: dedup key -> last-fired monotonic timestamp.
# Single-instance demo scope only — does not survive restarts and is not
# shared across multiple Cloud Run instances.
_last_fired: dict[tuple[str, tuple[str, ...]], float] = {}


def reset_dedup_cache() -> None:
    """Test hook: clear the idempotency cache between test cases."""
    _last_fired.clear()


def _dedup_key(report: AnomalyReport) -> tuple[str, tuple[str, ...]]:
    return (report.anomaly_type, tuple(sorted(report.affected_nodes)))


def _is_duplicate(report: AnomalyReport) -> bool:
    last = _last_fired.get(_dedup_key(report))
    if last is None:
        return False
    return (time.monotonic() - last) < config.poll_cooldown_seconds


def _mark_fired(report: AnomalyReport) -> None:
    _last_fired[_dedup_key(report)] = time.monotonic()


async def _notify_hands_unreachable(trace_id: str, error: str) -> None:
    """Local Dispatcher fallback (design spec §3.3): if Hands is still
    unreachable after send_to_hands's retries, tell a human directly
    rather than failing silently. Minimal Slack-only implementation —
    Brain's container doesn't include hands/agents/dispatcher.py (each
    service is a separate Docker image, see Dockerfile.brain), so this
    can't reuse DispatcherAgent directly."""
    if not config.slack_webhook_url:
        logger.warning("hands_unreachable_no_notification_channel", trace_id=trace_id)
        return
    summary = (
        f"🚨 *SecondUnit Alert*\nHands service unreachable after retries.\n"
        f"*Trace:* {trace_id}\n*Error type:* hands_unreachable\n*Error:* {error}"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(config.slack_webhook_url, json={"text": summary})
            resp.raise_for_status()
    except httpx.HTTPError as slack_error:
        logger.error("hands_unreachable_fallback_notify_failed", error=str(slack_error))


@app.get("/sentry/poll")
async def sentry_poll(x_scheduler_token: str = Header(default="")):
    # Only enforced when a token is configured, so local/demo runs without
    # SCHEDULER_TOKEN set keep working unauthenticated.
    if config.scheduler_token and x_scheduler_token != config.scheduler_token:
        logger.warning("sentry_poll_unauthorized")
        raise HTTPException(status_code=401, detail="invalid or missing scheduler token")

    try:
        grafana = GrafanaMCPClient(url=config.grafana_url, api_key=config.grafana_api_key)
        sentry = SentryAgent(grafana=grafana)
        report = await sentry.run()

        if not report.anomaly_detected:
            return {"status": "healthy"}

        if _is_duplicate(report):
            logger.info("sentry_poll_deduped", anomaly_type=report.anomaly_type)
            return {"status": "deduped", "anomaly_type": report.anomaly_type}
        _mark_fired(report)

        pathologist = PathologistAgent(
            grafana=grafana, trace_id=sentry.trace_id, simulator_url=config.simulator_url
        )
        diagnosis = await pathologist.run(report)

        quartermaster = QuartermasterAgent(
            trace_id=sentry.trace_id,
            hands_url=config.hands_service_url,
            state_path=config.budget_state_path,
        )
        decision = await quartermaster.evaluate(diagnosis)

        if decision["decision"] == "approve":
            remediation = RemediationRequest(
                trace_id=sentry.trace_id,
                diagnosis=diagnosis,
                cost_estimate=CostEstimate(**decision["cost_estimate"]),
                approval=decision["approval"],
            )
            result = await quartermaster.send_to_hands(
                remediation.model_dump(mode='json'),
                backoff_base_seconds=config.hands_retry_backoff_seconds,
            )
            return {"status": "remediation_sent", "result": result}
        else:
            return {"status": "escalated", "reason": decision["reason"]}

    except httpx.HTTPError as e:
        logger.error("sentry_poll_hands_unreachable", error=str(e))
        await _notify_hands_unreachable(sentry.trace_id, str(e))
        return JSONResponse(
            status_code=502,
            content={"status": "error", "error": f"hands service unreachable: {e}"},
        )
    except Exception as e:
        logger.error("sentry_poll_failed", error=str(e))
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})

@app.get("/health")
def health():
    return {"status": "ok", "service": "brain"}
