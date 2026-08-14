"""Brain service."""
from fastapi import FastAPI
from brain.agents.sentry import SentryAgent
from brain.agents.pathologist import PathologistAgent
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.config import Config
from shared.logger import get_logger

app = FastAPI(title="SecondUnit Brain")
config = Config()
logger = get_logger(agent_name="Brain")

@app.get("/sentry/poll")
async def sentry_poll():
    grafana = GrafanaMCPClient(url=config.grafana_url, api_key=config.grafana_api_key)
    sentry = SentryAgent(grafana=grafana)
    report = await sentry.run()
    
    if report.anomaly_detected:
        pathologist = PathologistAgent(grafana=grafana, trace_id=sentry.trace_id)
        diagnosis = await pathologist.run(report)
        return {
            "status": "diagnosis_complete",
            "diagnosis": diagnosis.model_dump(),
            "trace_id": sentry.trace_id,
        }
    return {"status": "healthy"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "brain"}
