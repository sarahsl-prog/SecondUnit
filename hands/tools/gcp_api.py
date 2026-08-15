from typing import Any

from shared.logger import get_logger

logger = get_logger(agent_name="GCPComputeClient")


class GCPComputeClient:
    """Wrapper for GCP Compute Engine API. Stub for local dev — no real GCP
    SDK/API calls are made yet regardless of dry_run.

    dry_run defaults True (outstanding-decision #8): if a real
    implementation lands here later, it must check self.dry_run and skip
    the actual provisioning call when true, so an unattended poll loop
    can never accidentally spin up billable instances unless a human
    explicitly set ENABLE_REAL_GCP_ACTIONS=true for demo day.
    """

    def __init__(self, project_id: str, zone: str, dry_run: bool = True):
        self.project_id = project_id
        self.zone = zone
        self.dry_run = dry_run

    async def start_preemptible_instances(self, count: int, machine_type: str) -> list:
        """Spin up preemptible GPU instances. Returns list of created instances."""
        if not self.dry_run:
            logger.error(
                "gcp_real_actions_not_implemented",
                detail="ENABLE_REAL_GCP_ACTIONS is set but GCPComputeClient has no real "
                "implementation yet — returning stub data, no instances were created.",
            )
        return [
            {
                "name": f"preemptible-gpu-{i}",
                "zone": self.zone,
                "status": "PROVISIONING",
                "dry_run": self.dry_run,
            }
            for i in range(count)
        ]

    async def resize_node_pool(self, pool_name: str, size: int) -> dict[str, Any]:
        return {"pool": pool_name, "size": size, "status": "ok", "dry_run": self.dry_run}
