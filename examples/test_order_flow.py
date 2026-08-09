"""Runnable example: API test with step tracking, retry, and custom records.

Run it:
    pip install pytest-resumable-stepmetrics
    pytest examples/test_order_flow.py -v --steplog-json

No extra dependencies — HTTP calls are mocked with unittest.mock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from pytest_resumable_stepmetrics import steplog_record

# ---------------------------------------------------------------------------
# Domain model — one record per HTTP call, auto-stamped with the attempt number
# ---------------------------------------------------------------------------


@steplog_record(key="api_requests", stamp=("attempt",))
@dataclass
class ApiRequest:
    """One HTTP call made during the test."""

    endpoint: str
    method: str
    status_code: int
    latency_ms: float
    attempt: int = 1  # filled automatically from the steplog context


# ---------------------------------------------------------------------------
# Fake HTTP client (replaces requests / httpx in a real test suite)
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status_code: int, body: dict, latency_ms: float = 50.0):
        self.status_code = status_code
        self._body = body
        self.latency_ms = latency_ms

    def json(self):
        return self._body


class FakeOrdersAPI:
    """Simulates a flaky REST API.

    - POST /auth/token  → always succeeds
    - GET  /api/products → always succeeds
    - POST /api/orders  → fails (500) on attempt 1, succeeds on attempt 2
    """

    def __init__(self):
        self._calls = 0

    def authenticate(self) -> FakeResponse:
        time.sleep(0.05)
        return FakeResponse(200, {"token": "eyJhbGci..."}, latency_ms=52.1)

    def get_products(self) -> FakeResponse:
        time.sleep(0.04)
        return FakeResponse(200, [{"id": "prod-1", "name": "Widget"}], latency_ms=43.7)

    def create_order(self, product_id: str, quantity: int) -> FakeResponse:
        self._calls += 1
        time.sleep(0.08)
        if self._calls == 1:
            # Simulate a transient upstream failure on the first attempt
            return FakeResponse(500, {"error": "upstream timeout"}, latency_ms=287.4)
        return FakeResponse(201, {"id": "ord-abc123", "product_id": product_id}, latency_ms=91.3)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_order_retries_on_failure(steplog):
    """Place an order through the API.  Retries once if a transient error occurs.

    Demonstrates:
      - steplog.run()        — guard-free skip on retry (authentication)
      - steplog("name")      — regular step tracking
      - steplog.record()     — attach a custom ApiRequest per HTTP call
      - steplog.reset_attempt() — advance the attempt counter each retry
    """
    api = FakeOrdersAPI()
    token = None
    product_id = None

    def run():
        nonlocal token, product_id

        steplog.reset_attempt()  # must be the first call in each attempt

        # Authentication is idempotent — skip it on retry with the callable form
        def authenticate():
            nonlocal token
            resp = api.authenticate()
            steplog.record(ApiRequest("/auth/token", "POST", resp.status_code, resp.latency_ms))
            assert resp.status_code == 200
            token = resp.json()["token"]

        steplog.run("POST /auth/token", authenticate)

        # Fetch products — re-runs on every attempt (stateful page cursor in real life)
        with steplog("GET /api/products"):
            resp = api.get_products()
            steplog.record(ApiRequest("/api/products", "GET", resp.status_code, resp.latency_ms))
            assert resp.status_code == 200
            product_id = resp.json()[0]["id"]

        # Place the order — re-runs on every attempt (idempotency key in real life)
        with steplog("POST /api/orders"):
            resp = api.create_order(product_id=product_id, quantity=1)
            steplog.record(ApiRequest("/api/orders", "POST", resp.status_code, resp.latency_ms))
            assert resp.status_code == 201, f"Order failed: {resp.json()}"
            assert "id" in resp.json(), "order id missing from response"

    # --- retry loop (replace with tenacity / pytest-rerunfailures in practice) ---
    last_exc = None
    for _ in range(2):
        try:
            run()
            return  # passed
        except AssertionError as exc:
            last_exc = exc

    raise last_exc  # re-raise if all attempts failed


def test_all_steps_pass_on_first_attempt(steplog):
    """Happy-path smoke test — no retries, all steps pass."""
    api = FakeOrdersAPI()
    api._calls = 1  # skip the simulated failure

    steplog.reset_attempt()

    with steplog("GET /api/products"):
        resp = api.get_products()
        steplog.record(ApiRequest("/api/products", "GET", resp.status_code, resp.latency_ms))
        assert resp.status_code == 200

    with steplog("POST /api/orders"):
        resp = api.create_order(product_id="prod-1", quantity=1)
        steplog.record(ApiRequest("/api/orders", "POST", resp.status_code, resp.latency_ms))
        assert resp.status_code == 201
