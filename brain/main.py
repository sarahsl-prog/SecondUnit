"""Brain service."""
from fastapi import FastAPI
from brain.agents.sentry import SentryAgent
from brain.agents.pathologist import PathologistAgent
from brain.agents.quartermaster import QuartermasterAgent
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.config import Config
from shared.logger import get_logger
from shared.types import RemediationRequest, CostEstimate

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
        
        quartermaster = QuartermasterAgent(
            trace_id=sentry.trace_id,
            hands_url=config.hands_service_url,
        )
        decision = await quartermaster.evaluate(diagnosis)
        
        if decision["decision"] == "approve":
            remediation = RemediationRequest(
                trace_id=sentry.trace_id,
                diagnosis=diagnosis,
                cost_estimate=CostEstimate(**decision["cost_estimate"]),
                approval=decision["approval"],
            )
            result = await quartermaster.send_to_hands(remediation.model_dump())
            return {"status": "remediation_sent", "result": result}
        else:
            return {"status": "escalated", "reason": decision["reason"]}
            
    return {"status": "healthy"}

@app.get("/health")
def health():
    return {"status": "ok", "service": "brain"}
