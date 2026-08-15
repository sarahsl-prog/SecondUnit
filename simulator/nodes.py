from pydantic import BaseModel
from typing import Literal


class RenderNode(BaseModel):
    id: str
    cpu_percent: float = 0.0
    gpu_percent: float = 0.0
    gpu_mem_percent: float = 0.0
    disk_io_mbps: float = 0.0
    network_latency_ms: float = 0.0
    status: Literal["idle", "rendering", "failed", "offline"] = "idle"
    error_log: str = ""
