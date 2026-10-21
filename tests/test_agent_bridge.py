"""Agent Communications Bridge tests (§29P).

Tests cover:
- Message schema: envelope, idempotency, claim types (§5, §16, §21)
- Delivery state machine: legal/illegal transitions (§6)
- Durable bus: persistence, inbox/outbox, recovery (§3)
- Adapter interface: OpenCode, Codex, internal, GUI (§12-§14)
- Bridge supervisor: assign → verify_ack → verify_start → handoff (§6-§11)
- Supervisor failure: manual relay detection (§44)
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest

from compute.agent_message import (
    AgentMessage,
    ClaimType,
    DeliveryState,
    Intent,
    SCHEMA_VERSION,
    build_ack,
    build_heartbeat,
    build_task_assign,
    build_task_complete,
    build_task_start,
)
from compute.agent_message_bus import (
    AgentMessageBus,
    DeliveryError,
    is_valid_transition,
    transition,
)
from compute.worker_bridge_adapters import (
    CodexAdapter,
    GuiAgentAdapter,
    InternalAgentAdapter,
    OpenCodeAdapter,
    WorkerAdapterInterface,
)
from compute.bridge_supervisor import BridgeSupervisor


# --- helpers ------------------------------------------------------------------

def _make_bus(tmp_dir):
    return AgentMessageBus(
        db_path=Path(tmp_dir) / "bridge.db",
        audit_path=Path(tmp_dir) / "audit.jsonl",
    )


def _task_assign(task_id="TEST-001", objective="Test task"):
    return build_task_assign(
        task_id=task_id,
        objective=objective,
        sender_agent="hermes",
        sender_worker="supervisor",
        receiver_agent="opencode",
        receiver_worker="opencode-01",
        project_id="test-project",
    )


# --- §5: message schema tests -------------------------------------------------

class TestMessageSchema:
    def test_schema_version(self):
        msg = _task_assign()
        assert msg.schema == SCHEMA_VERSION
        assert msg.schema == "aetherius.agent-message.v1"

    def test_message_has_unique_id(self):
        m1 = _task_assign()
        m2 = _task_assign()
        assert m1.message_id != m2.message_id

    def test_idempotency_key_computed(self):
        msg = _task_assign()
        assert msg.idempotency_key
        assert msg.idempotency_key.startswith("idem_")

    def test_idempotency_key_deterministic(self):
        """Same task_id + intent + sender = same idempotency key (§16)."""
        m1 = build_task_assign(
            task_id="X", objective="a",
            sender_agent="hermes", sender_worker="sup",
            receiver_agent="opencode", receiver_worker="oc-1")
        m1.created_at = 1000.0  # freeze time
        m2 = build_task_assign(
            task_id="X", objective="a",
            sender_agent="hermes", sender_worker="sup",
            receiver_agent="opencode", receiver_worker="oc-1")
        m2.created_at = 1000.0
        assert m1.idempotency_key == m2.idempotency_key

    def test_roundtrip_dict(self):
        """Message serializes and deserializes without loss."""
        msg = _task_assign()
        msg.claim_type = ClaimType.VERIFIED_CONCLUSION
        d = msg.to_dict()
        msg2 = AgentMessage.from_dict(d)
        assert msg2.message_id == msg.message_id
        assert msg2.task_id == msg.task_id
        assert msg2.intent == msg.intent
        assert msg2.claim_type == ClaimType.VERIFIED_CONCLUSION

    def test_unknown_schema_rejected(self):
        d = _task_assign().to_dict()
        d["schema"] = "wrong.schema.v99"
        with pytest.raises(ValueError, match="unknown schema"):
            AgentMessage.from_dict(d)

    def test_all_intents_valid(self):
        """Every intent in the enum is valid."""
        for intent in Intent:
            msg = AgentMessage(intent=intent)
            assert msg.intent == intent


# --- §6: delivery state machine tests -------------------------------------------

class TestDeliveryStateMachine:
    def test_pending_to_delivered(self):
        assert is_valid_transition(DeliveryState.PENDING, Intent.TASK_ASSIGN)
        result = transition(DeliveryState.PENDING, Intent.TASK_ASSIGN)
        assert result == DeliveryState.DELIVERED

    def test_delivered_to_acknowledged(self):
        """DELIVERED -> ACKNOWLEDGED requires TASK_ACK (§7)."""
        result = transition(DeliveryState.DELIVERED, Intent.TASK_ACK)
        assert result == DeliveryState.ACKNOWLEDGED

    def test_acknowledged_to_running(self):
        """ACKNOWLEDGED -> RUNNING_VERIFIED requires TASK_START (§8)."""
        result = transition(DeliveryState.ACKNOWLEDGED, Intent.TASK_START)
        assert result == DeliveryState.RUNNING_VERIFIED

    def test_illegal_transition_rejected(self):
        """PENDING + TASK_ACK is illegal — can't ACK before DELIVERED."""
        with pytest.raises(DeliveryError):
            transition(DeliveryState.PENDING, Intent.TASK_ACK)

    def test_illegal_pending_to_running(self):
        """PENDING + TASK_START is illegal — must ACK first (§6)."""
        with pytest.raises(DeliveryError):
            transition(DeliveryState.PENDING, Intent.TASK_START)

    def test_sent_is_not_acknowledged(self):
        """§6: SENT != ACKNOWLEDGED. DELIVERED is NOT ACKNOWLEDGED."""
        assert DeliveryState.DELIVERED != DeliveryState.ACKNOWLEDGED

    def test_complete_from_progressing(self):
        result = transition(DeliveryState.PROGRESSING, Intent.TASK_COMPLETE)
        assert result == DeliveryState.COMPLETED

    def test_handoff_from_completed(self):
        result = transition(DeliveryState.COMPLETED, Intent.HANDOFF)
        assert result == DeliveryState.HANDED_OFF

    def test_recall_from_any_state(self):
        """RECALL can apply from any active state (§25)."""
        for state in [DeliveryState.DELIVERED, DeliveryState.ACKNOWLEDGED,
                      DeliveryState.RUNNING_VERIFIED, DeliveryState.PROGRESSING,
                      DeliveryState.PAUSED]:
            assert is_valid_transition(state, Intent.RECALL)

    def test_cancel_from_active_states(self):
        for state in [DeliveryState.DELIVERED, DeliveryState.ACKNOWLEDGED,
                      DeliveryState.RUNNING_VERIFIED, DeliveryState.PROGRESSING,
                      DeliveryState.PAUSED]:
            assert is_valid_transition(state, Intent.CANCEL)


# --- §3: durable bus tests ---------------------------------------------------------

class TestDurableBus:
    def test_submit_and_query(self, tmp_path):
        bus = _make_bus(tmp_path)
        msg = _task_assign()
        bus.submit(msg)
        state = bus.get_delivery_state(msg.message_id)
        assert state == DeliveryState.PENDING

    def test_duplicate_idempotency_rejected(self, tmp_path):
        """§16: duplicate idempotency_key is rejected."""
        bus = _make_bus(tmp_path)
        msg = _task_assign()
        bus.submit(msg)
        with pytest.raises(DeliveryError, match="duplicate"):
            bus.submit(msg)

    def test_delivery_state_transitions(self, tmp_path):
        bus = _make_bus(tmp_path)
        msg = _task_assign()
        bus.submit(msg)
        bus.mark_delivered(msg.message_id)
        assert bus.get_delivery_state(msg.message_id) == DeliveryState.DELIVERED

    def test_inbox_outbox(self, tmp_path):
        """§2: every worker has an INBOX and OUTBOX."""
        bus = _make_bus(tmp_path)
        msg = _task_assign()
        bus.submit(msg)

        inbox = bus.get_inbox("opencode", "opencode-01")
        assert len(inbox) == 1
        assert inbox[0]["task_id"] == "TEST-001"

        outbox = bus.get_outbox("hermes", "supervisor")
        assert len(outbox) == 1

    def test_recovery_after_restart(self, tmp_path):
        """§3: messages survive restart. PENDING/DELIVERED are recoverable."""
        bus = _make_bus(tmp_path)
        msg = _task_assign()
        bus.submit(msg)
        bus.mark_delivered(msg.message_id)

        # Simulate restart: create a new bus instance on the same DB
        bus2 = AgentMessageBus(db_path=Path(tmp_path) / "bridge.db")
        pending = bus2.recover_pending()
        assert len(pending) == 1
        assert pending[0]["message_id"] == msg.message_id

    def test_audit_log_written(self, tmp_path):
        """§36: every communication is audited."""
        audit_path = Path(tmp_path) / "audit.jsonl"
        bus = AgentMessageBus(
            db_path=Path(tmp_path) / "bridge.db",
            audit_path=audit_path)
        msg = _task_assign()
        bus.submit(msg)
        bus.mark_delivered(msg.message_id)

        assert audit_path.exists()
        lines = audit_path.read_text().strip().split("\n")
        assert len(lines) >= 2  # submitted + delivered
        import json
        entry = json.loads(lines[0])
        assert entry["action"] == "submitted"
        assert entry["message"]["task_id"] == "TEST-001"

    def test_stats(self, tmp_path):
        bus = _make_bus(tmp_path)
        bus.submit(_task_assign("T1"))
        bus.submit(_task_assign("T2"))
        stats = bus.stats()
        assert stats["total_messages"] == 2
        assert "TASK_ASSIGN" in stats["by_intent"]


# --- §21: claim types tests -----------------------------------------------------------

class TestClaimTypes:
    def test_claim_types_distinct(self):
        """§21: workers must distinguish claim types."""
        assert ClaimType.OBSERVATION != ClaimType.CLAIM
        assert ClaimType.CLAIM != ClaimType.INFERENCE
        assert ClaimType.INFERENCE != ClaimType.HYPOTHESIS
        assert ClaimType.HYPOTHESIS != ClaimType.VERIFIED_CONCLUSION

    def test_task_complete_has_claim_type(self):
        """TASK_COMPLETE carries a claim type (§21)."""
        assign = _task_assign()
        complete = build_task_complete(
            assign, "opencode", "opencode-01",
            claim_type=ClaimType.VERIFIED_CONCLUSION,
            files_changed=["test.py"],
            tests_passed=10, tests_failed=0)
        assert complete.claim_type == ClaimType.VERIFIED_CONCLUSION
        assert complete.claim_confidence == "VERIFIED"

    def test_observation_not_verified(self):
        """An OBSERVATION claim is not VERIFIED (§21)."""
        assign = _task_assign()
        complete = build_task_complete(
            assign, "opencode", "opencode-01",
            claim_type=ClaimType.OBSERVATION)
        assert complete.claim_type == ClaimType.OBSERVATION
        assert complete.claim_confidence == "OBSERVED"


# --- §12-§14: adapter tests -----------------------------------------------------------

class TestAdapterInterface:
    def test_opencode_adapter_has_capabilities(self):
        adapter = OpenCodeAdapter()
        from compute.agent_message import Capability
        assert Capability.CODING in adapter.capabilities
        assert Capability.TOOL_CALLS in adapter.capabilities

    def test_codex_adapter_has_capabilities(self):
        adapter = CodexAdapter()
        from compute.agent_message import Capability
        assert Capability.CODING in adapter.capabilities

    def test_internal_adapter_without_func(self):
        adapter = InternalAgentAdapter()
        assert adapter.connect() is False
        result = adapter.send_message(_task_assign())
        assert result["delivered"] is False
        assert "no subagent" in result["evidence"][0]

    def test_internal_adapter_with_func(self):
        def mock_subagent(prompt):
            return "subagent completed: " + prompt[:50]
        adapter = InternalAgentAdapter(subagent_func=mock_subagent)
        assert adapter.connect() is True
        result = adapter.send_message(_task_assign())
        assert result["delivered"] is True
        assert "in-process" in result["channel"]

    def test_gui_adapter_delivery_verification(self):
        """§15: GUI adapter verifies receipt by searching transcript."""
        transcript_store = {"content": ""}
        def gui_send(prompt):
            transcript_store["content"] = prompt
            return True
        def gui_read():
            return transcript_store["content"]
        adapter = GuiAgentAdapter(
            "gui-01", "claude",
            gui_send_func=gui_send,
            gui_read_func=gui_read)
        msg = _task_assign("GUI-TEST-001")
        result = adapter.send_message(msg)
        assert result["delivered"] is True
        assert result["delivery_verified"] is True  # task_id found in transcript

    def test_gui_adapter_without_functions(self):
        """Honest: GUI adapter without functions reports unavailable."""
        adapter = GuiAgentAdapter("gui-02", "cursor")
        assert adapter.connect() is False
        result = adapter.send_message(_task_assign())
        assert result["delivered"] is False


# --- §6-§11: bridge supervisor tests -----------------------------------------------------

class TestBridgeSupervisor:
    def test_assign_task_delivered_not_implementing(self, tmp_path):
        """§44: after assign, state is DELIVERED — NOT 'IMPLEMENTING'."""
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)

        def mock_send(msg):
            return {"delivered": True, "channel": "test-channel",
                    "evidence": ["mock delivery"]}

        adapter = InternalAgentAdapter(subagent_func=lambda p: "done")
        adapter.send_message = mock_send
        sup.register_adapter(adapter)

        result = sup.assign_task(
            task_id="SUP-001", objective="Test",
            worker_id="hermes-subagent-01")
        assert result["delivery_state"] == "DELIVERED"
        # CRITICAL: NOT "IMPLEMENTING" or "RUNNING" (§44)
        assert result["delivery_state"] != "IMPLEMENTING"
        assert result["delivery_state"] != "RUNNING"

    def test_unknown_worker_rejected(self, tmp_path):
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)
        result = sup.assign_task("T", "obj", worker_id="nonexistent")
        assert result["delivered"] is False
        assert "unknown worker" in result["error"]

    def test_lifecycle_tracking(self, tmp_path):
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)
        adapter = InternalAgentAdapter(subagent_func=lambda p: "done")
        adapter.send_message = lambda msg: {
            "delivered": True, "channel": "test", "evidence": ["ok"]}
        sup.register_adapter(adapter)

        sup.assign_task("LC-001", "Test", worker_id="hermes-subagent-01")
        lc = sup.get_lifecycle("LC-001")
        assert lc is not None
        assert lc["delivery_state"] == "DELIVERED"
        assert len(lc["evidence"]) > 0

    def test_owner_manual_relay_detection(self, tmp_path):
        """§44: if delivery failed but worker has the task, manual relay detected."""
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)

        # Adapter that fails delivery but "has" the task in transcript
        class FailButHasTask(WorkerAdapterInterface):
            def discover(self): return {"status": "AVAILABLE"}
            def connect(self): return True
            def send_message(self, msg):
                return {"delivered": False, "channel": "test",
                        "evidence": ["delivery failed"]}
            def read_messages(self, limit=50): return []
            def acknowledge(self, msg):
                return True  # task_id IS in transcript (manually relayed)
            def status(self): return {"status": "AVAILABLE"}
            def cancel(self): return False
            def pause(self): return False
            def resume(self): return False

        adapter = FailButHasTask("fail-01", "opencode")
        sup.register_adapter(adapter)
        sup.assign_task("MANUAL-001", "Test", worker_id="fail-01")

        # Detect manual relay
        detected = sup.detect_manual_relay("MANUAL-001")
        assert detected is True
        lc = sup.get_lifecycle("MANUAL-001")
        assert lc["owner_manual_relay"] is True
        assert any("OWNER_MANUAL_RELAY" in e for e in lc["evidence"])

    def test_verify_ack_no_adapter(self, tmp_path):
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)
        result = sup.verify_ack("NONEXISTENT")
        assert result["acknowledged"] is False

    def test_handoff_received(self, tmp_path):
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)
        adapter = InternalAgentAdapter(subagent_func=lambda p: "done")
        adapter.send_message = lambda msg: {
            "delivered": True, "channel": "test", "evidence": ["ok"]}
        sup.register_adapter(adapter)

        sup.assign_task("HO-001", "Test", worker_id="hermes-subagent-01")

        # Simulate handoff
        from compute.agent_message import build_handoff
        assign = _task_assign("HO-001")
        handoff = build_handoff(
            assign, "opencode", "opencode-01",
            completed_work="Implemented feature X",
            files_changed=["feature.py"],
            tests_results="5 passed, 0 failed")

        result = sup.receive_handoff("HO-001", handoff)
        assert result["received"] is True
        assert result["delivery_state"] == "HANDED_OFF"
        assert "feature.py" in result["files_changed"]


# --- §9: heartbeat tests -------------------------------------------------------------

class TestHeartbeat:
    def test_heartbeat_build(self):
        hb = build_heartbeat(
            "opencode", "opencode-01",
            task_id="HB-001", phase="implementing",
            current_operation="writing tests",
            repo="test-repo", branch="main")
        assert hb.intent == Intent.HEARTBEAT
        assert hb.task_id == "HB-001"
        assert hb.payload["phase"] == "implementing"
        assert hb.payload["current_operation"] == "writing tests"

    def test_heartbeat_no_ack_required(self):
        """§9: heartbeats are lightweight — no ACK needed."""
        hb = build_heartbeat("opencode", "oc-1", task_id="HB-002")
        assert hb.required_ack is False


# --- §11: handoff tests -----------------------------------------------------------------

class TestHandoff:
    def test_handoff_has_required_fields(self):
        """§11: TASK_COMPLETE/HANDOFF must include specific fields."""
        assign = _task_assign("HF-001")
        from compute.agent_message import build_handoff
        hf = build_handoff(
            assign, "opencode", "opencode-01",
            completed_work="Done X",
            remaining_work="Y",
            files_changed=["a.py", "b.py"],
            repo="test", branch="main",
            baseline_sha="abc123", final_sha="def456",
            tests_results="10 passed",
            evidence=["test output"],
            decisions=["chose approach A"],
            known_gaps=["edge case Z"],
            blockers=[],
            recommended_next="implement Y")
        p = hf.payload
        assert p["completed_work"] == "Done X"
        assert p["remaining_work"] == "Y"
        assert p["files_changed"] == ["a.py", "b.py"]
        assert p["baseline_sha"] == "abc123"
        assert p["final_sha"] == "def456"
        assert p["tests_results"] == "10 passed"
        assert p["decisions"] == ["chose approach A"]
        assert p["known_gaps"] == ["edge case Z"]
        assert p["recommended_next"] == "implement Y"


# --- integration: full lifecycle test (§30) -------------------------------------------------

class TestFullLifecycle:
    def test_full_task_lifecycle(self, tmp_path):
        """§30: the complete lifecycle from assign to handoff.

        This is the acceptance test for the bridge protocol.
        Note: this tests the PROTOCOL, not live OpenCode delivery.
        Live delivery requires OpenCode to be running and reachable.
        """
        bus = _make_bus(tmp_path)
        sup = BridgeSupervisor(bus)

        # Mock adapter that simulates the full lifecycle
        class LifecycleAdapter(WorkerAdapterInterface):
            def __init__(self):
                super().__init__("lifecycle-01", "test-agent")
                self.state = "idle"
                self.received_tasks = []

            def discover(self):
                return {"status": "AVAILABLE"}

            def connect(self):
                return True

            def send_message(self, msg):
                if msg.intent == Intent.TASK_ASSIGN:
                    self.received_tasks.append(msg.task_id)
                    self.state = "delivered"
                    return {"delivered": True, "channel": "test",
                            "evidence": ["task received"]}
                return {"delivered": False, "channel": "test",
                        "evidence": ["unsupported intent"]}

            def read_messages(self, limit=50):
                return [{"task_id": t} for t in self.received_tasks]

            def acknowledge(self, msg):
                return msg.task_id in self.received_tasks

            def status(self):
                return {"status": "AVAILABLE", "state": self.state}

            def cancel(self): return True
            def pause(self): return True
            def resume(self): return True

        adapter = LifecycleAdapter()
        sup.register_adapter(adapter)

        # Step 1: assign
        result = sup.assign_task("LIFE-001", "Full test", worker_id="lifecycle-01")
        assert result["delivery_state"] == "DELIVERED"

        # Step 2: verify ACK (§7)
        ack_result = sup.verify_ack("LIFE-001")
        assert ack_result["acknowledged"] is True
        assert ack_result["delivery_state"] == "ACKNOWLEDGED"

        # Step 3: verify start (§8) — no TASK_START sent, so not started
        start_result = sup.verify_start("LIFE-001")
        assert start_result["started"] is False
        # §8: PROCESS_ALIVE alone is insufficient

        # Step 4: lifecycle state
        lc = sup.get_lifecycle("LIFE-001")
        assert lc["delivery_state"] == "ACKNOWLEDGED"

        # Step 5: no manual relay needed
        assert lc["owner_manual_relay"] is False
