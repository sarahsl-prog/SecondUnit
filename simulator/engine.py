import asyncio

from shared.logger import get_logger
from simulator.failures import FAILURE_SCENARIOS
from simulator.jobs import RenderJob
from simulator.logs import LogEmitter
from simulator.nodes import RenderNode
from simulator.scenes import DEFAULT_SCENES

logger = get_logger(agent_name="Simulator")


class RenderFarmSimulator:
    def __init__(self, node_count: int = 8, log_emitter: LogEmitter | None = None):
        self.nodes: dict[str, RenderNode] = {
            f"node-{i}": RenderNode(id=f"node-{i}") for i in range(node_count)
        }
        self.jobs: list[RenderJob] = []
        self.running = False
        self._task = None
        # review #19: LogEmitter previously existed but was never
        # instantiated anywhere — wire it in so a triggered failure's
        # error_log actually reaches Loki when configured.
        self.log_emitter = log_emitter or LogEmitter()

    def start(self):
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("simulator_started", node_count=len(self.nodes))

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("simulator_stopped")

    async def _loop(self):
        while self.running:
            for node in self.nodes.values():
                if node.status == "rendering":
                    node.cpu_percent = min(95.0, node.cpu_percent + 2.0)
                    node.gpu_percent = min(90.0, node.gpu_percent + 3.0)
                    node.gpu_mem_percent = min(85.0, node.gpu_mem_percent + 1.5)
                elif node.status == "idle":
                    node.cpu_percent = max(5.0, node.cpu_percent - 5.0)
                    node.gpu_percent = max(0.0, node.gpu_percent - 5.0)
                    node.gpu_mem_percent = max(10.0, node.gpu_mem_percent - 2.0)
            await asyncio.sleep(5)

    async def trigger_scenario(
        self, scenario_name: str, target_node: str = "", scene: str = ""
    ) -> dict:
        if scenario_name not in FAILURE_SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        scenario = FAILURE_SCENARIOS[scenario_name].copy()
        if not target_node:
            target_node = "node-7"  # Default for demo

        node = self.nodes.get(target_node)
        if not node:
            raise ValueError(f"Unknown node: {target_node}")

        # Apply scenario effects
        for attr, value in scenario.items():
            if hasattr(node, attr):
                setattr(node, attr, value)
        node.status = "failed"

        if node.error_log:
            await self.log_emitter.emit_log(target_node, node.error_log, level="error")

        # Seed a job record so Pathologist can derive real affected_frames
        # and scene instead of hardcoding them (review #10), rather than
        # just mutating node metrics with no job ever created.
        scene_name = scene or DEFAULT_SCENES[0].name
        frame = len(self.jobs) * 2 + 1
        job = RenderJob(
            id=f"job-{frame}",
            frame=frame,
            scene=scene_name,
            assigned_node=target_node,
            status="failed",
        )
        self.jobs.append(job)

        logger.info(
            "failure_triggered",
            scenario=scenario_name,
            target_node=target_node,
            job_id=job.id,
        )
        return {"scenario": scenario_name, "node": target_node, "applied": True, "job_id": job.id}

    def reset(self):
        for node in self.nodes.values():
            node.cpu_percent = 0.0
            node.gpu_percent = 0.0
            node.gpu_mem_percent = 0.0
            node.disk_io_mbps = 0.0
            node.network_latency_ms = 0.0
            node.status = "idle"
            node.error_log = ""
        self.jobs = []
        logger.info("simulator_reset")

    def get_status(self) -> dict:
        return {
            "nodes": {nid: n.model_dump() for nid, n in self.nodes.items()},
            "job_count": len(self.jobs),
        }
