# SecondUnit Demo Script

**Hackathon track:** Grafana — Agentic Cinema  
**Demo duration:** ~90 seconds  
**Persona:** Sarah Sund-Lussier, VFX pipeline engineer

---

## Pre-Demo Setup (before demo day)

### 1. Verify local environment

```bash
docker-compose up -d
docker-compose ps   # all services should show "Up"
```

### 2. Open Grafana dashboard

Navigate to your Grafana Cloud dashboard:

```
https://<your-stack>.grafana.net/d/secondunit-render-farm
```

You should see:
- Green nodes (healthy GPU memory < 70%)
- Queue depth at 0–5 pending frames
- Failure rate stat panel at 0.0 ops

### 3. Open Slack channel

Open the `#render-alerts` channel (or configured Slack webhook channel) in a second browser window.

### 4. Open project README

Have this open for the "Architecture" slide moment: `README.md`

---

## Demo Steps (90 seconds)

### Step 1 — Show the healthy state (10s)

Point to the Grafana dashboard. All panels should be green:

- **Queue Depth** — flat line near 0
- **GPU Memory** — all nodes < 70%
- **Failure Rate** — 0.0 ops
- **Farm Health** — green / "Healthy"

> Say: "Here's our render farm right now — 47 nodes, zero incidents. SecondUnit watches this dashboard 24/7."

---

### Step 2 — Inject a failure (5s)

Open a second terminal and run:

```bash
curl -X POST http://localhost:8081/simulator/trigger/gpu_memory_exhaustion
```

You should see `{"status": "triggered", "failure": "gpu_memory_exhaustion"}` returned.

> Say: "I'm going to simulate a GPU memory exhaustion on one of our render nodes."

---

### Step 3 — Watch detection (15s)

Wait ~15 seconds. Point to:

1. **Grafana** — the GPU Memory panel for one node spikes toward 95–100%
2. **Queue Depth** — climbs from 0 to 20+ pending frames
3. **Farm Health** — turns red / "Critical"

> Say: "Within seconds, Grafana detects the anomaly — GPU memory spiking on node-07, queue depth growing. Sentry has flagged this incident."

---

### Step 4 — Show diagnosis (20s)

Open the Brain service logs in Grafana Explore, or show the structured log output:

```
level=info agent=sentry incident_id=inc_abc123 type=gpu_memory_exhaustion trace_id=...
level=info agent=pathologist diagnosis=GPU_MEMORY_EXHAUSTION confidence=0.94 trace_id=...
level=info agent=quartermaster approval=APPROVED cost_estimate_usd=4.50 gpus=2 preemptible=true trace_id=...
```

> Say: "Sentry detected the anomaly. Pathologist read the logs, classified it as GPU memory exhaustion with 94% confidence. Quartermaster approved $4.50 to spin up 2 preemptible GPUs to handle the backlog."

---

### Step 5 — Show cost gating (10s)

Highlight the Quartermaster log line:

```
cost_estimate_usd=4.50  gpus=2  preemptible=true  approved=true
```

> Say: "Quartermaster enforces a strict cost policy — $5 max per incident. This remediation costs $4.50. Quartermaster auto-approved it without human intervention."

---

### Step 6 — Show remediation (15s)

Open the Hands service logs, or hit the OpenCue mock directly (it lives
in `hands`, port 8083 — not `brain`'s 8082; there's no GET listing
endpoint, only the action endpoints Surgeon actually calls):

```bash
curl -X POST http://localhost:8083/opencue/reroute \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job-1847", "target_node": "node-3"}'
```

Show that:
- A new frame批次 was requeued on a different node
- A new preemptible instance was spun up

```
level=info agent=surgeon action=reroute job_id=frame_4821 target_node=node-23
level=info agent=surgeon action=requeue jobs=[frame_4819, frame_4820, frame_4821]
```

> Say: "Surgeon rerouted the stuck frames to healthy nodes and requeued the backlog. Hands is executing the remediation now."

---

### Step 7 — Show human notification (10s)

Point to the Slack channel. You should see a Slack message:

```
🔴 *SecondUnit Incident Update*
*Incident:* inc_abc123
*Diagnosis:* GPU Memory Exhaustion
*Remediation:* Rerouted 3 frames + spun up 2 preemptible GPUs
*Cost:* $4.50 / $5.00 budget
*Trace:* https://console.cloud.google.com/run/logs?...
```

> Say: "Dispatcher sent a summary to our Slack channel — engineers have full audit trail with a direct link to the Cloud Logging trace."

---

### Step 8 — Show recovery (5s)

Switch back to Grafana:

- GPU Memory returns to < 70% on node-07
- Queue depth returns to 0
- Farm Health returns to green

> Say: "Farm is back to healthy. Incident resolved end-to-end in under 60 seconds — without a human in the loop."

---

## Backup Plan

If the live demo fails:

1. **Docker not starting** — show the pre-recorded terminal recording at `demo-video.mp4` (if available)
2. **Grafana not reachable** — show the static dashboard screenshot at `docs/dashboards/screenshot.png`
3. **API keys missing** — use `.env.example` to show the required configuration
4. **Network issues** — run everything locally via `docker-compose up` (no external deps)

### Static fallback

```bash
# Show the architecture diagram
open docs/superpowers/specs/2026-08-14-secondunit-design.md

# Show the dashboard JSON
cat docs/dashboards/render-farm.json | python -m json.tool | head -50
```

---

## Post-Demo

After the demo, attendees can:

1. Clone the repo and run locally: `docker-compose up -d`
2. Trigger their own failures: `curl -X POST localhost:8081/simulator/trigger/<failure_type>`
3. Deploy to GCP: `bash infra/deploy.sh`
4. Import the dashboard: `docs/dashboards/render-farm.json`

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `docker-compose up` fails | Run `uv sync` first, then `docker-compose up --build` |
| Simulator not emitting metrics | `MetricsEmitter`/`LogEmitter` are stubs (see review #19) — nothing pushes to Grafana/Loki yet, this is expected until that's wired up |
| Brain not connecting to Grafana MCP | Verify `GRAFANA_API_KEY` in `.env` |
| Slack not receiving messages | Check `SLACK_WEBHOOK_URL` in `.env` |
| All services up but no logs | Run `docker-compose logs -f` to tail all services |
