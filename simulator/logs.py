class LogEmitter:
    def __init__(self, grafana_url: str = "", api_key: str = ""):
        self.grafana_url = grafana_url
        self.api_key = api_key

    async def emit_log(self, node_id: str, message: str, level: str = "error"):
        """Push log to Loki. Stub for now."""
