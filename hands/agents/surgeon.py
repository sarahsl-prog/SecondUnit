import httpx
from typing import Dict, List
from shared.types import RemediationRequest
from shared.logger import get_logger
from hands.tools.gcp_api import GCPComputeClient


class SurgeonAgent:
    """Executes approved remediation actions."""

    ACTION_MAP = {
        "gpu_memory_exhaustion": ["reroute_job", "spin_up_preemptible"],
        "corrupt_scene_file": ["flag_for_artist", "skip_frame"],
        "network_timeout": ["check_storage_connectivity"],
        "license_failure": ["check_license_server"],
        "unknown": ["escalate_to_human"],
    }

    def __init__(self, trace_id: str = "", gcp: GCPComputeClient = None, opencue_url: str = ""):
        self.trace_id = trace_id
        self.gcp = gcp
        self.opencue_url = opencue_url or "http://localhost:8083"
        self.logger = get_logger(trace_id=trace_id, agent_name="Surgeon")

    async def execute(self, request: RemediationRequest) -> Dict:
        self.logger.info(
            "surgeon_executing",
            failure_type=request.diagnosis.failure_type,
            action=request.diagnosis.recommended_action,
        )

        actions = self.ACTION_MAP.get(request.diagnosis.failure_type, ["escalate_to_human"])
        actions_taken = []
        gcp_resources = []

        for action in actions:
            result = await self._execute_action(action, request)
            actions_taken.append(result)
            if result.get("gcp_resource"):
                gcp_resources.append(result["gcp_resource"])

        self.logger.info("surgeon_complete", actions_count=len(actions_taken))
        return {
            "trace_id": self.trace_id,
            "status": "success",
            "actions_taken": actions_taken,
            "gcp_resources_created": gcp_resources,
        }

    async def _execute_action(self, action: str, request: RemediationRequest) -> Dict:
        if action == "reroute_job":
            return await self._call_opencue("reroute", {
                "job_id": f"job-{request.diagnosis.affected_frames[0]}",
                "target_node": "node-3",  # Demo: reroute to healthy node
            }, caller_action=action)
        elif action == "spin_up_preemptible":
            if self.gcp:
                instances = await self.gcp.start_preemptible_instances(
                    count=2, machine_type="n1-standard-4"
                )
                return {
                    "action": "spin_up_preemptible",
                    "count": 2,
                    "instances": instances,
                    "gcp_resource": instances[0],
                }
            return {"action": "spin_up_preemptible", "status": "skipped_no_gcp"}
        elif action == "flag_for_artist":
            return {"action": "flag_for_artist", "status": "flagged"}
        elif action == "skip_frame":
            return {"action": "skip_frame", "status": "skipped"}
        elif action == "escalate_to_human":
            return {"action": "escalate_to_human", "status": "escalated"}
        return {"action": action, "status": "unknown"}

    async def _call_opencue(self, endpoint: str, payload: dict, caller_action: str = "") -> dict:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(f"{self.opencue_url}/opencue/{endpoint}", json=payload)
                resp.raise_for_status()
                result = resp.json()
                result["action"] = caller_action or endpoint
                return result
            except httpx.HTTPError as e:
                self.logger.error("opencue_call_failed", endpoint=endpoint, error=str(e))
                return {"action": caller_action, "status": "failed", "error": str(e)}
