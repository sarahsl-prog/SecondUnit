from typing import Dict, Any

FAILURE_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "gpu_memory_exhaustion": {
        "gpu_mem_percent": 99.0,
        "error_log": "CUDA out of memory",
        "node_status": "failed",
    },
    "corrupt_scene_file": {
        "error_log": "Scene file malformed at line 4821",
    },
    "network_timeout": {
        "network_latency_ms": 15000,
        "error_log": "Connection timed out to storage bucket",
    },
    "license_failure": {
        "error_log": "Arnold license server unreachable",
    },
    "stuck_job": {
        "cpu_percent": 3.0,
        "gpu_percent": 0.0,
        "status": "stuck",
        "duration_hours": 6,
    },
}
