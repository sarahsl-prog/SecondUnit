from typing import Literal

from pydantic import BaseModel


class RenderJob(BaseModel):
    id: str
    frame: int
    scene: str
    priority: int = 1
    assigned_node: str = ""
    status: Literal["queued", "rendering", "completed", "failed", "stuck"] = "queued"
    duration_seconds: float = 0.0
