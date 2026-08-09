# pytest-resumable-stepmetrics

> **When a test retries, you lose the story.**
> Which step failed? Which HTTP calls were made on attempt 1 vs attempt 2?
> Which steps already passed and don't need to re-run?
> Your only clue is a wall of logs.

`pytest-resumable-stepmetrics` gives you **structured step-level metadata** inside
every test, with **per-attempt tracking**, **resume-on-retry** for idempotent
steps, and a **JSON report** you can query, store, or feed into a dashboard.

```bash
pip install pytest-resumable-stepmetrics
```

---

## What you get

After a test with one retry, your terminal shows this automatically:

```
steplog summary:
====================================== = ======================================
  Test:    test_order_flow.py::test_create_order_retries_on_failure
  Status:  PASSED
  Retries: 1

 Steps:
+---+-------------------+---------+---------+-------------+--------+----------+------+
| # | Step              | Attempt | Status  | Duration(s) | Errors | Warnings | Info |
+===+===================+=========+=========+=============+========+==========+======+
| 1 | POST /auth/token  | 1       | passed  | 0.051       | 0      | 0        | 0    |
| 2 | GET /api/products | 1       | passed  | 0.041       | 0      | 0        | 0    |
| 3 | POST /api/orders  | 1       | failed  | 0.081       | 0      | 0        | 0    |
| 4 | POST /auth/token  | 2       | skipped | 0.000       | 0      | 0        | 0    |
| 5 | GET /api/products | 2       | passed  | 0.041       | 0      | 0        | 0    |
| 6 | POST /api/orders  | 2       | passed  | 0.080       | 0      | 0        | 0    |
+---+-------------------+---------+---------+-------------+--------+----------+------+

 api_requests:
+---------------+--------+-------------+------------+---------+
| Endpoint      | Method | Status Code | Latency Ms | Attempt |
+===============+========+=============+============+=========+
| /auth/token   | POST   | 200         | 52.1       | 1       |
| /api/products | GET    | 200         | 43.7       | 1       |
| /api/orders   | POST   | 500         | 287.4      | 1       |
| /api/products | GET    | 200         | 43.7       | 2       |
| /api/orders   | POST   | 201         | 91.3       | 2       |
+---------------+--------+-------------+------------+---------+
```

Row 3: `POST /api/orders` failed on attempt 1 — **exact failure point, no log digging**.
Row 4: `POST /auth/token` was **skipped on attempt 2** because it already passed — no wasted work.
The `api_requests` table shows every HTTP call across all attempts with its attempt number — a complete audit trail.

---

## Quick start

```python
def test_flow(steplog):
    with steplog("fetch config"):
        ...
    with steplog("call API"):
        ...
    with steplog("validate response"):
        ...
```

```bash
pytest --steplog-json    # also writes .steplog/report.json per test
```

---

## End-to-end example

> A fully runnable version with no extra dependencies lives in
> [`examples/test_order_flow.py`](examples/test_order_flow.py) — clone and run it.

### Domain model (custom record)

```python
from dataclasses import dataclass
from pytest_resumable_stepmetrics import steplog_record

@steplog_record(key="api_requests", stamp=("attempt",))
@dataclass
class ApiRequest:
    """One HTTP call — auto-stamped with the current attempt number."""
    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    attempt: int = 1    # filled automatically
```

Registering with `@steplog_record` means:
- `api_requests` appears as its own array in `report.json`
- a terminal table is rendered automatically after each test
- the `attempt` field is stamped from the live context — no manual wiring

### The test

```python
def test_create_order(steplog):
    api = OrdersAPI(base_url="https://api.example.com")

    def run():
        steplog.reset_attempt()   # first line of every attempt

        # Authentication is idempotent — skip it on retry, no guard needed
        steplog.run("POST /auth/token", lambda: api.authenticate())

        with steplog("GET /api/products"):
            resp = api.get_products()
            steplog.record(ApiRequest("/api/products", "GET", resp.status_code, resp.latency_ms))
            assert resp.status_code == 200

        with steplog("POST /api/orders"):
            resp = api.create_order(product_id=resp.json()[0]["id"])
            steplog.record(ApiRequest("/api/orders", "POST", resp.status_code, resp.latency_ms))
            assert resp.status_code == 201, f"Order failed: {resp.json()}"

    for attempt in range(2):
        try:
            run()
            return
        except AssertionError:
            if attempt == 1:
                raise
```

### Sample `report.json`

```json
{
  "run": {
    "test_nodeid": "test_order_flow.py::test_create_order",
    "status": "passed",
    "started_at": "2026-08-09T08:25:39.092605+00:00",
    "ended_at": "2026-08-09T08:25:41.340120+00:00",
    "duration_seconds": 2.248,
    "retry_count": 1,
    "info": {}
  },
  "steps": [
    { "name": "POST /auth/token",  "attempt": 1, "resumed": false, "status": "passed",  "duration_seconds": 0.051, "error": null },
    { "name": "GET /api/products", "attempt": 1, "resumed": false, "status": "passed",  "duration_seconds": 0.041, "error": null },
    { "name": "POST /api/orders",  "attempt": 1, "resumed": false, "status": "failed",  "duration_seconds": 0.081, "error": "Order failed: {'error': 'upstream timeout'}" },
    { "name": "POST /auth/token",  "attempt": 2, "resumed": true,  "status": "skipped", "duration_seconds": 0.0,   "error": null },
    { "name": "GET /api/products", "attempt": 2, "resumed": false, "status": "passed",  "duration_seconds": 0.041, "error": null },
    { "name": "POST /api/orders",  "attempt": 2, "resumed": false, "status": "passed",  "duration_seconds": 0.080, "error": null }
  ],
  "api_requests": [
    { "endpoint": "/auth/token",   "method": "POST", "status_code": 200, "latency_ms": 52.1,  "attempt": 1 },
    { "endpoint": "/api/products", "method": "GET",  "status_code": 200, "latency_ms": 43.7,  "attempt": 1 },
    { "endpoint": "/api/orders",   "method": "POST", "status_code": 500, "latency_ms": 287.4, "attempt": 1 },
    { "endpoint": "/api/products", "method": "GET",  "status_code": 200, "latency_ms": 43.7,  "attempt": 2 },
    { "endpoint": "/api/orders",   "method": "POST", "status_code": 201, "latency_ms": 91.3,  "attempt": 2 }
  ]
}
```

---

## Retry & attempt tracking

Call `steplog.reset_attempt()` as the first line of each attempt.
`run.retry_count` and each step's `attempt` field are tracked automatically.
The **Attempt** column appears in the terminal table only when retries occur.

Works with any retry mechanism — `tenacity`, `pytest-rerunfailures`, a manual
loop, whatever you already use.

---

## Resume-on-retry

Two forms — pick the one that fits your code style.

### Context manager (with guard)

```python
with steplog.resumable("download dataset") as step:
    if not step.resumed:          # guard required — with-blocks always run
        download()
```

### Callable (guard-free)

```python
steplog.run("download dataset", download)   # func is simply not called on retry
```

> ⚠️ Use resume only for **pure / idempotent** work (downloads, token fetch,
> name resolution). Stateful steps (writes, deployments, order creation) must
> re-run — use plain `steplog("name")`.

---

## Custom records

`steplog.record(obj)` accepts any dataclass. Register it with `@steplog_record`
to control the JSON key, auto-stamped fields, and optional custom renderer:

```python
@steplog_record(key="db_queries", stamp=("attempt",))
@dataclass
class DbQuery:
    table: str
    rows_affected: int
    duration_ms: float
    attempt: int = 1
```

An unregistered dataclass also works — it uses its snake_case class name as the
key and auto-tabulates all its fields. No extra code required.

---

## The `steplog` fixture API

| Call | What it does |
|---|---|
| `steplog("name")` | Track a step — context manager, always runs body. |
| `steplog.resumable("name")` | Track a resumable step — use `if not step.resumed:` guard. |
| `steplog.run("name", func, *a, **kw)` | Track a callable step — skips calling `func` on retry (guard-free). |
| `steplog.record(obj)` | Attach a custom dataclass record to the current attempt. |
| `steplog.reset_attempt()` | Advance the attempt counter — call first in each retry. |
| `steplog.context` | Mutable dict auto-stamped onto records (`attempt`, custom fields). |
| `steplog.collector` | The underlying `StepLogCollector` for advanced use. |

---

## JSON report

```bash
pytest --steplog-json                  # writes .steplog/<test-id>/report.json
pytest --steplog-json-dir=reports/     # custom output directory
```

Each file contains `run`, `steps`, and one array per registered record type.
Ingest into Elasticsearch, a database, or a CI dashboard — the schema is stable.

---

## License

MIT
