import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import yaml

from shared.logger import get_logger
from shared.types import Approval, CostEstimate, Diagnosis

# Design spec §3.3: retry with exponential backoff, max 3 attempts, before
# giving up on Hands.
MAX_HANDS_ATTEMPTS = 3
HANDS_RETRY_BACKOFF_SECONDS = 1.0

# Single-instance demo persistence for nightly spend tracking. Cloud Run
# guarantees a writable /tmp (tmpfs), but it does NOT survive instance
# restarts or get shared across concurrent instances — see review #6 /
# outstanding-decision #2 for the accepted limitation.
DEFAULT_BUDGET_STATE_PATH = Path("/tmp/secondunit-budget-state.json")


class QuartermasterAgent:
    """Gates expensive actions against budget/cost rules."""

    def __init__(
        self, trace_id: str = "", hands_url: str = "", state_path: Path | str | None = None
    ):
        self.trace_id = trace_id
        self.hands_url = hands_url
        self.state_path = Path(state_path) if state_path else DEFAULT_BUDGET_STATE_PATH
        self.logger = get_logger(trace_id=trace_id, agent_name="Quartermaster")
        self.policy = self._load_policy()

    def _load_policy(self) -> dict:
        policy_path = Path(__file__).parent / "cost_policy.yaml"
        with open(policy_path) as f:
            return yaml.safe_load(f)

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    def _load_spend_state(self) -> dict:
        """Read today's cumulative spend/instance count, resetting on a new day."""
        state = {"date": self._today(), "spent_usd": 0.0, "instances_used": 0}
        if self.state_path.exists():
            try:
                loaded = json.loads(self.state_path.read_text())
                if loaded.get("date") == state["date"]:
                    state.update(loaded)
            except (json.JSONDecodeError, OSError):
                pass  # corrupt/unreadable state -> start the day fresh
        return state

    def _save_spend_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state))

    async def evaluate(self, diagnosis: Diagnosis) -> dict:
        self.logger.info(
            "quartermaster_evaluating",
            failure_type=diagnosis.failure_type,
            recommended_action=diagnosis.recommended_action,
        )

        # Calculate cost estimate
        cost = self._estimate_cost(diagnosis)
        budget = self.policy["budget"]
        max_instances = budget["preemptible_gpu"]["max_instances"]

        state = self._load_spend_state()
        today_spent = state["spent_usd"]
        today_instances = state["instances_used"]
        projected_spent = today_spent + cost.estimated_cost_usd
        projected_instances = today_instances + cost.preemptible_gpus

        # Decision logic — running totals, not just this incident's cost.
        if projected_instances > max_instances:
            decision = "deny"
            reason = (
                f"Would use {projected_instances} preemptible GPUs today, "
                f"exceeding max_instances ({max_instances})"
            )
        elif projected_spent > budget["nightly_limit_usd"]:
            decision = "deny"
            reason = (
                f"Would bring today's spend to ${projected_spent:.2f}, "
                f"exceeding nightly limit of ${budget['nightly_limit_usd']}"
            )
        elif cost.estimated_cost_usd <= budget["preemptible_gpu"]["approval_threshold_usd"]:
            decision = "approve"
            approval_threshold = budget["preemptible_gpu"]["approval_threshold_usd"]
            reason = f"Within nightly GPU budget; under ${approval_threshold}"
        else:
            decision = "escalate"
            reason = "Exceeds auto-approval threshold but within nightly limit"

        if decision == "approve":
            state["spent_usd"] = projected_spent
            state["instances_used"] = projected_instances
            self._save_spend_state(state)

        approval = Approval(
            approved=(decision == "approve"),
            budget_remaining_usd=max(0.0, budget["nightly_limit_usd"] - state["spent_usd"]),
        )

        self.logger.info(
            "quartermaster_decision",
            decision=decision,
            cost=cost.estimated_cost_usd,
            today_spent=state["spent_usd"],
            today_instances=state["instances_used"],
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
        elif diagnosis.failure_type in ("corrupt_scene_file", "network_timeout"):
            return CostEstimate(estimated_cost_usd=0.0)
        return CostEstimate(estimated_cost_usd=0.0)
        
    async def send_to_hands(
        self,
        remediation_request: dict,
        max_attempts: int = MAX_HANDS_ATTEMPTS,
        backoff_base_seconds: float = HANDS_RETRY_BACKOFF_SECONDS,
    ) -> dict:
        """POST approved remediation to Hands service, retrying with
        exponential backoff before giving up (design spec §3.3 — previously
        this raised on the first failure, so a transient network blip
        failed the whole remediation)."""
        if not self.hands_url:
            self.logger.error("hands_url_not_configured")
            raise ValueError("HANDS_SERVICE_URL not set")

        last_error: httpx.HTTPError | None = None
        for attempt in range(1, max_attempts + 1):
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    resp = await client.post(
                        f"{self.hands_url}/remediate",
                        json=remediation_request,
                    )
                    resp.raise_for_status()
                    return resp.json()
                except httpx.HTTPError as e:
                    last_error = e
                    self.logger.warning(
                        "hands_call_failed",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=str(e),
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(backoff_base_seconds * (2 ** (attempt - 1)))

        self.logger.error("hands_unreachable", attempts=max_attempts, error=str(last_error))
        raise last_error
