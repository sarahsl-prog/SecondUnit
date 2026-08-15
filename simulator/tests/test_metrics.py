"""MetricsEmitter Prometheus exposition output (review #19)."""
import pytest

from simulator.jobs import RenderJob
from simulator.metrics import MetricsEmitter
from simulator.nodes import RenderNode


@pytest.mark.asyncio
async def test_emit_node_metrics_renders_prometheus_exposition_format():
    nodes = {
        "node-1": RenderNode(id="node-1", gpu_mem_percent=42.0),
        "node-2": RenderNode(id="node-2", gpu_mem_percent=99.0),
    }
    jobs = [
        RenderJob(id="job-1", frame=1, scene="scene_1", assigned_node="node-2", status="rendering"),
        RenderJob(id="job-2", frame=2, scene="scene_1", assigned_node="node-2", status="queued"),
        RenderJob(id="job-3", frame=3, scene="scene_1", assigned_node="node-1", status="failed"),
    ]
    emitter = MetricsEmitter()

    text = await emitter.emit_node_metrics(nodes, jobs)

    assert 'node_gpu_mem_percent{node="node-1"} 42.0' in text
    assert 'node_gpu_mem_percent{node="node-2"} 99.0' in text
    # node-2 has 2 queued/rendering jobs, node-1 has 0 (its job is "failed")
    assert 'render_queue_depth{node="node-2"} 2' in text
    assert 'render_queue_depth{node="node-1"} 0' in text
    assert text.startswith("# HELP")


@pytest.mark.asyncio
async def test_emit_node_metrics_handles_no_jobs():
    nodes = {"node-1": RenderNode(id="node-1")}
    emitter = MetricsEmitter()
    text = await emitter.emit_node_metrics(nodes)
    assert 'render_queue_depth{node="node-1"} 0' in text
