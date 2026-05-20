# Remote CI Failure Review (2026-05-15)

## Purpose

This report records the root-cause analysis for the remote CI failures observed
on 2026-05-15 before remediation started. It is intentionally dated evidence,
not the long-term operating guide.

## Inputs Reviewed

- remote `backend-quick-pytest` failure summary
- remote `Python selector tooling` failure summary
- `apps/backend/courseeval_backend/llm_grading.py`
- `apps/backend/courseeval_backend/domains/llm/runtime.py`
- `apps/backend/courseeval_backend/domains/llm/protocol.py`
- `tests/backend/e2e_dev/test_e2e_dev_llm_mock.py`
- `tests/backend/homework/test_homework_llm_grading.py`
- `tests/behavior/test_material_chapters_notifications_homework_flow.py`
- `tests/backend/manual/test_validation_selector.py`
- `ops/scripts/dev/sync_pitfall_index_lines.py`
- `docs/product/LLM_HOMEWORK_GUIDE.md`
- `docs/architecture/ASYNC_TASKS_AND_WORKERS.md`

## Finding 1. Most `backend-quick-pytest` failures come from stale test expectations

The dominant failure cluster is not six independent regressions. It is mostly
one semantic mismatch:

- current implementation and docs treat transient grading failures as
  `retry_scheduled` on the **same** `HomeworkGradingTask` row;
- several older tests still expect immediate terminal `failed` state or an
  additional queued replacement row.

Authoritative current contract in docs:

- `docs/product/LLM_HOMEWORK_GUIDE.md`
- `docs/architecture/ASYNC_TASKS_AND_WORKERS.md`

Implementation evidence:

- transient `llm_call_failed` currently classifies as retryable in
  `domains/llm/runtime.py`
- `500` / `503` and malformed model JSON currently flow through retryable
  grading paths in `domains/llm/protocol.py`
- `_mark_task_failed(...)` in `llm_grading.py` writes `retry_scheduled` for
  transient failure class instead of terminal `failed`
- the same durable row is reused; replacement task rows are no longer the
  intended transient-recovery mechanism

### Tests now identified as stale against the current contract

These tests are stale because they still assert the old task lifecycle:

- `tests/backend/e2e_dev/test_e2e_dev_llm_mock.py::test_e2e_worker_status_and_control`
- `tests/backend/homework/test_homework_llm_grading.py::test_auto_retry_after_llm_failure_queues_second_task`
- `tests/backend/homework/test_homework_llm_grading.py::test_all_endpoints_exhausted_fails`
- `tests/behavior/test_material_chapters_notifications_homework_flow.py::test_ui29_llm_non_json_content_fails_task`
- `tests/behavior/test_material_chapters_notifications_homework_flow.py::test_ui31_llm_500_response_fails_task`

### Why each stale test fails

#### `test_e2e_worker_status_and_control`

The test polls until task status becomes only `failed` or `success`. A worker
that actually processes the task into `retry_scheduled` will still satisfy the
current contract, but the test treats that as “not processed yet” and times out.

#### `test_auto_retry_after_llm_failure_queues_second_task`

The test still expects two task rows:

- first row `failed`
- second row `queued`

That expectation conflicts with the documented and implemented persistent retry
model, where the same row transitions through
`queued -> processing -> retry_scheduled -> processing -> success|failed`.

#### `test_ui29_llm_non_json_content_fails_task`

Malformed or non-JSON model output now routes through retryable grading error
handling rather than terminal failure on the first attempt.

#### `test_ui31_llm_500_response_fails_task`

HTTP `500` is currently part of the retryable upstream error set, so the test's
immediate `failed` expectation is stale.

## Finding 2. One grading test likely reflects a real implementation issue

`tests/backend/homework/test_homework_llm_grading.py::test_all_endpoints_exhausted_fails`
needs more careful handling than the other stale tests.

The current docs say:

- transient failures can persist on the same row as `retry_scheduled`
- but “all endpoints exhausted” inside one routing attempt can still become a
  terminal failure depending on whether the failure is classified as permanent
  after route exhaustion

The present implementation behavior observed from code inspection is:

- a single endpoint returning `503` can still land the task in
  `retry_scheduled`
- the test expects terminal `failed`

This mismatch may still be stale-test behavior if product intent is “persist
the same task row in retry lane until retry lifetime is exhausted”.
However, Phase 3 should re-check whether “all endpoints exhausted” was supposed
to produce immediate terminal failure once the request-local routing options are
spent. Do not blindly rewrite this test without first confirming the intended
contract.

## Finding 3. `Python selector tooling` failure is stale governance metadata

The separate remote failure:

- `pitfall index line sync check failed: docs/testing/pitfall-index.csv has stale line references`

is caused by line-number drift between:

- `docs/testing/pitfall-index.csv`
- the canonical Markdown pitfall docs referenced by each row

The checker:

- `ops/scripts/dev/sync_pitfall_index_lines.py --check`

recomputes each row's `line` value by searching `heading` within
`document_path`. Any Markdown edits that shift headings without resynchronizing
the CSV will fail CI.

This is governance metadata drift, not a runtime product bug.

## Non-blocking warnings seen in the same remote output

These warnings did not fail the lane directly:

### Pydantic v2 deprecation

`apps/backend/courseeval_backend/api/schemas.py` still contains many
class-based:

```python
class Config:
    from_attributes = True
```

These should be migrated to `ConfigDict(from_attributes=True)` in a later pass.

### SQLAlchemy concurrent delete warning

The discussion delete path can emit:

- `SAWarning: DELETE statement ... expected to delete 1 row(s); 0 were matched`

under concurrent double-delete coverage. This is warning-level debt unless the
repository decides to treat it as a correctness issue.

## Phase-2 Decision Summary

At the end of the initial analysis pass:

- the retry-lifecycle documentation and implementation are aligned
- most grading failures appear to be stale tests, not fresh regressions
- one “all endpoints exhausted” expectation still deserves a contract check
  before rewriting tests
- the selector-tooling failure is definitely stale line metadata

## Intended Next Steps

1. Fix the grading/worker test cluster consistently against the current retry
   contract, while double-checking the “all endpoints exhausted” semantics.
2. Re-run targeted grading and worker tests.
3. Synchronize `docs/testing/pitfall-index.csv` line references and re-run the
   selector governance check.
4. Defer warning cleanup until the blockers are green.
