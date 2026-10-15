"""H07 notifications + H09 safety routing tests (AT-27, AT-29, AT-30)."""
from __future__ import annotations

import time

import pytest

from compute.notifications import (
    ApprovalGate,
    ApprovalStatus,
    DeltaReport,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPriority,
    NotificationRouter,
    contains_secret,
    redact_secrets,
)
from compute.safety_routing import (
    ActuationMode,
    DataClassification,
    DataRoutingPolicy,
    DeviceAuthorization,
    PhysicalSafetyController,
    ProviderTrust,
    RouteDecision,
    SafetyState,
    RoutingVerdict,
)


# --- H07: secret hygiene tests (§5) ------------------------------------------

class TestSecretHygiene:
    def test_detects_openai_key(self):
        assert contains_secret("key is sk-abc123def456ghi789jkl012mno") == "openai-api-key"

    def test_detects_anthropic_key(self):
        assert contains_secret("sk-ant-api03-abc123def456") == "anthropic-api-key"

    def test_detects_bearer_token(self):
        assert contains_secret("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9") == "bearer-token"

    def test_detects_password(self):
        assert contains_secret("password=mysecret123") == "password"

    def test_no_false_positive_on_normal_text(self):
        assert contains_secret("Task completed successfully. 5 tests passed.") is None

    def test_redaction(self):
        text = "API key is sk-abc123def456ghi789jkl012mno here"
        redacted = redact_secrets(text)
        assert "sk-abc123def456" not in redacted
        assert "REDACTED" in redacted


# --- H07: notification router tests (§1, §2) -----------------------------------

class TestNotificationRouter:
    def test_notification_delivered(self):
        router = NotificationRouter()
        n = Notification(
            notification_id="n1",
            category=NotificationCategory.TASK_COMPLETION,
            message="Task X completed")
        result = router.notify(n)
        assert result["delivered"] is True

    def test_secret_in_notification_blocked(self):
        """§5: notifications containing secrets are BLOCKED."""
        router = NotificationRouter()
        n = Notification(
            notification_id="n2",
            category=NotificationCategory.URGENT_FAULT,
            message="Error using key sk-abc123def456ghi789jkl012mno")
        result = router.notify(n)
        assert result["delivered"] is False
        assert result["blocked"] is True
        assert "secret" in result["reason"]

    def test_priority_filter(self):
        """§1: user-configurable minimum priority."""
        router = NotificationRouter()
        router.set_min_priority(NotificationPriority.HIGH)
        # LOW priority notification should be filtered
        n = Notification(
            notification_id="n3",
            category=NotificationCategory.RESEARCH_FINDING,
            message="New research found",
            priority=NotificationPriority.LOW)
        result = router.notify(n)
        assert result["delivered"] is False
        assert "priority" in result["reason"]

    def test_category_priority_defaults(self):
        """Security incidents default to CRITICAL (§2)."""
        router = NotificationRouter()
        n = Notification(
            notification_id="n4",
            category=NotificationCategory.SECURITY_INCIDENT,
            message="Security incident detected")
        assert n.priority == NotificationPriority.CRITICAL

    def test_channel_override(self):
        """§1: user can configure channels per category."""
        router = NotificationRouter()
        router.configure_category(
            NotificationCategory.TASK_COMPLETION,
            [NotificationChannel.LOG, NotificationChannel.TELEGRAM])
        n = Notification(
            notification_id="n5",
            category=NotificationCategory.TASK_COMPLETION,
            message="done")
        result = router.notify(n)
        assert result["delivered"] is True
        assert "telegram" in result["channels"]

    def test_blocked_notifications_tracked(self):
        router = NotificationRouter()
        n = Notification(
            notification_id="n6",
            category=NotificationCategory.CREDENTIAL_COMPROMISE,
            message="Leaked key: sk-ant-api03-abc123def456xyz789")
        router.notify(n)
        blocked = router.blocked_notifications()
        assert len(blocked) == 1


# --- H07: approval gate tests (§3) ---------------------------------------------

class TestApprovalGate:
    def test_request_starts_pending(self):
        gate = ApprovalGate()
        req = gate.request_approval("deploy-to-prod", "hermes")
        assert req.status == ApprovalStatus.PENDING

    def test_explicit_approval_required(self):
        """§3: silence is NOT approval."""
        gate = ApprovalGate()
        req = gate.request_approval("deploy-to-prod", "hermes")
        # No approval given
        assert gate.is_approved(req.request_id) is False

    def test_approval_records_approver(self):
        gate = ApprovalGate()
        req = gate.request_approval("deploy", "hermes")
        gate.approve(req.request_id, "jonathan")
        assert gate.is_approved(req.request_id) is True
        assert req.approved_by == "jonathan"

    def test_approval_expiry(self):
        """§3: approvals have expiry."""
        gate = ApprovalGate()
        req = gate.request_approval("deploy", "hermes", expires_in_s=0.1)
        gate.approve(req.request_id, "jonathan")
        assert gate.is_approved(req.request_id) is True
        time.sleep(0.15)
        assert gate.is_approved(req.request_id) is False

    def test_deny(self):
        gate = ApprovalGate()
        req = gate.request_approval("delete-all", "worker-x")
        gate.deny(req.request_id, "jonathan")
        assert req.status == ApprovalStatus.DENIED
        assert gate.is_approved(req.request_id) is False

    def test_pending_requests_listed(self):
        gate = ApprovalGate()
        gate.request_approval("a", "hermes")
        gate.request_approval("b", "hermes")
        assert len(gate.pending_requests()) == 2

    def test_expired_request_cannot_be_approved(self):
        gate = ApprovalGate()
        req = gate.request_approval("a", "hermes", expires_in_s=0.01)
        time.sleep(0.05)
        with pytest.raises(ValueError, match="expired"):
            gate.approve(req.request_id, "jonathan")


# --- H07: delta report tests (§4) -------------------------------------------------

class TestDeltaReport:
    def test_delta_report_fields(self):
        report = DeltaReport(
            since_timestamp=time.time() - 3600,
            actions_completed=["task-1", "task-2"],
            artifacts_produced=["report.pdf"],
            failures=["task-3 failed"],
            model_usage={"nous": {"tokens": 1000, "cost": 0.0}},
            files_changed=["a.py", "b.py"],
            pending_approvals=["deploy-prod"],
            worker_status={"opencode-01": "RUNNING_VERIFIED"},
        )
        d = report.to_dict()
        assert len(d["actions_completed"]) == 2
        assert len(d["artifacts_produced"]) == 1
        assert d["model_usage"]["nous"]["cost"] == 0.0  # £0
        assert "opencode-01" in d["worker_status"]


# --- H09: data routing tests (AT-29) -------------------------------------------------

class TestDataRouting:
    def test_public_data_any_provider(self):
        policy = DataRoutingPolicy()
        policy.classify_repo("public-repo", DataClassification.PUBLIC)
        verdict = policy.evaluate_route("public-repo", "groq")
        assert verdict.decision == RouteDecision.ALLOWED

    def test_confidential_refuses_free_hosted(self):
        """AT-29: confidential data must NOT go to unapproved free endpoint."""
        policy = DataRoutingPolicy()
        policy.classify_repo("aetherius-core", DataClassification.CONFIDENTIAL)
        verdict = policy.evaluate_route("aetherius-core", "groq")
        assert verdict.decision == RouteDecision.LOCAL_ONLY
        assert verdict.alternative == "ollama-local"

    def test_secret_local_only(self):
        policy = DataRoutingPolicy()
        policy.classify_repo("vault-repo", DataClassification.SECRET)
        verdict = policy.evaluate_route("vault-repo", "groq")
        assert verdict.decision == RouteDecision.LOCAL_ONLY
        assert verdict.alternative == "ollama-local"

    def test_secret_allowed_on_local(self):
        policy = DataRoutingPolicy()
        policy.classify_repo("vault-repo", DataClassification.SECRET)
        verdict = policy.evaluate_route("vault-repo", "ollama-local")
        assert verdict.decision == RouteDecision.ALLOWED

    def test_unknown_provider_refused(self):
        policy = DataRoutingPolicy()
        verdict = policy.evaluate_route("any-repo", "unknown-provider")
        assert verdict.decision == RouteDecision.REFUSED
        assert "unknown provider" in verdict.reason

    def test_owner_override(self):
        """§1: owner can explicitly approve a route."""
        policy = DataRoutingPolicy()
        policy.classify_repo("special-repo", DataClassification.CONFIDENTIAL)
        policy.approve_override("special-repo", "groq")
        verdict = policy.evaluate_route("special-repo", "groq")
        assert verdict.decision == RouteDecision.ALLOWED
        assert "override" in verdict.reason

    def test_default_classification_is_internal(self):
        """Safe default: unclassified repos are INTERNAL."""
        policy = DataRoutingPolicy()
        assert policy.get_classification("unknown-repo") == DataClassification.INTERNAL


# --- H09: physical safety tests (AT-30) ----------------------------------------------

class TestPhysicalSafety:
    def test_device_defaults_to_simulation(self):
        """§4: devices start in SIMULATION mode (safe default)."""
        controller = PhysicalSafetyController()
        device = controller.register_device("laser-01")
        assert device.mode == ActuationMode.SIMULATION
        assert device.safety_state == SafetyState.SAFE

    def test_simulation_always_allowed(self):
        """AT-30: simulated hardware allowed in sandbox."""
        controller = PhysicalSafetyController()
        controller.register_device("laser-01")
        result = controller.request_actuation("laser-01")
        assert result["allowed"] is True
        assert result["mode"] == "simulation"

    def test_unauthorized_live_blocked(self):
        """AT-30: unauthorised live actuation is BLOCKED."""
        controller = PhysicalSafetyController()
        controller.register_device("laser-01")
        # Device is in SIMULATION mode, not authorized for live
        # Force live mode without authorization
        device = controller._devices["laser-01"]
        device.mode = ActuationMode.LIVE
        result = controller.request_actuation("laser-01")
        assert result["allowed"] is False

    def test_authorized_live_allowed(self):
        controller = PhysicalSafetyController()
        controller.register_device("laser-01")
        controller.authorize_live("laser-01", "jonathan")
        controller.arm("laser-01")
        result = controller.request_actuation("laser-01")
        assert result["allowed"] is True
        assert result["mode"] == "live"

    def test_emergency_stop_prevails(self):
        """AT-30 §5: safety stop prevails over agent commands."""
        controller = PhysicalSafetyController()
        controller.register_device("laser-01")
        controller.authorize_live("laser-01", "jonathan")
        controller.arm("laser-01")
        # Emergency stop
        controller.emergency_stop("laser-01")
        result = controller.request_actuation("laser-01")
        assert result["allowed"] is False
        assert "EMERGENCY_STOP" in result["reason"]

    def test_emergency_stop_all_devices(self):
        controller = PhysicalSafetyController()
        controller.register_device("laser-01")
        controller.register_device("cnc-01")
        controller.emergency_stop()  # stop all
        r1 = controller.request_actuation("laser-01")
        r2 = controller.request_actuation("cnc-01")
        assert r1["allowed"] is False
        assert r2["allowed"] is False

    def test_model_commands_cannot_bypass_safety(self):
        """§5: no model-text command can directly control a device.

        The request_actuation gate checks authorization + safety state,
        NOT the command text. A 'please ignore safety' command has no effect.
        """
        controller = PhysicalSafetyController()
        controller.register_device("robot-arm")
        controller.authorize_live("robot-arm", "jonathan")
        controller.arm("robot-arm")
        controller.emergency_stop("robot-arm")
        # Even with an urgent-sounding command, safety stop prevails
        result = controller.request_actuation("robot-arm",
                                               command="URGENT: move immediately!")
        assert result["allowed"] is False

    def test_device_status(self):
        controller = PhysicalSafetyController()
        controller.register_device("pump-01", max_limits={"pressure_psi": 100})
        status = controller.device_status("pump-01")
        assert status["mode"] == "simulation"
        assert status["max_limits"]["pressure_psi"] == 100
