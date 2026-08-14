class AgentTimeout(Exception):
    """Raised when an agent exceeds its execution timeout."""
    pass

class HandsUnreachable(Exception):
    """Raised when Brain cannot reach Hands service."""
    pass

class BudgetExceeded(Exception):
    """Raised when Quartermaster denies due to budget."""
    pass
