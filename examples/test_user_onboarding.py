"""Runnable example: SaaS user onboarding with step tracking, retry, and custom records.

Run it:
    pip install pytest-resumable-stepmetrics
    pytest examples/test_user_onboarding.py -v --steplog-json

No extra dependencies — all external calls are simulated in-process.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from pytest_resumable_stepmetrics import steplog_record


# ---------------------------------------------------------------------------
# Domain model — one record per provisioning action, auto-stamped with attempt
# ---------------------------------------------------------------------------


@steplog_record(key="provisioning_actions", stamp=("attempt",))
@dataclass
class ProvisioningAction:
    """A single resource provisioning event during onboarding."""

    resource: str   # e.g. "user", "workspace", "email", "plan"
    action: str     # e.g. "created", "sent", "provisioned", "assigned"
    status: str     # "ok" | "error"
    duration_ms: float
    attempt: int = 1  # filled automatically from the steplog context


# ---------------------------------------------------------------------------
# Fake onboarding service (simulates a flaky workspace provisioner)
# ---------------------------------------------------------------------------


class FakeOnboardingService:
    """Simulates a SaaS backend.

    - create_account      → always succeeds
    - send_welcome_email  → always succeeds (but must NOT fire twice)
    - provision_workspace → fails (timeout) on attempt 1, succeeds on attempt 2
    - assign_trial_plan   → always succeeds
    """

    def __init__(self):
        self._provision_calls = 0

    def create_account(self, email: str) -> dict:
        time.sleep(0.06)
        return {"user_id": "usr-abc123", "email": email}

    def send_welcome_email(self, user_id: str) -> dict:
        time.sleep(0.03)
        return {"message_id": "msg-xyz789", "status": "queued"}

    def provision_workspace(self, user_id: str) -> dict:
        self._provision_calls += 1
        time.sleep(0.14)
        if self._provision_calls == 1:
            raise TimeoutError("workspace provisioner timed out after 30s")
        return {"workspace_id": "ws-def456", "region": "us-east-1"}

    def assign_trial_plan(self, user_id: str, workspace_id: str) -> dict:
        time.sleep(0.04)
        return {"plan": "trial-14d", "expires_in_days": 14}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_new_user_signup_retries_on_provisioning_failure(steplog):
    """Sign up a new user end-to-end.  Retries once if workspace provisioning fails.

    Demonstrates:
      - steplog("name")         — track a stateful step (re-runs on retry)
      - steplog.run(name, func) — guard-free skip on retry (welcome email)
      - steplog.record(obj)     — attach a ProvisioningAction per event
      - steplog.reset_attempt() — advance the attempt counter each retry
    """
    svc = FakeOnboardingService()
    user_id = None
    workspace_id = None

    def run():
        nonlocal user_id, workspace_id

        steplog.reset_attempt()  # must be the first call in every attempt

        # --- create account (stateful — re-runs each attempt) ---
        with steplog("create account"):
            result = svc.create_account(email="alice@example.com")
            user_id = result["user_id"]
            steplog.record(ProvisioningAction("user", "created", "ok", 61.2))

        # --- send welcome email (idempotent — skip on retry, no guard needed) ---
        def send_email():
            svc.send_welcome_email(user_id=user_id)
            steplog.record(ProvisioningAction("email", "sent", "ok", 31.7))

        steplog.run("send welcome email", send_email)

        # --- provision workspace (stateful — re-runs each attempt) ---
        with steplog("provision workspace"):
            try:
                result = svc.provision_workspace(user_id=user_id)
                workspace_id = result["workspace_id"]
                steplog.record(ProvisioningAction("workspace", "provisioned", "ok", 143.8))
            except TimeoutError as exc:
                steplog.record(ProvisioningAction("workspace", "provisioned", "error", 143.8))
                raise AssertionError(str(exc)) from exc

        # --- assign trial plan ---
        with steplog("assign trial plan"):
            result = svc.assign_trial_plan(user_id=user_id, workspace_id=workspace_id)
            steplog.record(ProvisioningAction("plan", "assigned", "ok", 38.4))
            assert result["plan"] == "trial-14d"

    # Retry loop — replace with tenacity / pytest-rerunfailures in practice
    last_exc = None
    for _ in range(2):
        try:
            run()
            return  # passed
        except AssertionError as exc:
            last_exc = exc

    raise last_exc


def test_new_user_signup_happy_path(steplog):
    """Happy-path: all steps succeed on the first attempt, no retries."""
    svc = FakeOnboardingService()
    svc._provision_calls = 1  # skip the simulated timeout

    steplog.reset_attempt()

    with steplog("create account"):
        result = svc.create_account(email="bob@example.com")
        steplog.record(ProvisioningAction("user", "created", "ok", 58.3))

    with steplog("provision workspace"):
        result = svc.provision_workspace(user_id=result["user_id"])
        steplog.record(ProvisioningAction("workspace", "provisioned", "ok", 141.2))

    with steplog("assign trial plan"):
        result = svc.assign_trial_plan(user_id="usr-abc123", workspace_id=result["workspace_id"])
        steplog.record(ProvisioningAction("plan", "assigned", "ok", 37.9))
        assert result["plan"] == "trial-14d"
