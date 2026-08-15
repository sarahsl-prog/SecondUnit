import httpx

from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.logger import get_logger
from shared.types import AnomalyReport, Diagnosis

# Deterministic fallback used only when the simulator is unreachable or has
# no matching failed job for the affected nodes — e.g. an anomaly reported
# by a real Grafana backend that didn't originate from /simulator/trigger.
_DEFAULT_FRAMES = [1847, 1848]
_DEFAULT_SCENE = "scene_47"


class PathologistAgent:
    """Diagnoses root cause by correlating metrics, logs, and traces."""

    def __init__(self, grafana: GrafanaMCPClient, trace_id: str = "", simulator_url: str = "http://simulator:8080"):
        self.grafana = grafana
        self.trace_id = trace_id
        self.simulator_url = simulator_url.rstrip("/")
        self.logger = get_logger(trace_id=trace_id, agent_name="Pathologist")

    async def run(self, anomaly: AnomalyReport) -> Diagnosis:
        self.logger.info(
            "pathologist_start",
            anomaly_type=anomaly.anomaly_type,
            affected_nodes=anomaly.affected_nodes,
        )

        logs = await self._query_logs(anomaly.affected_nodes)
        failure_type = self._classify_from_logs(logs)
        affected_frames, scene = await self._lookup_job_context(anomaly.affected_nodes)

        diagnosis = Diagnosis(
            failure_type=failure_type,
            affected_nodes=anomaly.affected_nodes,
            affected_frames=affected_frames,
            scene=scene,
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
        """Query the simulator's per-node error_log for the affected nodes.
        Stands in for a real Loki query until review #19 wires LogEmitter
        to an actual log backend."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.simulator_url}/simulator/status")
                resp.raise_for_status()
                node_states = resp.json().get("nodes", {})
        except httpx.HTTPError as e:
            self.logger.warning("simulator_status_query_failed", error=str(e))
            return "No errors found"

        for node_id in nodes:
            error_log = node_states.get(node_id, {}).get("error_log")
            if error_log:
                return error_log
        return "No errors found"

    async def _lookup_job_context(self, nodes: list) -> tuple[list[int], str]:
        """Derive affected_frames/scene from the simulator's actual job
        state instead of hardcoding [1847, 1848] / scene_47 for every
        diagnosis regardless of the input anomaly."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{self.simulator_url}/simulator/jobs", params={"status": "failed"}
                )
                resp.raise_for_status()
                jobs = resp.json().get("jobs", [])
        except httpx.HTTPError as e:
            self.logger.warning("simulator_jobs_query_failed", error=str(e))
            jobs = []

        matching = [j for j in jobs if j.get("assigned_node") in nodes]
        if matching:
            frames = sorted(j["frame"] for j in matching)
            scene = matching[0]["scene"]
            return frames, scene

        return list(_DEFAULT_FRAMES), _DEFAULT_SCENE

    def _classify_from_logs(self, logs: str) -> str:
        log_lower = logs.lower()
        if "cuda" in log_lower or "out of memory" in log_lower:
            return "gpu_memory_exhaustion"
        elif "malformed" in log_lower or "corrupt" in log_lower:
            return "corrupt_scene_file"
        elif "timeout" in log_lower or "timed out" in log_lower:
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
