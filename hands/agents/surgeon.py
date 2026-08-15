from typing import ClassVar

import httpx

from hands.tools.gcp_api import GCPComputeClient
from shared.logger import get_logger
from shared.types import RemediationRequest


class SurgeonAgent:
    """Executes approved remediation actions."""

    # Statuses on an individual action result that count as that action
    # having failed. "unknown" covers actions in ACTION_MAP with no
    # matching branch in _execute_action (defensive — shouldn't happen).
    FAILURE_STATUSES: ClassVar[set[str]] = {"failed", "unknown"}

    ACTION_MAP: ClassVar[dict[str, list[str]]] = {
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

    async def execute(self, request: RemediationRequest) -> dict:
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

        statuses = [a.get("status") for a in actions_taken]
        failed_count = sum(1 for s in statuses if s in self.FAILURE_STATUSES)
        if failed_count == 0:
            overall_status = "success"
        elif failed_count == len(statuses):
            overall_status = "failure"
        else:
            overall_status = "partial_failure"

        self.logger.info(
            "surgeon_complete", actions_count=len(actions_taken), status=overall_status
        )
        return {
            "trace_id": self.trace_id,
            "status": overall_status,
            "actions_taken": actions_taken,
            "gcp_resources_created": gcp_resources,
        }

    async def _execute_action(self, action: str, request: RemediationRequest) -> dict:
        if action == "reroute_job":
            return await self._call_opencue("reroute", {
                "job_id": f"job-{request.diagnosis.affected_frames[0]}",
                "target_node": self._select_healthy_node(request),
            }, caller_action=action)
        elif action == "spin_up_preemptible":
            if self.gcp:
                try:
                    instances = await self.gcp.start_preemptible_instances(
                        count=2, machine_type="n1-standard-4"
                    )
                except Exception as e:
                    self.logger.error("gcp_call_failed", action=action, error=str(e))
                    return {"action": action, "status": "failed", "error": str(e)}
                return {
                    "action": "spin_up_preemptible",
                    "status": "success",
                    "count": 2,
                    "instances": instances,
                    "gcp_resource": instances[0],
                }
            return {"action": "spin_up_preemptible", "status": "skipped_no_gcp"}
        elif action == "flag_for_artist":
            return {"action": "flag_for_artist", "status": "flagged"}
        elif action == "skip_frame":
            return {"action": "skip_frame", "status": "skipped"}
        elif action == "check_storage_connectivity":
            return {"action": "check_storage_connectivity", "status": "checked"}
        elif action == "check_license_server":
            return {"action": "check_license_server", "status": "checked"}
        elif action == "escalate_to_human":
            return {"action": "escalate_to_human", "status": "escalated"}
        return {"action": action, "status": "unknown"}

    def _select_healthy_node(self, request: RemediationRequest) -> str:
        """Pick the first node in context.healthy_nodes that isn't itself
        affected. Falls back to the demo default "node-3" only when Sentry/
        Pathologist didn't populate a healthy_nodes list — real farms
        should always provide one."""
        healthy_nodes = request.context.get("healthy_nodes") or []
        affected = set(request.diagnosis.affected_nodes)
        for node in healthy_nodes:
            if node not in affected:
                return node
        return "node-3"  # Demo fallback: no healthy_nodes list provided

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
