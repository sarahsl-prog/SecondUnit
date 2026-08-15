# simulator/tests/test_engine.py
from simulator.nodes import RenderNode


def test_node_initial_state():
    node = RenderNode(id="node-1")
    assert node.cpu_percent == 0.0
    assert node.status == "idle"
