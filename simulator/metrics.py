from simulator.jobs import RenderJob
from simulator.nodes import RenderNode


class MetricsEmitter:
    """Exposes render-farm node metrics for scraping (review #19).

    A full Prometheus remote-write push client needs protobuf+snappy
    encoding and a live remote-write endpoint to verify against —
    neither practical here. This implements the review's documented
    "at minimum" fallback instead: real Prometheus text exposition
    format (a plain, standard format), served at GET /simulator/metrics
    so any local Prometheus/Grafana Agent can scrape it with zero
    custom protocol code — no grafana_url/api_key required for this
    (pull, not push).
    """

    def __init__(self, grafana_url: str = "", api_key: str = ""):
        self.grafana_url = grafana_url
        self.api_key = api_key

    async def emit_node_metrics(
        self, nodes: dict[str, RenderNode], jobs: list[RenderJob] | None = None
    ) -> str:
        """Render current node/queue metrics in Prometheus text exposition
        format. Async to match the original stub's signature and the
        rest of the codebase's emitter interfaces, even though rendering
        itself has no I/O."""
        jobs = jobs or []
        queue_depth_by_node: dict[str, int] = {}
        for job in jobs:
            if job.status in ("queued", "rendering"):
                node = job.assigned_node
                queue_depth_by_node[node] = queue_depth_by_node.get(node, 0) + 1

        lines = [
            "# HELP node_gpu_mem_percent GPU memory utilization percent",
            "# TYPE node_gpu_mem_percent gauge",
        ]
        for node_id, node in nodes.items():
            lines.append(f'node_gpu_mem_percent{{node="{node_id}"}} {node.gpu_mem_percent}')

        lines += [
            "# HELP render_queue_depth Number of queued/rendering jobs assigned to this node",
            "# TYPE render_queue_depth gauge",
        ]
        for node_id in nodes:
            depth = queue_depth_by_node.get(node_id, 0)
            lines.append(f'render_queue_depth{{node="{node_id}"}} {depth}')

        return "\n".join(lines) + "\n"
