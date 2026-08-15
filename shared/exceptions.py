class AgentTimeout(Exception):
    """Raised when an agent exceeds its execution timeout."""

class HandsUnreachable(Exception):
    """Raised when Brain cannot reach Hands service."""

class BudgetExceeded(Exception):
    """Raised when Quartermaster denies due to budget."""
