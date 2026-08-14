"""Hands service."""
from fastapi import FastAPI
from hands.routers import opencue, health
from shared.config import Config
from shared.logger import get_logger
from hands.agents.surgeon import SurgeonAgent
from hands.tools.gcp_api import GCPComputeClient
from shared.types import RemediationRequest

app = FastAPI(title="SecondUnit Hands")
app.include_router(opencue.router)
app.include_router(health.router)

config = Config()
logger = get_logger(agent_name="Hands")


@app.post("/remediate")
async def remediate(request: dict):
    """Entry point from Brain service."""
    logger.info("remediation_received", trace_id=request.get("trace_id"))

    remediation = RemediationRequest(**request)
    gcp = GCPComputeClient(
        project_id=config.gcp_project_id,
        zone=config.gcp_zone,
    )
    surgeon = SurgeonAgent(
        trace_id=remediation.trace_id,
        gcp=gcp,
    )
    result = await surgeon.execute(remediation)

    # Pass to Dispatcher (next task)
    return {"status": "surgeon_complete", "result": result}
