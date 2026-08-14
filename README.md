# SecondUnit

**VFX Render Farm Health Agent**

A multi-agent system that monitors, diagnoses, and remediates failures in VFX/animation render farms. Built for the [Agentic Cinema: The Blockbuster Hackathon](https://agentic-cinema.devpost.com/) (Grafana track).

SecondUnit combines **Grafana Cloud** (observability via MCP) with **Gemini + Google ADK** (orchestration and reasoning) to create a deterministic, multi-step agentic workflow:

> **Detection → Diagnosis → Cost-Gating → Remediation → Human Notification**

## The Problem

Animation and VFX houses run render farms that process thousands of frames per scene. Jobs fail silently, artists waste hours waiting, and production coordinators manually check dashboards. SecondUnit automates the entire cycle.

## Architecture

Three Cloud Run services work together:

- **Simulator** — Generates synthetic render farm metrics and logs (emits to Grafana Cloud)
- **Brain** — Runs the "thinking" agents: Sentry (detect), Pathologist (diagnose), Quartermaster (cost-gate)
- **Hands** — Runs the "acting" agents: Surgeon (remediate), Dispatcher (notify humans)

Brain and Hands communicate via structured HTTP POST with full audit logging.

## Tech Stack

| Layer | Technology |
|---|---|
| Agent Platform | Google ADK + Gemini Flash |
| Observability | Grafana Cloud (MCP server) |
| Agent Tracing | Vertex AI Experiments + Cloud Logging |
| Infrastructure | Google Cloud Run |
| Scheduling | Cloud Scheduler |
| Secrets | Secret Manager |
| Simulation | Python asyncio + OpenTelemetry |
| Mock API | FastAPI (OpenCue API mock) |
| Local Dev | docker-compose |

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd SecondUnit

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys

# 3. Install dependencies (uv)
uv sync

# 4. Start local services
docker-compose up -d

# 5. Run tests
pytest

# 6. Trigger a demo failure
curl -X POST http://localhost:8081/simulator/trigger/gpu_memory_exhaustion
```

## Documentation

- [Design Specification](docs/superpowers/specs/2026-08-14-secondunit-design.md)
- [Implementation Plan](docs/superpowers/plans/2026-08-14-secondunit-plan.md)
- [Grafana Dashboard](docs/dashboards/render-farm.json)

## Deploy to GCP

```bash
export GCP_PROJECT_ID=your-project-id
export GEMINI_API_KEY=...
export GRAFANA_API_KEY=...
export SLACK_WEBHOOK_URL=...
bash infra/deploy.sh
```

## Demo

See [DEMO.md](DEMO.md) for the full 90-second demo script.

## License

MIT — see [LICENSE](LICENSE).

## Author

Sarah Sund-Lussier
