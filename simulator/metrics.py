

from simulator.nodes import RenderNode


class MetricsEmitter:
    def __init__(self, grafana_url: str = "", api_key: str = ""):
        self.grafana_url = grafana_url
        self.api_key = api_key

    async def emit_node_metrics(self, nodes: dict[str, RenderNode]):
        """Push node metrics to Grafana. Stub for now."""
        # TODO: Implement OpenTelemetry push
