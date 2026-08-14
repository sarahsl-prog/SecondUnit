from typing import Optional
from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.types import AnomalyReport, Diagnosis
from shared.logger import get_logger
import random

class PathologistAgent:
    """Diagnoses root cause by correlating metrics, logs, and traces."""
    
    def __init__(self, grafana: GrafanaMCPClient, trace_id: str = ""):
        self.grafana = grafana
        self.trace_id = trace_id
        self.logger = get_logger(trace_id=trace_id, agent_name="Pathologist")
        
    async def run(self, anomaly: AnomalyReport) -> Diagnosis:
        self.logger.info(
            "pathologist_start",
            anomaly_type=anomaly.anomaly_type,
            affected_nodes=anomaly.affected_nodes,
        )
        
        # Query logs for affected nodes
        logs = await self._query_logs(anomaly.affected_nodes)
        
        # Simple keyword-based classification (deterministic for demo)
        failure_type = self._classify_from_logs(logs)
        
        diagnosis = Diagnosis(
            failure_type=failure_type,
            affected_nodes=anomaly.affected_nodes,
            affected_frames=[1847, 1848],  # Demo hardcoded
            scene="scene_47",
            recommended_action=self._get_recommended_action(failure_type),
            confidence=0.94 if failure_type != "unknown" else 0.5,
            reasoning=f"Detected {failure_type} from logs: {logs[:100]}...",
        )
        
        self.logger.info(
            "diagnosis_complete",
            failure_type=diagnosis.failure_type,
            confidence=diagnosis.confidence,
        )
        return diagnosis
        
    async def _query_logs(self, nodes: list) -> str:
        """Query Loki logs for affected nodes."""
        # Stub: return realistic error messages based on node
        if "node-7" in nodes:
            return "CUDA out of memory at frame 1847"
        return "No errors found"
        
    def _classify_from_logs(self, logs: str) -> str:
        log_lower = logs.lower()
        if "cuda" in log_lower or "out of memory" in log_lower:
            return "gpu_memory_exhaustion"
        elif "malformed" in log_lower or "corrupt" in log_lower:
            return "corrupt_scene_file"
        elif "timeout" in log_lower:
            return "network_timeout"
        elif "license" in log_lower:
            return "license_failure"
        return "unknown"
        
    def _get_recommended_action(self, failure_type: str) -> str:
        actions = {
            "gpu_memory_exhaustion": "reroute_to_healthy_nodes",
            "corrupt_scene_file": "flag_for_artist_skip_frame",
            "network_timeout": "check_storage_connectivity",
            "license_failure": "check_license_server",
            "unknown": "escalate_to_human",
        }
        return actions.get(failure_type, "escalate_to_human")
