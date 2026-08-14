---
date: 2026-08-14
project: SecondUnit
status: Design Approved
hackathon: Agentic Cinema: The Blockbuster Hackathon
deadline: 2026-09-07
track: Grafana
author: Sarah Sund-Lussier
---

# SecondUnit — VFX Render Farm Health Agent: Design Specification

## 1. Executive Summary

SecondUnit is a multi-agent system that monitors, diagnoses, and remediates failures in a VFX/animation render farm. It combines **Grafana Cloud** (observability via MCP) with **Gemini + Google ADK** (orchestration and reasoning) to create a deterministic, multi-step agentic workflow.

**The problem:** Animation and VFX houses run render farms that process thousands of frames. Jobs fail silently, artists waste hours waiting, and production coordinators manually check dashboards. SecondUnit automates the entire cycle: detection → diagnosis → remediation → cost-gating → human escalation.

**Why it fits the hackathon:**
- Heavy Grafana Cloud MCP usage (60+ tools for metrics, logs, traces, dashboards, alerts)
- Multi-agent architecture with clear role separation
- Real media/entertainment workflow (VFX production)
- Deterministic, observable agentic chain

---

## 2. Architecture Overview

### 2.1 System Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Simulator Service (Cloud Run)                               │
│  - Python asyncio simulator                                  │
│  - Emits metrics/logs to Grafana Cloud                       │
│  - Exposes POST /trigger/{scenario} for demo control       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ↓ emits metrics/logs
┌──────────────────────────────────────────────────────────────┐
│                      Brain Service (Cloud Run)               │
│  ┌──────────┐    ┌─────────────┐    ┌──────────────────┐   │
│  │ Sentry   │───→│ Pathologist │───→│ Quartermaster    │   │
│  │ Agent    │    │ Agent       │    │ Agent            │   │
│  └──────────┘    └─────────────┘    └────────┬─────────┘   │
└────────────────────────────────────────────────┼─────────────┘
                                                 │
                              HTTP POST /remediate
                              (JSON: diagnosis, cost_estimate, context)
                                                 │
                              ┌──────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│                      Hands Service (Cloud Run)               │
│              ┌──────────────┐    ┌──────────────────┐      │
│              │ Surgeon      │───→│ Dispatcher       │      │
│              │ Agent        │    │ Agent            │      │
│              └──────────────┘    └──────────────────┘      │
└──────────────────────────────────────────────────────────────┘
                              │
                              ↓
                    ┌─────────────────┐
                    │  Mock OpenCue   │
                    │  API (module)   │
                    │  Same container │
                    └─────────────────┘
```

### 2.2 Deployment Model

- **Three Cloud Run services:** Simulator, Brain, Hands
- **Single Gemini Flash model** for all agent reasoning (fast, cost-effective)
- **Grafana Cloud MCP** connected via stdio (locally) or SSE (Cloud Run) for metrics, logs, traces, dashboards, alerts
- **Mock OpenCue API** — FastAPI router within Hands service (requeue, reroute, kill)
- **Structured logging** to Cloud Logging + Vertex AI Experiments for full traceability

### 2.3 Rationale for Multi-Service Design

The original design considered a single Cloud Run service. We chose three services to:
- Separate simulation from agent logic (cleaner testing, independent scaling)
- Practice real distributed agent architecture (learning value)
- Improve observability (each service has isolated logs, easier to debug)
- Demonstrate inter-service communication to judges

The Brain→Hands boundary is the key architectural decision: the "thinking" agents (Sentry, Pathologist, Quartermaster) run together for fast iteration, while the "acting" agents (Surgeon, Dispatcher) run separately to model real-world separation of concerns.

---

## 3. Data Flow

### 3.1 Happy Path

```
1. Simulator emits healthy baseline metrics to Grafana Cloud
2. Simulator triggers "gpu_memory_exhaustion" failure on node-7
3. Grafana dashboards show queue depth spike + failure rate increase
4. Cloud Scheduler triggers Sentry Agent (every 30s)
5. Sentry polls Grafana → detects anomaly → spawns Pathologist
6. Pathologist queries Loki logs + Tempo traces → classifies:
   - Failure type: "gpu_memory_exhaustion"
   - Affected nodes: ["node-7"]
   - Affected frames: [1847, 1848]
   - Scene: "scene_47"
   - Recommended action: "reroute_to_healthy_nodes"
   - Confidence: 0.94
7. Quartermaster evaluates cost:
   - Preemptible GPUs: 2
   - Estimated cost: $4.50
   - Decision: APPROVE (within nightly budget policy)
8. Quartermaster POSTs to Hands Service /remediate
9. Surgeon executes:
   - reroute_job(job-1847, node-3)
   - spin_up_preemptible(count=2, type=n1-standard-4)
10. Dispatcher sends:
    - Slack notification to artist
    - Grafana dashboard annotation
    - Morning summary log
11. Simulator shows recovery → Grafana returns to green
```

### 3.2 Brain → Hands Communication Contract

**Request (Brain → Hands):**
```json
{
  "trace_id": "txn-2026-08-14-abc123",
  "diagnosis": {
    "failure_type": "gpu_memory_exhaustion",
    "affected_nodes": ["node-7", "node-12"],
    "affected_frames": [1847, 1848],
    "scene": "scene_47",
    "recommended_action": "reroute_to_healthy_nodes",
    "confidence": 0.94
  },
  "cost_estimate": {
    "preemptible_gpus": 2,
    "estimated_cost_usd": 4.50,
    "duration_minutes": 15
  },
  "approval": {
    "approved": true,
    "approved_by": "Quartermaster",
    "budget_remaining_usd": 245.50,
    "timestamp": "2026-08-14T09:23:00Z"
  },
  "context": {
    "sentry_alert_id": "alert-12345",
    "grafana_dashboard_url": "https://grafana.cloud/..."
  }
}
```

**Response (Hands → Brain):**
```json
{
  "trace_id": "txn-2026-08-14-abc123",
  "status": "success",
  "actions_taken": [
    {"action": "reroute_job", "job_id": "job-1847", "target_node": "node-3"},
    {"action": "spin_up_preemptible", "count": 2, "instance_type": "n1-standard-4"}
  ],
  "dispatcher_summary": {
    "notification_sent": true,
    "channels": ["slack", "grafana_annotation"],
    "message": "Scene 47 frame 1847 rerouted. 2 preemptible GPUs spun up."
  }
}
```

### 3.3 Error Handling

**Brain → Hands communication failure:**
- Quartermaster retries with exponential backoff (max 3 attempts)
- After 3 failures, falls back to Dispatcher-in-Brain (simplified escalation)
- Logs `error_type: "hands_unreachable"` with full context

**Surgeon partial failure:**
- If GCP API returns error mid-action, Surgeon returns `status: "partial_failure"`
- Includes `succeeded_actions` and `failed_actions` arrays
- Dispatcher still notifies human with clear status

**Agent timeout:**
- Each agent has a 30-second timeout
- Timeout triggers Dispatcher escalation with `reason: "agent_timeout"`

---

## 4. Agent Specifications

### 4.1 Sentry Agent (Brain Service)

| Attribute | Value |
|---|---|
| **Role** | Detect anomalies by polling Grafana Cloud metrics and alert states |
| **Trigger** | Cloud Scheduler HTTP call every 30 seconds |
| **Model** | Gemini Flash, temperature=0.1 |
| **Output format** | Structured JSON (forced) |

**Tools:**
- `grafana_mcp.query_metrics` — node CPU/GPU, queue depth, failure rate
- `grafana_mcp.get_dashboard` — read render farm health dashboard state
- `grafana_mcp.list_incidents` — check if anomaly is part of broader incident

**Decision logic:**
- Compares current metrics against thresholds
- Does not reason creatively — applies deterministic rules
- If anomaly detected, spawns Pathologist with full context

**Output schema:**
```json
{
  "anomaly_detected": true,
  "anomaly_type": "queue_depth_spike",
  "severity": "high",
  "affected_nodes": ["node-7"],
  "grafana_context": {
    "metric": "render_queue_depth",
    "value": 98.5,
    "threshold": 80,
    "dashboard_url": "https://grafana.cloud/..."
  }
}
```

---

### 4.2 Pathologist Agent (Brain Service)

| Attribute | Value |
|---|---|
| **Role** | Diagnose root cause by correlating metrics, logs (Loki), and traces (Tempo) |
| **Trigger** | Called by Sentry with anomaly context |
| **Model** | Gemini Flash, temperature=0.3 |
| **Output format** | Structured JSON with confidence score |

**Tools:**
- `grafana_mcp.query_logs` — Loki logs from affected nodes
- `grafana_mcp.query_traces` — Tempo traces for job execution paths
- `grafana_mcp.query_metrics` — historical correlation

**Failure classification (exhaustive):**
- `memory_exhaustion` — reduce threads and retry
- `corrupt_scene_file` — flag for artist, skip frame
- `gpu_driver_crash` — reroute to healthy node
- `network_timeout` — check storage connectivity
- `license_failure` — check license server
- `unknown` — escalate to human

**Output schema:**
```json
{
  "diagnosis": {
    "failure_type": "gpu_memory_exhaustion",
    "affected_nodes": ["node-7"],
    "affected_frames": [1847, 1848],
    "scene": "scene_47",
    "recommended_action": "reroute_to_healthy_nodes",
    "confidence": 0.94,
    "reasoning": "GPU memory at 99% with CUDA OOM errors in Loki logs"
  }
}
```

---

### 4.3 Quartermaster Agent (Brain Service)

| Attribute | Value |
|---|---|
| **Role** | Gate expensive actions against budget/cost rules |
| **Trigger** | Called by Pathologist with diagnosis |
| **Model** | Gemini Flash, temperature=0.2 |
| **Output format** | Structured JSON (forced) |

**Tools:**
- `grafana_mcp.query_metrics` — cost dashboards, billing metrics
- `check_budget_policy` — reads YAML/JSON cost policy

**Cost policy (YAML):**
```yaml
budget:
  nightly_limit_usd: 50.00
  preemptible_gpu:
    max_instances: 4
    cost_per_hour: 0.50
    approval_threshold_usd: 10.00
  standard_instance:
    approval_threshold_usd: 20.00
escalation:
  human_approval_required: true
  channels: ["slack", "email"]
```

**Decision logic:**
- Parses diagnosis and applies policy rules
- Cost estimate from GCP pricing API or hardcoded estimates
- If uncertain, defaults to `escalate`

**Output schema:**
```json
{
  "decision": "approve",
  "reason": "Within nightly GPU budget; preemptible instances approved under $10",
  "cost_estimate": {
    "preemptible_gpus": 2,
    "usd": 4.50,
    "duration_minutes": 15
  },
  "budget_remaining_usd": 245.50
}
```

---

### 4.4 Surgeon Agent (Hands Service)

| Attribute | Value |
|---|---|
| **Role** | Execute approved remediation actions |
| **Trigger** | HTTP POST from Quartermaster to `/remediate` |
| **Model** | Mostly deterministic code; Gemini Flash temperature=0.1 for edge cases only |
| **Output format** | Structured JSON |

**Tools:**
- `gcp_api.resize_node_pool` — GKE/Compute Engine node pool scaling
- `gcp_api.start_preemptible_instances` — spin up preemptible GPU instances
- `mock_opencue.requeue_job` — requeue failed frame
- `mock_opencue.reroute_job` — reroute remaining frames
- `mock_opencue.kill_stuck_job` — kill hung process

**Action mapping (deterministic):**
| Failure type | Action |
|---|---|
| `gpu_memory_exhaustion` | reroute_job + spin_up_preemptible |
| `corrupt_scene_file` | flag_for_artist + skip_frame |
| `network_timeout` | check_storage_connectivity |
| `license_failure` | check_license_server |
| `unknown` | escalate_to_human |

**Output schema:**
```json
{
  "status": "success",
  "actions_taken": [
    {"action": "reroute_job", "job_id": "job-1847", "target_node": "node-3"},
    {"action": "spin_up_preemptible", "count": 2, "instance_type": "n1-standard-4"}
  ],
  "gcp_resources_created": [
    {"type": "compute_instance", "name": "preemptible-gpu-1", "zone": "us-central1-a"}
  ]
}
```

---

### 4.5 Dispatcher Agent (Hands Service + Brain fallback)

| Attribute | Value |
|---|---|
| **Role** | Communicate outcomes to humans and log to Grafana annotations |
| **Trigger** | Called by Surgeon (Hands) or Quartermaster (Brain fallback on denial) |
| **Model** | Gemini Flash, temperature=0.4 (human-readable summary generation) |
| **Output format** | Structured JSON |

**Tools:**
- `grafana_mcp.create_alert` — add annotation to dashboard
- `grafana_mcp.annotate_dashboard` — mark timeline with event
- `slack_webhook.send_notification` — notify artist/coordinator
- `email.send_summary` — morning summary

**Notification content:**
- What failed (failure type, affected nodes/frames)
- What was done (actions taken, resources created)
- What the human should check (if anything)
- Links to Grafana dashboard for full context

**Output schema:**
```json
{
  "notification_sent": true,
  "channels": ["slack", "grafana_annotation"],
  "grafana_annotation_id": "ann-98765",
  "slack_message_ts": "1234567890.123456",
  "summary": "Scene 47 frame 1847 rerouted to node-3. 2 preemptible GPUs spun up. Total cost: $4.50."
}
```

---

## 5. Simulation Design

### 5.1 Render Farm Simulator

A Python asyncio service that simulates 8-10 render nodes, each processing a queue of frames from multiple scenes. Runs as a separate Cloud Run service.

**Simulated entities:**
- **Nodes:** 8 nodes with CPU %, GPU %, GPU memory %, disk I/O, network latency
- **Jobs:** Each has frame number, scene file, priority, assigned node, status
- **Scenes:** Each has frame count, average render time, memory profile

**Failure injection modes (configurable):**
```python
FAILURE_SCENARIOS = {
    "gpu_memory_exhaustion": {
        "gpu_mem": 99,
        "error_log": "CUDA out of memory",
        "affected_node": "node-7"
    },
    "corrupt_scene_file": {
        "error_log": "Scene file malformed at line 4821",
        "affected_node": "random"
    },
    "network_timeout": {
        "network_latency_ms": 15000,
        "error_log": "Connection timed out to storage bucket"
    },
    "license_failure": {
        "error_log": "Arnold license server unreachable"
    },
    "stuck_job": {
        "cpu": 3,
        "gpu": 0,
        "status": "rendering",
        "duration_hours": 6
    }
}
```

**Metrics emission:**
- Pushes synthetic metrics to Grafana Cloud via OpenTelemetry SDK
- Dashboards show real-time moving data
- Baseline "healthy" metrics at low frequency when idle

**Log emission:**
- Writes synthetic Loki logs via Grafana's Loki push API
- Contains realistic VFX error messages (Blender/Arnold/V-Ray style)

**Trace emission:**
- Optional: generates Tempo traces showing job execution paths

**Demo control:**
- `POST /simulator/trigger/{scenario_name}` — trigger failure manually
- `POST /simulator/reset` — reset to healthy state
- `GET /simulator/status` — current node/job status

### 5.2 Demo Script

1. Start simulator in "healthy" mode → Grafana shows green
2. Trigger `gpu_memory_exhaustion` on `node-7`
3. Within 30 seconds, Sentry detects queue depth spike
4. Pathologist reads logs → diagnoses GPU memory exhaustion
5. Quartermaster approves (preemptible GPUs cost $4.50)
6. Surgeon reroutes frames, spins up 2 preemptible instances
7. Dispatcher sends Slack summary + Grafana annotation
8. Simulator shows recovery → Grafana returns to green
9. **Elapsed time: ~90 seconds**

---

## 6. Tech Stack

| Layer | Technology |
|---|---|
| **Agent Platform** | Google ADK + Gemini Flash |
| **Observability** | Grafana Cloud (MCP server: `grafana/mcp-grafana`) |
| **Agent Tracing** | Vertex AI Experiments + Cloud Logging |
| **Infrastructure** | Google Cloud Run (3 services) |
| **Scheduling** | Cloud Scheduler (Sentry polling) |
| **Secrets** | Secret Manager |
| **Pipeline** | Synthetic render farm simulator (Python asyncio) |
| **Mock API** | Flask-based OpenCue API mock |
| **Local Dev** | `adk web` + docker-compose |

---

## 7. Infrastructure & Deployment

### 7.1 Cloud Run Services

**Simulator Service:**
- Image: Python 3.12 slim
- Entrypoint: `python simulator/main.py`
- Port: 8080
- Scaling: min=0, max=1 (only needs one instance)
- Environment: GRAFANA_URL, GRAFANA_API_KEY (from Secret Manager)

**Brain Service:**
- Image: Python 3.12 slim
- Entrypoint: `uvicorn brain.main:app --host 0.0.0.0 --port 8080` (FastAPI wrapper around ADK agents)
- Port: 8080
- Scaling: min=0, max=2
- Environment: GEMINI_API_KEY, GRAFANA_MCP_PATH, HANDS_SERVICE_URL

**Hands Service:**
- Image: Python 3.12 slim
- Entrypoint: `uvicorn hands.main:app --host 0.0.0.0 --port 8080` (FastAPI wrapper around ADK agents + Mock OpenCue router)
- Port: 8080
- Scaling: min=0, max=2
- Environment: GCP_PROJECT_ID, GCP_ZONE, SLACK_WEBHOOK_URL

### 7.2 Supporting GCP Services

**Cloud Scheduler:**
- Job: `GET https://brain-service/.../sentry/poll`
- Frequency: every 30 seconds
- Can be disabled when not demoing

**Cloud Logging:**
- All services log structured JSON
- Required fields: `trace_id`, `agent_name`, `step`, `latency_ms`, `tokens`, `severity`
- Query example: `trace_id="txn-abc123"`

**Vertex AI Experiments:**
- Each `trace_id` becomes an experiment run
- Metrics: agent_count, total_latency, total_cost, success_rate

**Secret Manager:**
- `secondunit/grafana-api-key`
- `secondunit/gemini-api-key`
- `secondunit/slack-webhook-url`
- `secondunit/gcp-service-account-key` (if needed)

### 7.3 IAM Roles

| Service | Role | Purpose |
|---|---|---|
| Brain | `roles/logging.logWriter` | Write structured logs |
| Brain | `roles/secretmanager.secretAccessor` | Read API keys |
| Hands | `roles/logging.logWriter` | Write structured logs |
| Hands | `roles/secretmanager.secretAccessor` | Read API keys |
| Hands | `roles/compute.instanceAdmin.v1` | Manage compute instances |
| Simulator | `roles/logging.logWriter` | Write logs |

### 7.4 Cost Estimate

| Resource | Estimated Cost |
|---|---|
| Cloud Run (3 services, testing only) | ~$6 |
| Cloud Scheduler | ~$0.10 |
| Cloud Logging | Free tier (50 GB/month) |
| Compute Engine (preemptible GPUs) | ~$15 |
| Vertex AI (Gemini API) | ~$5 |
| **Total** | **~$26-30** |
| **Buffer** | **~$45** |

**Cost controls:**
- All services scale to zero when idle
- Simulator only runs during active testing
- Preemptible instances auto-deleted after 15 minutes
- Daily budget alerts at $10

### 7.5 Local Development

**docker-compose.yml:**
- Simulator container
- Brain container
- Hands container
- Mock OpenCue container (or module in Hands)
- No GCP dependencies needed locally

**Local env:**
- Gemini Developer API key (free tier)
- Grafana Cloud free tier
- Mock OpenCue returns deterministic responses

---

## 8. Grafana MCP Integration Points

The agents actively call Grafana MCP tools at runtime:

| Tool | Agent | Purpose |
|---|---|---|
| `query_metrics` | Sentry | Detect queue depth, failure rate, CPU/GPU utilization |
| `query_metrics` | Pathologist | Correlate historical metrics |
| `query_metrics` | Quartermaster | Read cost dashboards |
| `query_logs` | Pathologist | Read Loki logs from affected nodes |
| `query_traces` | Pathologist | Trace job execution paths |
| `get_dashboard` | Sentry | Read render farm health dashboard state |
| `create_alert` | Dispatcher | Add human-review alert |
| `annotate_dashboard` | Dispatcher | Mark timeline with remediation event |
| `list_incidents` | Sentry | Check if anomaly is part of broader incident |

---

## 9. Observability & Logging

### 9.1 Structured Logging Format

Every agent decision is logged as structured JSON:

```json
{
  "trace_id": "txn-2026-08-14-abc123",
  "agent_name": "Pathologist",
  "step": "classify_failure",
  "timestamp": "2026-08-14T09:23:00Z",
  "input": {
    "anomaly": "GPU mem 98%",
    "affected_nodes": ["node-7"]
  },
  "output": {
    "diagnosis": "memory_exhaustion",
    "confidence": 0.94
  },
  "latency_ms": 1200,
  "tokens": 450,
  "severity": "INFO"
}
```

### 9.2 Traceability Requirements

- Every `trace_id` must be queryable across all services
- Each agent handoff is logged with `from_agent` and `to_agent`
- Every tool call is logged with arguments and response summary
- LLM outputs are logged (not just final decisions)
- Cost of each remediation is logged for audit

### 9.3 Dashboards

**Grafana:**
- Render farm health dashboard (from simulator data)
- Agent activity annotations

**Vertex AI Experiments:**
- Agent decision traces
- Success/failure rates by agent
- Average latency per agent
- Total token consumption

---

## 10. Testing Strategy

### 10.1 Unit Tests

- Each agent module tested independently with mocked tools
- Agent prompt tests (verify structured output schemas)
- Cost policy tests (verify approve/deny/escalate logic)

### 10.2 Integration Tests

- Local docker-compose: full pipeline from simulator → Brain → Hands
- Mock Grafana MCP responses for predictable testing
- Mock GCP API responses for Surgeon testing

### 10.3 Demo Verification

- Pre-recorded Grafana dashboard showing healthy baseline
- Scripted failure injection and expected agent responses
- Checklist: each agent fires, each tool is called, notification sent

---

## 11. Security & Privacy

### 11.1 Secret Management

- All API keys stored in Secret Manager
- No secrets in code or environment variables (except Secret Manager refs)
- Service accounts use least-privilege IAM roles

### 11.2 Network Security

- Cloud Run services use built-in HTTPS
- Brain→Hands communication authenticated via Cloud Run service account
- No public API exposed except Simulator trigger endpoint (for demo)

### 11.3 Data Handling

- Simulator generates synthetic data — no real production data
- Grafana logs contain only simulated node names and frame numbers
- No PII or sensitive VFX assets involved

---

## 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| ADK doesn't support multi-agent branching as needed | Medium | High | Fallback to custom state machine with python-genai |
| Grafana MCP server connection issues | Medium | High | Mock Grafana responses for local dev; have fallback alert mechanism |
| Gemini API rate limits | Low | Medium | Use Flash (higher rate limits); cache common responses |
| Cloud Run cold start latency | Medium | Low | Keep min instances=0; demo script accounts for ~5s warmup |
| GCP credit exhaustion | Low | High | Daily budget alerts; auto-shutdown after 15 min; synthetic data generator costs ~$0 |
| Demo day failure | Medium | High | Pre-record demo video as backup; have local docker-compose running offline |

---

## 13. Post-Hackathon Stretch Goals

### 13.1 Real OpenCue Deployment

**Effort estimate:** Medium-High (2-3 weekends)
- Deploy OpenCue server + worker on GKE
- Configure OpenCue REST API for agent integration
- Replace mock OpenCue module with real API calls
- Update Surgeon agent tools to call actual OpenCue endpoints

### 13.2 Additional Failure Scenarios

- Disk space exhaustion
- Network partition between nodes
- File permission errors
- Plugin version mismatches

### 13.3 Production Enhancements

- Persistent state store (Firestore) for long-running failures
- Real-time WebSocket dashboard for agent activity
- Integration with production render farm schedulers (Deadline, Tractor)
- Automated cost reporting and budget forecasting

---

## 14. Next Steps

1. ✅ Review hackathon rules and submission requirements
2. ✅ Set up GCP project and enable APIs
3. ✅ Set up Grafana Cloud free tier and enable MCP server
4. ⬜ Initialize ADK project structure
5. ⬜ Build Simulator service (synthetic data generator)
6. ⬜ Build Brain service (Sentry, Pathologist, Quartermaster)
7. ⬜ Build Hands service (Surgeon, Dispatcher, Mock OpenCue)
8. ⬜ Set up Cloud Run deployments
9. ⬜ Configure Cloud Scheduler and Secret Manager
10. ⬜ Wire Grafana dashboards and MCP tools
11. ⬜ Implement end-to-end integration tests
12. ⬜ Record demo video
13. ⬜ Write submission post

---

*Design approved by project owner on 2026-08-14.*
*Ready for implementation plan via writing-plans skill.*
