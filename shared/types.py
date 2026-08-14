from pydantic import BaseModel, Field
from typing import Literal, List
from datetime import datetime

class Diagnosis(BaseModel):
    failure_type: Literal[
        "gpu_memory_exhaustion",
        "corrupt_scene_file",
        "network_timeout",
        "license_failure",
        "unknown",
    ]
    affected_nodes: List[str]
    affected_frames: List[int]
    scene: str
    recommended_action: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""

class Approval(BaseModel):
    approved: bool
    approved_by: str = "Quartermaster"
    budget_remaining_usd: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class CostEstimate(BaseModel):
    preemptible_gpus: int = 0
    estimated_cost_usd: float = 0.0
    duration_minutes: int = 0

class RemediationRequest(BaseModel):
    trace_id: str
    diagnosis: Diagnosis
    cost_estimate: CostEstimate
    approval: Approval
    context: dict = {}

class RemediationResult(BaseModel):
    trace_id: str
    status: Literal["success", "partial_failure", "failure"]
    actions_taken: List[dict] = []
    dispatcher_summary: dict = {}

class AgentLog(BaseModel):
    trace_id: str
    agent_name: str
    step: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input_data: dict = {}
    output_data: dict = {}
    latency_ms: int = 0
    tokens: int = 0
    severity: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
