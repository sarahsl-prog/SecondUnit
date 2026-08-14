from typing import Optional
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.types import AnomalyReport
from shared.logger import get_logger
import random

class SentryAgent:
    """Detects anomalies by polling Grafana Cloud metrics."""
    
    def __init__(self, grafana: GrafanaMCPClient, trace_id: str = ""):
        self.grafana = grafana
        self.trace_id = trace_id or f"txn-{random.randint(100000, 999999)}"
        self.logger = get_logger(trace_id=self.trace_id, agent_name="Sentry")
        
    async def run(self) -> AnomalyReport:
        self.logger.info("sentry_polling_start")
        
        # Query queue depth metric
        metrics = await self.grafana.query_metrics(
            "render_queue_depth{job=\"render_farm\"}"
        )
        
        # Parse result (simplified for demo)
        result = metrics.get("data", {}).get("result", [])
        max_value = 0.0
        affected = []
        
        for item in result:
            val = float(item.get("value", [0, "0"])[1])
            if val > max_value:
                max_value = val
                affected = [item.get("metric", {}).get("node", "unknown")]
                
        # Threshold check
        threshold = 80.0
        if max_value > threshold:
            report = AnomalyReport(
                anomaly_detected=True,
                anomaly_type="queue_depth_spike",
                severity="high",
                affected_nodes=affected,
                grafana_context={
                    "metric": "render_queue_depth",
                    "value": max_value,
                    "threshold": threshold,
                }
            )
            self.logger.info(
                "anomaly_detected",
                anomaly_type=report.anomaly_type,
                value=max_value,
            )
            return report
            
        self.logger.info("no_anomaly_detected")
        return AnomalyReport(
            anomaly_detected=False,
            anomaly_type="none",
            severity="low",
            affected_nodes=[],
        )
