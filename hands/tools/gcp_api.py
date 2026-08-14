from typing import Dict, Any

class GCPComputeClient:
    """Wrapper for GCP Compute Engine API. Stub for local dev."""

    def __init__(self, project_id: str, zone: str):
        self.project_id = project_id
        self.zone = zone

    async def start_preemptible_instances(self, count: int, machine_type: str) -> list:
        """Spin up preemptible GPU instances. Returns list of created instances."""
        # Stub: return mock instance names
        return [
            {"name": f"preemptible-gpu-{i}", "zone": self.zone, "status": "PROVISIONING"}
            for i in range(count)
        ]

    async def resize_node_pool(self, pool_name: str, size: int) -> Dict[str, Any]:
        return {"pool": pool_name, "size": size, "status": "ok"}
