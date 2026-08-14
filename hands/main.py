"""Hands service."""
from fastapi import FastAPI
from hands.routers import opencue, health
from shared.config import Config
from shared.logger import get_logger

app = FastAPI(title="SecondUnit Hands")
app.include_router(opencue.router)
app.include_router(health.router)

config = Config()
logger = get_logger(agent_name="Hands")


@app.post("/remediate")
async def remediate(request: dict):
    """Entry point from Brain service."""
    logger.info("remediation_received", trace_id=request.get("trace_id"))
    # Surgeon and Dispatcher will handle this in next tasks
    return {"status": "received", "trace_id": request.get("trace_id")}
