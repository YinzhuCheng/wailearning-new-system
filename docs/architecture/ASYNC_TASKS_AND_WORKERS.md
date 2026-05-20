# Async tasks and workers (LLM homework grading + discussion retries)

**Fact:** There is **no** Redis queue or Celery worker package in this repository for grading or discussion-assistant retries. Async work is modeled as **database rows** processed by an **in-process background thread** inside the API process.

**Primary implementation:** `apps/backend/courseeval_backend/llm_grading.py`.

---

## 1. Task storage

| Item | Detail |
|------|--------|
| ORM model | `HomeworkGradingTask` (`db/models.py`) |
| Creation | Router/service queues row when auto grading triggers (see homework router + helpers in `llm_grading.py`) |
| Status values | `queued`, `processing`, `retry_scheduled`, `success`, `failed` |

Tasks are durable: restarting API leaves rows in DB; worker resumes according to stale reclaim rules.

Discussion assistant work uses the sibling durable model `DiscussionLLMJob` with lifecycle `pending`, `retry_scheduled`, `success`, `failed`.

---

## 2. Worker process model

| Component | Detail |
|-----------|--------|
| Class | `_WorkerManager` inside `llm_grading.py` |
| Start | `start_grading_worker()` → `worker_manager.start()` invoked from `main.py` lifespan when `ENABLE_LLM_GRADING_WORKER` and `LLM_GRADING_WORKER_LEADER` true |
| Thread | Daemon thread named `llm-grading-worker` |
| Stop | `worker_manager.stop()` on app shutdown |
| Concurrency | `ThreadPoolExecutor` sized by `resolve_max_parallel_grading_tasks(db)` (global policy) |

**Multi-worker gunicorn:** only the leader should drain (`LLM_GRADING_WORKER_LEADER=true`) to avoid duplicate churn; single uvicorn dev often runs leader.

---

## 3. Processing loop (simplified)

1. Poll / sleep `LLM_GRADING_WORKER_POLL_SECONDS`.
2. `claim_grading_tasks_batch(cap)` marks up to `cap` tasks as processing.
3. The same loop also scans for due `DiscussionLLMJob` rows whose `next_retry_at` has matured.
4. For each grading task id, `process_grading_task(task_id)` executes vendor HTTP via httpx, writes `HomeworkScoreCandidate`, updates submission summary via `refresh_submission_summary`, and marks the task `success`, `failed`, or `retry_scheduled`.
5. For each due discussion job id, `run_discussion_llm_reply_for_job(job_id)` attempts the assistant reply and marks the same row `success`, `failed`, or `retry_scheduled`.
6. Exceptions map to retry vs permanent failure (grep `RetryableLLMError`, `NonRetryableLLMError`, `classify_llm_error_code`).

Transient retry model:

- request-local endpoint retries and group failover still happen inside one processing attempt;
- after those immediate retries are exhausted, transient failures persist on the same row with `retry_count`, `failure_class="transient"`, `last_error_at`, and `next_retry_at`;
- backoff is exponential and capped at 20 minutes;
- persisted task/job retries are not immortal; the default total retry lifetime is 7 days, after which the same durable row becomes `failed`;
- retry vs permanent classification is shared runtime logic based on normalized error codes plus HTTP/error-message semantics, with hard provider statuses such as `401`, `403`, `404`, and `413` treated as permanent;
- no unbounded chain of replacement task rows is created for transient grading failures.

---

## 4. Stale tasks

**Setting:** `LLM_GRADING_TASK_STALE_SECONDS` (`Settings`).

If a worker dies mid-processing, reclaim logic should allow tasks to return to queue — implementation details in `llm_grading.py` (grep `stale`).

---

## 5. Quota interaction

Before / during execution, quota policies gate token reservations (`domains/llm/` helpers). Exhaustion surfaces as task failure states + UI diagnostics — see [`../product/LLM_HOMEWORK_GUIDE.md`](../product/LLM_HOMEWORK_GUIDE.md).

Billing rule for retried LLM work:

- failed attempts release reservations and do not write billed usage rows;
- homework usage is written only after a successful grading result;
- discussion usage is written only after a successful assistant reply.

---

## 6. Testing hooks

- Tests frequently patch HTTP (`httpx`) rather than calling live vendors.
- Worker may be disabled via `tests/conftest.py` defaults to reduce background interference.
- Direct helpers: `process_grading_task`, `process_next_grading_task`, and `run_discussion_llm_reply_for_job` — used in tests.
- Virtual-time tests can inject a fake clock through `domains/llm/runtime.py` instead of waiting for real backoff windows.

---

## 7. Operational troubleshooting

| Symptom | Checks |
|---------|--------|
| Tasks never leave `queued` / `retry_scheduled` | Worker flags; DB connectivity; leader setting; inspect `next_retry_at` vs current UTC |
| Stuck `processing` | Stale seconds; kill orphaned workers; DB inspection |
| Unexpected score | Effective aggregate rule vs latest attempt body — see `refresh_submission_summary` |
| Discussion reply never appears after transient vendor failure | Inspect `DiscussionLLMJob.status`, `failure_class`, `retry_count`, `next_retry_at`, and worker logs |

Cross-links: [`architecture/TROUBLESHOOTING.md`](../architecture/TROUBLESHOOTING.md), [`testing/TEST_EXECUTION_PITFALLS.md`](../testing/TEST_EXECUTION_PITFALLS.md).

---

## 8. Current state summary

- `HomeworkGradingTask.status`: `queued`, `processing`, `retry_scheduled`, `success`, `failed`
- `DiscussionLLMJob.status`: `pending`, `retry_scheduled`, `success`, `failed`
- Retry metadata is persisted on both row types via `retry_count`, `failure_class`, `last_error_at`, and `next_retry_at`
