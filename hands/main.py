"""Hands service."""
from fastapi import FastAPI

from hands.agents.dispatcher import DispatcherAgent
from hands.agents.surgeon import SurgeonAgent
from hands.routers import health, opencue
from hands.tools.gcp_api import GCPComputeClient
from shared.config import Config
from shared.logger import get_logger
from shared.types import RemediationRequest

app = FastAPI(title="SecondUnit Hands")
app.include_router(opencue.router)
app.include_router(health.router)

config = Config()
logger = get_logger(agent_name="Hands")


@app.post("/remediate")
async def remediate(remediation: RemediationRequest):
    """Entry point from Brain service."""
    logger.info("remediation_received", trace_id=remediation.trace_id)

    gcp = GCPComputeClient(
        project_id=config.gcp_project_id,
        zone=config.gcp_zone,
        dry_run=not config.enable_real_gcp_actions,
    )
    surgeon = SurgeonAgent(
        trace_id=remediation.trace_id,
        gcp=gcp,
    )
    result = await surgeon.execute(remediation)

    # Dispatcher
    dispatcher = DispatcherAgent(
        trace_id=remediation.trace_id,
        slack_url=config.slack_webhook_url,
        grafana_url=config.grafana_url,
        grafana_key=config.grafana_api_key,
    )
    affected_frames = remediation.diagnosis.affected_frames
    dispatch_result = await dispatcher.notify({
        "failure_type": remediation.diagnosis.failure_type,
        "scene": remediation.diagnosis.scene,
        "frame": affected_frames[0] if affected_frames else None,
        "actions": [a["action"] for a in result["actions_taken"]],
    })

    return {
        "status": "complete",
        "trace_id": remediation.trace_id,
        "surgeon_result": result,
        "dispatch_result": dispatch_result,
    }
