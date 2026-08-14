import yaml
from pathlib import Path
from shared.types import Diagnosis, Approval, CostEstimate
from shared.logger import get_logger
import httpx

class QuartermasterAgent:
    """Gates expensive actions against budget/cost rules."""
    
    def __init__(self, trace_id: str = "", hands_url: str = ""):
        self.trace_id = trace_id
        self.hands_url = hands_url
        self.logger = get_logger(trace_id=trace_id, agent_name="Quartermaster")
        self.policy = self._load_policy()
        
    def _load_policy(self) -> dict:
        policy_path = Path(__file__).parent / "cost_policy.yaml"
        with open(policy_path) as f:
            return yaml.safe_load(f)
            
    async def evaluate(self, diagnosis: Diagnosis) -> dict:
        self.logger.info(
            "quartermaster_evaluating",
            failure_type=diagnosis.failure_type,
            recommended_action=diagnosis.recommended_action,
        )
        
        # Calculate cost estimate
        cost = self._estimate_cost(diagnosis)
        budget = self.policy["budget"]
        
        # Decision logic
        if cost.estimated_cost_usd <= budget["preemptible_gpu"]["approval_threshold_usd"]:
            decision = "approve"
            reason = f"Within nightly GPU budget; under ${budget['preemptible_gpu']['approval_threshold_usd']}"
        elif cost.estimated_cost_usd <= budget["nightly_limit_usd"]:
            decision = "escalate"
            reason = "Exceeds auto-approval threshold but within nightly limit"
        else:
            decision = "deny"
            reason = f"Exceeds nightly limit of ${budget['nightly_limit_usd']}"
            
        approval = Approval(
            approved=(decision == "approve"),
            budget_remaining_usd=budget["nightly_limit_usd"] - cost.estimated_cost_usd,
        )
        
        self.logger.info(
            "quartermaster_decision",
            decision=decision,
            cost=cost.estimated_cost_usd,
        )
        
        return {
            "decision": decision,
            "reason": reason,
            "cost_estimate": cost.model_dump(),
            "approval": approval.model_dump(),
        }
        
    def _estimate_cost(self, diagnosis: Diagnosis) -> CostEstimate:
        """Simple cost estimation based on failure type."""
        if diagnosis.failure_type == "gpu_memory_exhaustion":
            return CostEstimate(
                preemptible_gpus=2,
                estimated_cost_usd=4.50,
                duration_minutes=15,
            )
        elif diagnosis.failure_type == "corrupt_scene_file":
            return CostEstimate(estimated_cost_usd=0.0)
        elif diagnosis.failure_type == "network_timeout":
            return CostEstimate(estimated_cost_usd=0.0)
        return CostEstimate(estimated_cost_usd=0.0)
        
    async def send_to_hands(self, remediation_request: dict) -> dict:
        """POST approved remediation to Hands service."""
        if not self.hands_url:
            self.logger.error("hands_url_not_configured")
            raise ValueError("HANDS_SERVICE_URL not set")
            
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.post(
                    f"{self.hands_url}/remediate",
                    json=remediation_request,
                )
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPError as e:
                self.logger.error("hands_unreachable", error=str(e))
                raise
