# simulator/tests/test_engine.py
from unittest.mock import AsyncMock

import pytest

from simulator.engine import RenderFarmSimulator
from simulator.nodes import RenderNode


def test_node_initial_state():
    node = RenderNode(id="node-1")
    assert node.cpu_percent == 0.0
    assert node.status == "idle"


@pytest.mark.asyncio
async def test_trigger_scenario_pushes_error_log_via_log_emitter():
    """review #19: LogEmitter previously existed but was never wired into
    the simulator at all — a triggered failure's error_log must reach it."""
    log_emitter = AsyncMock()
    sim = RenderFarmSimulator(node_count=8, log_emitter=log_emitter)

    await sim.trigger_scenario("gpu_memory_exhaustion", target_node="node-3")

    log_emitter.emit_log.assert_called_once_with("node-3", "CUDA out of memory", level="error")


@pytest.mark.asyncio
async def test_trigger_scenario_skips_log_emit_when_scenario_has_no_error_log():
    log_emitter = AsyncMock()
    sim = RenderFarmSimulator(node_count=8, log_emitter=log_emitter)

    # stuck_job (simulator/failures.py) has no error_log key
    await sim.trigger_scenario("stuck_job", target_node="node-3")

    log_emitter.emit_log.assert_not_called()
