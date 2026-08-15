# SecondUnit Code Review — 2026-08-14

**Repository:** `sarahsl-prog/SecondUnit`  
**Branch reviewed:** `code-review` (HEAD: `bb2d24d`)  
**Reviewer:** OpenCode  
**Date:** 2026-08-14

---

## Executive Summary

SecondUnit is a multi-agent VFX render-farm health system for the Agentic Cinema hackathon. The codebase implements the architecture described in the design spec (three Cloud Run services: Simulator, Brain, Hands) and includes deterministic agents for detection (Sentry), diagnosis (Pathologist), cost gating (Quartermaster), remediation (Surgeon), and notification (Dispatcher). Most unit tests pass when invoked with the correct import mode, and the integration test demonstrates the happy path.

However, the repo has several **Critical** and **High** issues that block production-like reliability, break the documented quick-start, or introduce safety concerns. This review prioritizes them and provides concrete fixes.

---

## Critical Issues

### 1. Default `pytest` invocation fails collection for most test directories

**Priority:** Critical  
**Files:** `tests/__init__.py`, `simulator/tests/__init__.py`, `brain/tests/__init__.py`, plus root pytest behavior  
**Issue:** Running `pytest` (as documented in `README.md`) produces `ModuleNotFoundError` for `brain`, `hands`, `simulator`, and `tests.integration`. The root cause is that the project lacks top-level `__init__.py` files in some service packages and/or the interaction between `PYTHONPATH` and pytest's package discovery. The plan documents `pytest` as the test command, but it only succeeds when called with `pytest --import-mode=importlib`.  
**Impact:** New contributors cannot follow the README's quick-start. CI will fail unless custom flags are added.  
**Recommended Fix:**

- Add empty `__init__.py` files to `brain/`, `brain/tests/`, `hands/`, `hands/tests/`, `simulator/`, `simulator/tests/`, and ensure `tests/__init__.py` and `tests/integration/__init__.py` exist.
- Alternatively, add a `pytest.ini` or `pyproject.toml` `[tool.pytest.ini_options]` with `pythonpath = ["."]` and `testpaths = ["shared/tests", "brain/tests", "hands/tests", "simulator/tests", "tests/integration"]`.
- Document the exact test command in `README.md` and `DEMO.md`.
- Run `pytest` in CI with no extra flags to verify.

```toml
[tool.pytest.ini_options]
testpaths = [
    "shared/tests",
    "brain/tests",
    "hands/tests",
    "simulator/tests",
    "tests/integration",
]
pythonpath = ["."]
asyncio_mode = "auto"
```

---

### 2. `.python-version` pins 3.13 while Dockerfiles and `pyproject.toml` require 3.12

**Priority:** Critical  
**Files:** `.python-version`, `Dockerfile.*`, `pyproject.toml`, `uv.lock`  
**Issue:** The project root contains `.python-version` with `3.13`, but Dockerfiles use `FROM python:3.12-slim` and `pyproject.toml` requires `requires-python = ">=3.12"`. The mismatch means local `uv sync` may resolve a 3.13 venv while the deployment target is 3.12, risking dependency or wheel incompatibility.  
**Impact:** Non-deterministic local/dev parity; possible runtime surprises in Cloud Run.  
**Recommended Fix:**

- Align everything to a single Python version. Since the spec and Dockerfiles target 3.12, set `.python-version` to `3.12`.
- Update `requires-python` to `==3.12.*` or `>=3.12,<3.13` if strict parity is desired.
- Re-run `uv sync` and regenerate `uv.lock`.

---

### 3. `Dockerfile.*` are missing `apt` dependency for healthcheck `curl`

**Priority:** Critical  
**Files:** `Dockerfile.simulator`, `Dockerfile.hands`  
**Issue:** `docker-compose.yml` defines healthchecks using `curl`, but the `python:3.12-slim` base image does not include `curl` by default. The simulator and hands services will fail their Docker healthchecks, so `brain` and `hands` `depends_on` conditions will never be satisfied.  
**Impact:** `docker-compose up -d` hangs or reports unhealthy services; the demo cannot proceed.  
**Recommended Fix:**

Install `curl` in Dockerfiles before `CMD`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
```

Alternatively, replace `curl` healthchecks with lightweight Python/HTTPX invocations or use the base image's built-in `python -c` one-liner. The `brain` service has no `healthcheck` at all and depends on `simulator` being healthy — add one.

---

### 4. Docker compose service dependency chain is inverted/circular

**Priority:** Critical  
**File:** `docker-compose.yml`  
**Issue:**

- `brain` `depends_on` `simulator` with `condition: service_healthy`.
- `hands` `depends_on` `brain` with `condition: service_healthy`.
- But `brain` also needs to POST to `hands:8080` at runtime, while `hands` has no declared dependency on `brain` for its own startup.
- `brain` has no `healthcheck`, so `hands` can never satisfy its `depends_on` condition.

**Impact:** Compose will never finish startup in the documented order.  
**Recommended Fix:**

Remove the `condition: service_healthy` chains or make them acyclic. All three services can start independently (only runtime HTTP calls create dependencies). If ordering is desired for demo clarity, use `depends_on` without `condition` and add a small wait/health-poll script, or add healthchecks to all three and keep `condition: service_started` rather than `service_healthy`.

---

### 5. `brain/main.py` does not validate the incoming request body with Pydantic

**Priority:** Critical  
**File:** `brain/main.py`  
**Issue:** `brain/main.py` creates `RemediationRequest(...)` from a dict returned by `quartermaster.evaluate(diagnosis)`, but that dict contains a serialized `Approval` and `CostEstimate` from `.model_dump()`. `RemediationRequest(...)` accepts them as keyword arguments, but `approval` is a dict, not an `Approval` instance, so Pydantic will coerce it. However, `quartermaster.send_to_hands` then calls `remediation.model_dump(mode='json')`, which serializes datetimes to ISO strings. This is correct, but the route does not return a structured error if any step fails; it will return a 500 with a stack trace.  
**More importantly:** the `/sentry/poll` route is a `GET` but triggers a stateful side effect (Sentry poll + Pathologist + Quartermaster + Hands POST). Cloud Scheduler `GET` is fine, but accidental browser/crawler hits will fire the full remediation chain. There is no authentication or idempotency check.  
**Impact:** Accidental or malicious polling can repeatedly spin up preemptible instances and cost money; no way to distinguish legitimate scheduler calls.  
**Recommended Fix:**

- Change `/sentry/poll` to require a secret header (e.g., `X-Cloud-Scheduler: <token>`) or verify the Cloud Scheduler `User-Agent` in production.
- Add idempotency: log/cache the last `trace_id` and skip if the same anomaly was already sent within a cooldown window.
- Wrap the route body in try/except and return structured errors (e.g., `{"status": "error", "error": ...}`) with appropriate HTTP status codes.

---

## High Issues

### 6. `QuartermasterAgent` budget math ignores actual state and running budget

**Priority:** High  
**File:** `brain/agents/quartermaster.py`  
**Issue:** `budget_remaining_usd` is computed as `nightly_limit - current_estimate`. It does not track the *running* nightly spend. Two incidents each costing $4.50 will both be approved, even though the cumulative cost may exceed $50. The policy also has `max_instances: 4`, but `QuartermasterAgent` never enforces it.  
**Impact:** Budget policy is effectively a per-incident check, not a nightly limit. A runaway loop or repeated failures can exceed the declared $50 cap.  
**Recommended Fix:**

- Introduce a persistent spend tracker (e.g., a simple JSON file, Firestore, or in-memory guarded by a lock for single-instance demo) keyed by calendar day.
- Update `_estimate_cost` to respect `max_instances` from the policy.
- Compute `budget_remaining_usd = max(0, nightly_limit - today_spent - estimate)` and deny/escalate when negative.
- Add tests for cumulative spend and `max_instances` enforcement.

---

### 7. `SurgeonAgent` always reports `status: "success"` even when OpenCue or GCP calls fail

**Priority:** High  
**File:** `hands/agents/surgeon.py`  
**Issue:** `_call_opencue` catches `httpx.HTTPError` and returns `{"action": ..., "status": "failed", "error": ...}`. `execute()` appends that to `actions_taken` but still returns `status: "success"`. The design spec requires `partial_failure` when any action fails.  
**Impact:** Brain/operator believes remediation succeeded when it did not.  
**Recommended Fix:**

- After the loop, scan `actions_taken` for any entry with `status == "failed"`.
- Return `status: "partial_failure"` if some failed, `"success"` only if all succeeded, `"failure"` if all failed.
- Add a test covering the failed-OpenCue path and assert `partial_failure` is returned.

---

### 8. `SurgeonAgent` hardcodes `target_node="node-3"` without checking health

**Priority:** High  
**File:** `hands/agents/surgeon.py`  
**Issue:** The reroute action always sends `target_node: "node-3"`. In a real farm, node-3 may be the failing node itself, offline, or already overloaded. The design spec says reroute to "healthy nodes".  
**Impact:** Demo-only behavior that will mis-remediate in real scenarios.  
**Recommended Fix:**

- Accept a `healthy_nodes` list in `RemediationRequest.context` (populated by Sentry/Pathologist).
- Pick the first healthy node not in `affected_nodes`, or fall back to `"node-3"` only when no healthy list is provided.
- Add unit tests for healthy-node selection and the affected-node exclusion.

---

### 9. `SentryAgent` only checks `render_queue_depth` and ignores the GPU memory threshold the demo promises

**Priority:** High  
**File:** `brain/agents/sentry.py`, `DEMO.md`  
**Issue:** `DEMO.md` Step 3 says "Grafana detects the anomaly — GPU memory spiking on node-07" and Sentry flags the incident. The actual `SentryAgent.run()` only queries `render_queue_depth` and uses a hardcoded 80 threshold. It never queries `node_gpu_mem_percent`. Therefore the simulator's `gpu_memory_exhaustion` scenario (which sets `gpu_mem_percent: 99`) does not directly drive detection. Detection happens only because the mock `GrafanaMCPClient.query_metrics` always returns 98.5 for any query.  
**Impact:** Detection logic is not tied to the failure scenario it claims to monitor. In production or with a real Grafana backend, the demo would not work as scripted.  
**Recommended Fix:**

- Add separate metric queries for queue depth and GPU memory in `SentryAgent`.
- An anomaly is detected if either metric exceeds its threshold on any node.
- Include the actual metric name and value in `AnomalyReport`.
- Update tests to provide mock data for both metrics and assert detection on GPU memory spike.

---

### 10. `PathologistAgent` hardcodes diagnosis to `node-7` and `scene_47`

**Priority:** High  
**File:** `brain/agents/pathologist.py`  
**Issue:** `_query_logs` returns `CUDA out of memory` only when `"node-7" in nodes`. `run()` always sets `affected_frames=[1847, 1848]` and `scene="scene_47"` regardless of the input anomaly. The spec frames this as demo scaffolding, but it means the agent cannot generalize to any real failure.  
**Impact:** The system cannot be demoed with a different target node or scene without code changes.  
**Recommended Fix:**

- Derive affected frames from the simulator's actual job state (e.g., expose `/simulator/jobs` and query it).
- Use the `scene` field from the affected job or default to a deterministic scene only when data is missing.
- Keep the keyword-based log classification but source the log text from the mock Loki endpoint or from the simulator's `LogEmitter`.
- Add tests for `node-12`, `corrupt_scene_file`, `network_timeout`, and `license_failure` to ensure classification branches work.

---

### 11. `docker-compose.yml` `depends_on` blocks but no shared network or explicit `networks`

**Priority:** High  
**File:** `docker-compose.yml`  
**Issue:** Compose creates an implicit network by default, which is fine, but the `hands` service depends on `brain` being healthy while `brain` needs `hands` at runtime. Additionally, the simulator has no dependency on anything, which is fine, but `brain` references `hands:8080` while `hands` references nothing, so startup order matters only because of `depends_on`. The real problem is the circular dependency described in #4.  
**Impact:** Compose startup failure.  
**Recommended Fix:**

- Remove `condition: service_healthy` from all `depends_on` blocks, or add healthchecks to every service and use `condition: service_started` only where truly needed.
- Consider adding an explicit `networks: secondunit` block for clarity.

---

### 12. `infra/deploy.sh` Cloud Scheduler URL is wrong for Cloud Run

**Priority:** High  
**File:** `infra/deploy.sh`  
**Issue:** The scheduler URI is `https://brain-${REGION}.run.app/sentry/poll`. Cloud Run service URLs follow `https://<service-name>-<hash>-<region>.a.run.app`, not `https://brain-<region>.run.app`.  
**Impact:** Cloud Scheduler job will 404 after deployment.  
**Recommended Fix:**

- Capture the actual service URL after `gcloud run deploy` and use it for the scheduler job, e.g.:

```bash
BRAIN_URL=$(gcloud run services describe secondunit-brain --region="$REGION" --format='value(status.url)')
gcloud scheduler jobs create http "$SCHEDULER_JOB_ID" \
  --location="$REGION" \
  --schedule="*/1 * * * *" \
  --uri="${BRAIN_URL}/sentry/poll" \
  ...
```

- Also grant `roles/run.invoker` to the scheduler service account (`service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com`) so it can invoke the authenticated Cloud Run service.

---

### 13. `infra/iam.tf` grants Artifact Registry writer to runtime service account unnecessarily

**Priority:** High  
**File:** `infra/iam.tf`  
**Issue:** The `secondunit` service account is intended to run Cloud Run services, but it is granted `roles/artifactregistry.writer`. Cloud Build (using its own service account) pushes images; the runtime service account only needs reader or no Artifact Registry access at all if images are public/internal.  
**Impact:** Over-privileged runtime identity violates least privilege.  
**Recommended Fix:**

- Remove `artifact_registry_writer` binding for the runtime SA.
- If images are in Artifact Registry, reader access is sufficient (`roles/artifactregistry.reader`).
- Document which service account Cloud Build uses (usually the Compute default SA or a dedicated Cloud Build SA).

---

### 14. `hands/main.py` `/remediate` endpoint uses `request: dict` instead of Pydantic model

**Priority:** High  
**File:** `hands/main.py`  
**Issue:** Using `dict` bypasses FastAPI's automatic validation, documentation, and OpenAPI schema generation. Typos in the incoming JSON will produce 500 errors instead of 422 validation errors.  
**Impact:** Poor API contract, harder debugging, missing OpenAPI docs.  
**Recommended Fix:**

```python
from shared.types import RemediationRequest

@app.post("/remediate")
async def remediate(request: RemediationRequest):
    ...
```

Then update the route body to use `request` directly.

---

### 15. `shared/config.py` uses deprecated Pydantic `class Config` and env prefix mismatch

**Priority:** High  
**File:** `shared/config.py`  
**Issue:**

- `class Config:` is deprecated in Pydantic v2.
- `env_prefix = "SECONDUNIT_"` means fields are read as `SECONDUNIT_GEMINI_API_KEY`, but `.env.example` uses unprefixed names (`GEMINI_API_KEY`). In local docker-compose, `.env` is loaded directly into the container environment, so unprefixed variables work. In Cloud Run with Secret Manager via `--set-secrets`, secrets are injected as environment variables with unprefixed names too. The prefix therefore breaks the documented config.

**Impact:** Environment variables in `.env.example` and the spec do not match `Config` semantics.  
**Recommended Fix:**

- Remove `env_prefix = "SECONDUNIT_"` or update `.env.example` and all docs to use `SECONDUNIT_*` variables.
- Migrate to `model_config = SettingsConfigDict(env_file=".env")`.
- Add a test that instantiates `Config` with representative env vars.

---

## Medium Issues

### 16. `pytest.ini_options` missing; lint/type-check not wired into CI

**Priority:** Medium  
**File:** `pyproject.toml`  
**Issue:** There is no `[tool.pytest.ini_options]` section, no `ruff`/`mypy` config, and no GitHub Actions or Cloud Build test step.  
**Impact:** Tests are not reproducible across environments; style/type drift will accumulate.  
**Recommended Fix:**

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["shared/tests", "brain/tests", "hands/tests", "simulator/tests", "tests/integration"]
pythonpath = ["."]
asyncio_mode = "auto"

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "UP", "SIM", "RUF", "PIE"]

[tool.mypy]
python_version = "3.12"
strict = true
explicit_package_bases = true
mypy_path = "."
```

Then run `ruff check . --fix` and `mypy` after adding `__init__.py` files and a mypy path.

---

### 17. `mypy` cannot run because of duplicate `main` modules and missing package roots

**Priority:** Medium  
**File:** whole repo  
**Issue:** `mypy brain hands simulator shared tests` fails with "Duplicate module named 'main'" because `brain/main.py`, `hands/main.py`, and `simulator/main.py` share a bare module name without explicit package bases.  
**Impact:** Static type checking is unavailable.  
**Recommended Fix:**

- Add `__init__.py` to `brain/`, `hands/`, `simulator/` and run `mypy` with `explicit_package_bases = true` and `mypy_path = "."`.
- Alternatively run `mypy --explicit-package-bases --python-version 3.12 brain hands simulator shared`.

---

### 18. `GrafanaMCPClient` is a hardcoded mock and ignores `url`/`api_key`

**Priority:** Medium  
**File:** `brain/tools/grafana_mcp.py`  
**Issue:** `query_metrics`, `get_dashboard`, and `list_incidents` return static JSON regardless of inputs. The `url`, `api_key`, and `httpx.AsyncClient` are never used to make real requests.  
**Impact:** The "Grafana MCP integration" is not actually implemented; the demo relies entirely on fake data.  
**Recommended Fix:**

- Implement real Grafana API calls for the demo-critical endpoints, guarded by a feature flag or fallback to mock when `GRAFANA_URL` is empty.
- Add tests with `respx`/`pytest-httpx` to assert request headers, query params, and response parsing.
- Document that the current implementation is a stub in `README.md` until the real MCP server is wired.

---

### 19. `MetricsEmitter` and `LogEmitter` are empty stubs

**Priority:** Medium  
**Files:** `simulator/metrics.py`, `simulator/logs.py`  
**Issue:** The simulator never emits real metrics or logs to Grafana. The dashboard JSON expects metrics like `render_queue_depth` and `node_gpu_mem_percent`, but nothing sends them.  
**Impact:** Grafana dashboard will be empty; the demo cannot show real data.  
**Recommended Fix:**

- Implement OpenTelemetry push to Grafana's OTLP endpoint or Prometheus remote-write in `MetricsEmitter`.
- Implement Loki push in `LogEmitter`.
- At minimum, log metrics to stdout in a scrapeable format (e.g., Prometheus exposition) so a local Prometheus/Grafana stack can consume them.
- Add tests verifying that `emit_node_metrics` and `emit_log` produce expected output.

---

### 20. `Approval.timestamp` uses deprecated `datetime.utcnow()`

**Priority:** Medium  
**File:** `shared/types.py`  
**Issue:** `Field(default_factory=datetime.utcnow)` triggers a `DeprecationWarning` on Python 3.12+.  
**Impact:** Future Python versions will remove `utcnow()`.  
**Recommended Fix:**

```python
from datetime import datetime, timezone

timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

Apply the same fix to `AgentLog.timestamp`.

---

### 21. `shared/logger.py` side effects at import time

**Priority:** Medium  
**File:** `shared/logger.py`  
**Issue:** The module configures `logging` and `structlog` when imported. This is convenient but surprising in tests and can interfere with other loggers.  
**Impact:** Hard to unit-test in isolation; may duplicate handlers if imported multiple times.  
**Recommended Fix:**

- Move configuration into a `configure_logging()` function called from each service's `main.py` at startup.
- Keep `get_logger()` as a thin wrapper.
- Guard the global setup with `if not logging.getLogger().handlers:` (already partially done) but avoid `setLevel` side effects at import.

---

### 22. `hands/agents/surgeon.py` `ACTION_MAP` is a mutable class attribute

**Priority:** Medium  
**File:** `hands/agents/surgeon.py`  
**Issue:** `ACTION_MAP` is defined as a class-level dict. If any instance mutates it, all instances are affected. `ruff` already flags this as `RUF012`.  
**Impact:** Potential accidental global mutation.  
**Recommended Fix:**

- Move `ACTION_MAP` into the instance inside `__init__`, or annotate it with `typing.ClassVar[dict[str, list[str]]]` and never mutate it.

```python
from typing import ClassVar

class SurgeonAgent:
    ACTION_MAP: ClassVar[dict[str, list[str]]] = {...}
```

---

### 23. `QuartermasterAgent.send_to_hands` has no retry/backoff

**Priority:** Medium  
**File:** `brain/agents/quartermaster.py`  
**Issue:** The design spec (§3.3) says Quartermaster retries with exponential backoff (max 3 attempts) and falls back to a Brain-based Dispatcher after 3 failures. The code raises immediately on the first `httpx.HTTPError`.  
**Impact:** Transient network blips between Brain and Hands cause the entire remediation to fail.  
**Recommended Fix:**

- Add a retry loop with exponential backoff (e.g., using `tenacity` or a manual loop).
- On exhaustion, call a local Dispatcher fallback to notify humans with `error_type: "hands_unreachable"`.
- Add a test that simulates 2 failures then success, and another that tests the fallback.

---

### 24. `DispatcherAgent` Slack result hardcodes `"mock-ts"`

**Priority:** Medium  
**File:** `hands/agents/dispatcher.py`  
**Issue:** `_send_slack` always returns `{"ts": "mock-ts", "ok": True}` on success, ignoring the real Slack API response. The test asserts this value, masking the bug.  
**Impact:** Real Slack message timestamp is lost; future threads/reactions cannot reference it.  
**Recommended Fix:**

- Return the parsed JSON from Slack: `resp.json()` (e.g., `{"ok": True, "ts": "..."}`).
- Update the test to patch the response JSON and assert the actual timestamp is propagated.

---

### 25. Missing tests for escalation/deny paths and non-GPU failures

**Priority:** Medium  
**Files:** `brain/tests/`, `hands/tests/`  
**Issue:**

- `test_quartermaster` only tests the approve path.
- No test for `deny`/`escalate`, cumulative cost, or `license_failure`/`network_timeout`.
- No test for `SurgeonAgent` when `gcp` is `None`.
- No test for `DispatcherAgent` Grafana annotation path.

**Impact:** Regressions in important branches will not be caught.  
**Recommended Fix:**

Add parameterized tests covering all failure types and Quartermaster decisions. Add tests for partial failure and missing Slack/Grafana config.

---

### 26. `docker-compose.yml` exposes services on different ports than README says

**Priority:** Medium  
**File:** `README.md`, `DEMO.md`, `docker-compose.yml`  
**Issue:** `README.md` says `curl -X POST http://localhost:8081/simulator/trigger/gpu_memory_exhaustion`, which matches `docker-compose.yml` (simulator `8081:8080`). But `DEMO.md` also references `localhost:8082/opencue/jobs`, which is wrong — the OpenCue mock lives in `hands` on port `8083`, not `brain` on 8082.  
**Impact:** Demo script has an incorrect command.  
**Recommended Fix:**

- Change `DEMO.md` Step 6 `curl http://localhost:8082/opencue/jobs` to `curl http://localhost:8083/opencue/reroute` (or the correct hands port and endpoint).
- Audit all `localhost:808X` references in docs for consistency.

---

### 27. `pyproject.toml` description is a placeholder

**Priority:** Medium  
**File:** `pyproject.toml`  
**Issue:** `description = "Add your description here"`.  
**Impact:** Looks unprofessional in package metadata.  
**Recommended Fix:**

```toml
description = "VFX render farm health agent using Grafana MCP and Google ADK"
```

---

## Low Issues

### 28. `Optional` imported but unused in several modules

**Priority:** Low  
**Files:** `brain/agents/pathologist.py`, `brain/agents/sentry.py`, `brain/tools/grafana_mcp.py`  
**Issue:** Lint noise; no functional impact.  
**Recommended Fix:** Run `ruff check . --fix`.

---

### 29. Import ordering is inconsistent across modules

**Priority:** Low  
**Files:** most Python files  
**Issue:** Standard library, third-party, and local imports are interleaved.  
**Recommended Fix:** Enforce `isort`/ruff I001 rules in CI and auto-fix.

---

### 30. `shared/exceptions.py` defines exceptions that are never raised

**Priority:** Low  
**File:** `shared/exceptions.py`  
**Issue:** `AgentTimeout`, `HandsUnreachable`, and `BudgetExceeded` are defined but never used in the code.  
**Recommended Fix:** Either start raising them in the appropriate places (e.g., `BudgetExceeded` on deny, `HandsUnreachable` after retries, `AgentTimeout` with timeout wrappers) or remove them if not needed.

---

### 31. `simulator/engine.py` imports `DEFAULT_SCENES` but never uses it

**Priority:** Low  
**File:** `simulator/engine.py`  
**Issue:** Dead import.  
**Recommended Fix:** Remove the import or use `DEFAULT_SCENES` to seed realistic jobs during simulator startup.

---

### 32. `shared/types.py` still uses `typing.List`

**Priority:** Low  
**File:** `shared/types.py`  
**Issue:** Python 3.12+ supports `list[str]` natively.  
**Recommended Fix:** Replace `List` with `list` and remove the import.

---

## Outstanding Technical Decisions / Clarifications Needed

1. **Grafana MCP implementation scope:** Is the hackathon demo allowed to rely on mocked Grafana data, or must the MCP server be fully wired before submission? The code is currently all stubs except dashboard JSON.
2. **Budget state storage:** The design mentions a nightly budget but provides no persistence. Should the prototype track spend in memory, in a file, or skip it for the demo and document the limitation?
3. **Cloud Run service identities:** `deploy.sh` creates a `secondunit` service account but Cloud Build deploys with `--allow-unauthenticated` and does not bind the runtime SA to the services. Should services run as the Compute default SA or the dedicated `secondunit` SA? If the latter, `--service-account=` must be added to each `gcloud run deploy` step.
4. **OpenCue mock vs. real:** The design lists real OpenCue integration as a post-hackathon stretch goal. Should the current mock be treated as the target for submission, and if so, should `/opencue` endpoints be documented as mock-only?
5. **Python version strategy:** The Dockerfiles pin 3.12 but `.python-version` says 3.13. Should the project standardize on 3.12 or 3.13?
6. **Test discovery policy:** Should tests be run with `pytest --import-mode=importlib` indefinitely, or should the package structure be fixed so plain `pytest` works?
7. **Authentication on `/sentry/poll`:** Cloud Scheduler invokes the public endpoint. Should the demo rely on `--allow-unauthenticated`, or should a secret token be required? The design spec mentions Cloud Run service-account authentication for Brain→Hands but does not detail Scheduler→Brain.
8. **Cost of real GCP actions:** `GCPComputeClient` is a stub. If the demo runs against a real GCP project, spinning up preemptible instances must be gated. Should the deploy script default to dry-run mode outside of demo time?
9. **Failure scenario coverage:** The design spec lists five scenarios. The simulator implements all five, but only `gpu_memory_exhaustion` is exercised end-to-end. Should tests be added for the other four before demo day?
10. **Slack vs. Grafana annotation priority:** When Slack URL or Grafana key is missing, `DispatcherAgent` silently skips that channel. Should it escalate to a logged warning or a human fallback when *no* notification channel is configured?

---

## Summary Table

| Priority | Count | Main Themes |
|---|---|---|
| Critical | 5 | Test invocation broken, Python/Docker version mismatch, Docker healthchecks/compose broken, unauthenticated stateful GET endpoint |
| High | 10 | Budget logic, partial-failure reporting, hardcoded remediation, detection not tied to GPU metric, deployment URL errors, config mismatch, IAM over-provisioning, request validation |
| Medium | 9 | Tooling config, type checking, Grafana/Loki stubs, missing tests, doc inconsistencies |
| Low | 5 | Lint/style noise, unused imports/exceptions |

**Total issues:** 29

---

*End of review.*
