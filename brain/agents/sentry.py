from brain.tools.grafana_mcp import GrafanaMCPClient
from shared.types import AnomalyReport
from shared.logger import get_logger
import random

class SentryAgent:
    """Detects anomalies by polling Grafana Cloud metrics."""

    # GPU memory checked first: exhaustion is the more immediate failure
    # mode (crashes the render), queue depth is a slower-building backlog.
    GPU_MEM_THRESHOLD = 90.0
    QUEUE_DEPTH_THRESHOLD = 80.0

    def __init__(self, grafana: GrafanaMCPClient, trace_id: str = ""):
        self.grafana = grafana
        self.trace_id = trace_id or f"txn-{random.randint(100000, 999999)}"
        self.logger = get_logger(trace_id=self.trace_id, agent_name="Sentry")

    async def run(self) -> AnomalyReport:
        self.logger.info("sentry_polling_start")

        gpu_metrics = await self.grafana.query_metrics(
            'node_gpu_mem_percent{job="render_farm"}'
        )
        queue_metrics = await self.grafana.query_metrics(
            'render_queue_depth{job="render_farm"}'
        )

        gpu_node, gpu_value = self._max_metric(gpu_metrics)
        queue_node, queue_value = self._max_metric(queue_metrics)

        if gpu_value > self.GPU_MEM_THRESHOLD:
            return self._report(
                anomaly_type="gpu_memory_spike",
                metric="node_gpu_mem_percent",
                node=gpu_node,
                value=gpu_value,
                threshold=self.GPU_MEM_THRESHOLD,
            )

        if queue_value > self.QUEUE_DEPTH_THRESHOLD:
            return self._report(
                anomaly_type="queue_depth_spike",
                metric="render_queue_depth",
                node=queue_node,
                value=queue_value,
                threshold=self.QUEUE_DEPTH_THRESHOLD,
            )

        self.logger.info("no_anomaly_detected")
        return AnomalyReport(
            anomaly_detected=False,
            anomaly_type="none",
            severity="low",
            affected_nodes=[],
        )

    @staticmethod
    def _max_metric(metrics: dict) -> tuple[str, float]:
        """Parse a Prometheus-shaped query_metrics() result (simplified for
        demo) into (node with the highest value, that value)."""
        result = metrics.get("data", {}).get("result", [])
        max_value = 0.0
        node = "unknown"
        for item in result:
            val = float(item.get("value", [0, "0"])[1])
            if val > max_value:
                max_value = val
                node = item.get("metric", {}).get("node", "unknown")
        return node, max_value

    def _report(self, anomaly_type: str, metric: str, node: str, value: float, threshold: float) -> AnomalyReport:
        report = AnomalyReport(
            anomaly_detected=True,
            anomaly_type=anomaly_type,
            severity="high",
            affected_nodes=[node],
            grafana_context={"metric": metric, "value": value, "threshold": threshold},
        )
        self.logger.info("anomaly_detected", anomaly_type=anomaly_type, metric=metric, value=value)
        return report
