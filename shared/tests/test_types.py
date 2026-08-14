# shared/tests/test_types.py
from shared.types import Diagnosis, Approval, RemediationRequest

def test_diagnosis_validation():
    d = Diagnosis(
        failure_type="gpu_memory_exhaustion",
        affected_nodes=["node-7"],
        affected_frames=[1847],
        scene="scene_47",
        recommended_action="reroute_to_healthy_nodes",
        confidence=0.94,
        reasoning="GPU memory at 99%",
    )
    assert d.confidence == 0.94
