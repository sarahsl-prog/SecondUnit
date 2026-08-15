# SecondUnit Code Review — To-Do

Source: `docs/Code-review-Aug14.md`. All 32 findings verified against the actual codebase on `impl-review-fixes` (2026-08-15) — every one is real and the recommended fix is technically sound. Checklist below tracks implementation.

**Doc bug (not code):** the review's Summary Table says Medium=9/Total=29, but the body lists 12 Medium issues (#16–#27) and 32 total. Fix the table when this doc is closed out.

---

## Critical

- [x] **#1 — `pytest` collection broken.** Add `__init__.py` to `brain/`, `hands/`, `simulator/`, `brain/tests/` (confirmed missing — `shared/`, `shared/tests/`, `hands/tests/`, `simulator/tests/`, `tests/`, `tests/integration/`, `hands/routers/` already have them). Add `[tool.pytest.ini_options]` to `pyproject.toml` (`testpaths`, `pythonpath = ["."]`, `asyncio_mode = "auto"`) — currently absent. Verify plain `pytest` passes with no flags. Update README/DEMO test command.
- [x] **#2 — Python version mismatch.** `.python-version` = 3.13, Dockerfiles + `pyproject.toml` = 3.12 (confirmed). Set `.python-version` to `3.12`, re-run `uv sync`, regenerate `uv.lock`.
- [x] **#3 — `curl` missing in Dockerfiles.** `Dockerfile.simulator`/`Dockerfile.hands` have no `apt-get install curl`, but `docker-compose.yml` healthchecks use `curl -f http://localhost:8080/health` (confirmed). Install curl or switch healthcheck to a Python one-liner. Also confirmed: `brain` service has **no healthcheck block at all**.
- [x] **#4 — Circular/broken compose dependency chain.** Confirmed: `brain` depends_on `simulator` (healthy), `hands` depends_on `brain` (healthy) — but `brain` has no healthcheck, so `hands` can never start via that condition. Remove `condition: service_healthy` chains or add a healthcheck to `brain` and reconsider whether the chain should exist at all (runtime dependency is HTTP calls, not startup order).
- [x] **#5 — Unauthenticated stateful `GET /sentry/poll`.** Confirmed: no header/token check, no idempotency, and errors will surface as unhandled 500s (no try/except in the route). Add secret-header or Scheduler User-Agent check, add trace_id cooldown/idempotency, wrap in try/except with structured error responses.

## High

- [x] **#6 — Quartermaster budget ignores running spend.** Confirmed: `budget_remaining_usd = nightly_limit - cost.estimated_cost_usd` in `evaluate()`, no persisted daily total. `max_instances` (in `cost_policy.yaml`, confirmed present at `preemptible_gpu.max_instances: 4`) is never read by `_estimate_cost`. Add a spend tracker keyed by day + enforce `max_instances`; add cumulative-spend tests.
- [x] **#7 — Surgeon always reports `"success"`.** Confirmed in `hands/agents/surgeon.py::execute()` — `actions_taken` can contain `status: "failed"` entries (from `_call_opencue`'s except branch) but the return is hardcoded `"status": "success"`. Scan actions, return `partial_failure`/`failure` as appropriate; add a failed-OpenCue test.
- [x] **#8 — Surgeon hardcodes `target_node="node-3"`.** Confirmed, no health check. Accept `healthy_nodes` from `RemediationRequest.context`, pick first not in `affected_nodes`, fall back to `"node-3"` only if list absent.
- [x] **#9 — Sentry ignores GPU memory metric.** Confirmed: `SentryAgent.run()` only queries `render_queue_depth{job="render_farm"}` with hardcoded threshold 80; never queries `node_gpu_mem_percent` despite `DEMO.md` describing GPU-memory detection. Detection only "works" because `GrafanaMCPClient.query_metrics` mock always returns 98.5 regardless of query string. Add a second metric query + threshold, detect on either.
- [x] **#10 — Pathologist hardcodes `node-7`/`scene_47`/frames.** Confirmed in `_query_logs` (only branches on `"node-7" in nodes`) and `run()` (`affected_frames=[1847,1848]`, `scene="scene_47"` are literal, unconditional). Derive from simulator job state; add tests for `node-12`, `corrupt_scene_file`, `network_timeout`, `license_failure`.
- [x] **#11 — Compose `depends_on` circularity** — same root cause as #4; fold into that fix. Consider explicit `networks:` block for clarity (optional, not required for correctness — default bridge network already lets services resolve each other by name).
- [x] **#12 — `deploy.sh` Cloud Scheduler URL wrong.** Confirmed literal string `https://brain-${REGION}.run.app/sentry/poll` (and the two "deployed successfully" URLs at the bottom) — not a valid Cloud Run URL format. Capture real URL via `gcloud run services describe --format='value(status.url)')` and use it for both the scheduler job and the final echo. Also grant `roles/run.invoker` to the Scheduler service agent.
- [x] **#13 — Runtime SA over-privileged.** Confirmed in `infra/iam.tf`: `secondunit` SA gets both `artifactregistry.reader` **and** `artifactregistry.writer`. Drop the writer binding — Cloud Build pushes images, runtime SA only needs pull/read.
- [x] **#14 — `hands/main.py` `/remediate` takes `request: dict`.** Confirmed — no Pydantic validation on the route signature (it's constructed manually inside the body via `RemediationRequest(**request)`, so malformed input still 500s instead of getting a 422 at the FastAPI layer). Change signature to `request: RemediationRequest`.
- [x] **#15 — `shared/config.py` deprecated `class Config` + prefix mismatch.** Confirmed: `class Config: env_prefix = "SECONDUNIT_"` (Pydantic v1-style, deprecated in v2) and `.env.example` uses unprefixed names (`GEMINI_API_KEY` not `SECONDUNIT_GEMINI_API_KEY`). Migrate to `model_config = SettingsConfigDict(...)`, drop or reconcile the prefix — **see outstanding question below, this needs a decision, not just a fix.**

## Medium

- [x] **#16 — No `pytest.ini_options`/ruff/mypy config, no CI.** Confirmed absent from `pyproject.toml`. Add config block from review; wire into CI once one exists.
- [x] **#17 — `mypy` duplicate `main` module.** Confirmed: `brain/main.py`, `hands/main.py`, `simulator/main.py` share bare name, no package roots declared. Fixed by #1's `__init__.py` additions + `explicit_package_bases = true`.
- [ ] **#18 — `GrafanaMCPClient` fully mocked.** Confirmed: `query_metrics`, `get_dashboard`, `list_incidents` all return static literals; `url`/`api_key`/`httpx.AsyncClient` constructed but never used. Real implementation is a scope decision — **see outstanding questions.**
- [ ] **#19 — `MetricsEmitter`/`LogEmitter` are no-op stubs.** Confirmed — both methods are `pass`. Same scope question as #18.
- [x] **#20 — `datetime.utcnow()` deprecated.** Confirmed in both `Approval.timestamp` and `AgentLog.timestamp` (`shared/types.py`). Replace with `lambda: datetime.now(timezone.utc)` in both places.
- [x] **#21 — `shared/logger.py` import-time side effects.** Confirmed: `structlog.configure(...)` and root-logger setup run at module scope. Move into a `configure_logging()` called from each `main.py`.
- [x] **#22 — `SurgeonAgent.ACTION_MAP` mutable class attr.** Confirmed, plain dict, no `ClassVar` annotation. Annotate `ClassVar[dict[str, list[str]]]`.
- [x] **#23 — `Quartermaster.send_to_hands` no retry.** Confirmed: `except httpx.HTTPError` logs and immediately `raise`s, no backoff loop, no Dispatcher fallback despite spec §3.3. Add retry (tenacity or manual) + fallback notify path.
- [x] **#24 — Dispatcher hardcodes `"mock-ts"`.** Confirmed in `_send_slack` — real `resp.json()` from Slack is discarded. Return the parsed response instead.
- [x] **#25 — Missing tests for escalate/deny/non-GPU paths.** Confirmed: `test_quartermaster.py` only has the approve-path test shown above. No deny/escalate/cumulative-cost test, no `gcp=None` Surgeon test, no Dispatcher Grafana-annotation test. Add parameterized coverage.
- [x] **#26 — Doc port mismatch.** Confirmed: `DEMO.md:113` says `curl http://localhost:8082/opencue/jobs`; OpenCue mock actually lives on `hands` (port 8083 per `docker-compose.yml`), and the router is `opencue.router` not a `/jobs` path — verify the correct endpoint name when fixing (review suggests `/opencue/reroute`, confirm against `hands/routers/opencue.py`). `README.md`/`DEMO.md:61` simulator references (8081) are correct as-is.
- [x] **#27 — Placeholder package description.** Confirmed: `pyproject.toml:4` = `"Add your description here"`. Replace with real description.

## Low

- [x] **#28 — Unused `Optional` imports.** Confirmed in `brain/agents/pathologist.py`, `brain/agents/sentry.py` (both import but never use `Optional`); review also names `brain/tools/grafana_mcp.py` — worth double-checking that one specifically since `Optional` is used there in a type hint (`get_dashboard`/method signatures) — re-verify before blindly running `ruff --fix`.
- [x] **#29 — Inconsistent import ordering.** Confirmed generally true across files (e.g. `random` after local imports in sentry.py/pathologist.py). Run `ruff --fix` with `I001` once #16 lands.
- [x] **#30 — Unused exceptions.** Confirmed: `AgentTimeout`, `HandsUnreachable`, `BudgetExceeded` defined in `shared/exceptions.py`, never raised or imported elsewhere. Wire them in (`BudgetExceeded` on deny, `HandsUnreachable` after #23's retry exhaustion, `AgentTimeout` on timeout wrappers) or delete.
- [x] **#31 — Dead `DEFAULT_SCENES` import.** (Resolved as a side effect of #10 — DEFAULT_SCENES is now used to seed the default scene name in trigger_scenario().) Confirmed in `simulator/engine.py:5`, imported, never referenced elsewhere in the file. Remove or use to seed jobs at startup.
- [x] **#32 — `typing.List` instead of `list`.** Confirmed throughout `shared/types.py` (`List[str]`, `List[int]` used 4x). Replace with builtin generics, drop the import.

---

## Outstanding Decisions — RESOLVED 2026-08-15

All 10 questions from the review's "Outstanding Technical Decisions" section are now decided. Checklist items above updated to match where the decision changes the fix.

| # | Question | Decision |
|---|---|---|
| 1 | Grafana MCP scope | **Implement real API calls** before submission (not mock-only). Changes #18/#19 from "document as stub" to "wire real Grafana + Loki calls." |
| 2 | Budget state storage | **Persistent** (file or Firestore), not in-memory. Changes #6 — needs a real store, not a module-level dict. |
| 3 | Cloud Run service identities | **Dedicated `secondunit` SA.** Add `--service-account=secondunit@$PROJECT_ID.iam.gserviceaccount.com` to each `gcloud run deploy` step in `deploy.sh`/`cloudbuild.yaml` — currently missing, so iam.tf's SA is provisioned but unused. New action item, see below. |
| 4 | OpenCue mock vs. real | **Mock is the submission target.** Document `/opencue` endpoints as mock-only in README (folds into #18/#26 doc cleanup). |
| 5 | Python version strategy | **Standardize on 3.12** — matches #2's fix as written. |
| 6 | Test discovery policy | **Fix package structure** so plain `pytest` works — matches #1's fix as written. |
| 7 | Auth on `/sentry/poll` | **Secret header/token required**, not `--allow-unauthenticated` — matches #5's fix as written. |
| 8 | Cost of real GCP actions | **Dry-run by default.** New action item: add `ENABLE_REAL_GCP_ACTIONS` (or `DRY_RUN`) flag to `GCPComputeClient`/`Config`, default off, gate `start_preemptible_instances` on it. |
| 9 | Failure scenario coverage | **Cover all 5 scenarios end-to-end**, not just `gpu_memory_exhaustion` — reinforces #10/#25, extend to `corrupt_scene_file`, `network_timeout`, `license_failure`, and the 5th scenario (check `simulator/failures.py` for its name) through Pathologist → Quartermaster → Surgeon → Dispatcher. |
| 10 | Slack/Grafana missing-channel fallback | **Human fallback required** when zero channels configured — stronger than "log a warning." New action item, see below. |

### New action items from resolved decisions

- [x] **Budget persistence.** Replace #6's in-memory assumption with a real store (file-based JSON keyed by date is enough for a single-instance demo; Firestore if multi-instance). Track cumulative `estimated_cost_usd` per day, read it back in `evaluate()`.
- [x] **Bind runtime SA in deploy.** Add `--service-account=` to every `gcloud run deploy` call (`infra/cloudbuild.yaml` and/or `deploy.sh`, wherever the actual deploy happens — deploy.sh currently only creates the SA and grants Secret Manager access, it doesn't attach it to any Cloud Run service).
- [x] **GCP dry-run flag.** Add a config flag (default: dry-run/off) gating `GCPComputeClient.start_preemptible_instances` from actually creating instances; document how to flip it on for demo day.
- [x] **Dispatcher human fallback on zero channels.** When `channels` ends up empty in `DispatcherAgent.notify()`, don't just log — write to a fallback surface (e.g. a local file/queue an operator can check, or escalate via whatever channel *is* guaranteed, like stdout structured log at ERROR severity with a distinct event name) so a fully-silent remediation is never possible.
- [ ] **5th failure scenario test.** Confirm the 5th scenario name in `simulator/failures.py` (review names `gpu_memory_exhaustion`, `corrupt_scene_file`, `network_timeout`, `license_failure` — one more exists per "five scenarios" in the review) and add its Pathologist classification test alongside #10's fix.
- [x] **`shared/config.py` env_prefix — resolved by inspection, not asked:** `.env.example` and Cloud Run Secret Manager `--set-secrets` both use unprefixed names (`GEMINI_API_KEY`, not `SECONDUNIT_GEMINI_API_KEY`). Drop `env_prefix = "SECONDUNIT_"` rather than reprefixing every documented env var — smaller change, matches existing docs/deploy config.

---

## Notes from validation pass

- Issue #5's first paragraph (Pydantic coercing a dict into `Approval`/`CostEstimate`) is technically accurate but not actually a bug — Pydantic v2 handles nested dict-to-model coercion fine. The load-bearing part of #5 is the second paragraph (auth/idempotency) and the missing try/except; don't spend time on the coercion framing when fixing.
- #9's claim that detection only "works" via the mock always returning 98.5 is worth double-checking once #18's Grafana scope question is settled — if the client stays mocked, #9's fix (query GPU metric too) is still correct in isolation but won't change demo behavior until the mock differentiates queries.
