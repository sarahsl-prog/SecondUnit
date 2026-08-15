class HandsUnreachable(Exception):
    """Raised when Brain cannot reach Hands service after exhausting
    retries (see QuartermasterAgent.send_to_hands, review #23)."""
