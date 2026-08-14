"""Brain service."""
from fastapi import FastAPI
from brain.agents.sentry import SentryAgent
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
        # Trigger Pathologist (next task)
        return {"status": "anomaly_detected", "report": report.model_dump()}
    return {"status": "healthy"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "brain"}
