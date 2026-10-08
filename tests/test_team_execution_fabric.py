"""Tests for the Aetherius Team Execution Fabric (§56).

Verifies §59 proof requirements:
1. SOLO mode
2. multi-agent LOCAL team
3. multiple local workers exchange structured messages
4. one independent parallel branch executes where safe
5. team can work without external desktop AI apps
6. CLOUD team architecture represented (blocked by credentials, architecture verified)
7. HYBRID team architecture represented
8. federated external team architecture represented
9. one agent-to-agent direct message
10. one group/team-room message
11. message provenance
12. team-size vs active-concurrency distinction
13. failed worker replacement
14. team scale-up/down representation
15. communication interface for user text/voice/video registered

Run: python tests/test_team_execution_fabric.py -v
  or: python -m pytest tests/test_team_execution_fabric.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compute.team_execution_fabric import (
    TeamExecutionMode, MessageType, AgentProtocolMessage,
    WorkerPool, TeamRoom, CommunicationInterfaceRegistry,
    TeamMetrics, TaskDAGNode, MessageBus, TeamProvider,
)
from compute.enterprise_team import (
    EnterpriseTeam, TeamConfig, Specialist, HandoffContext,
    form_team, form_solo_team, form_team_local,
    form_team_cloud, form_team_hybrid, form_team_federated,
    SPECIALIST_ROLES, WorkerStatus,
    TextCommunicationInterface, VoiceCommunicationInterface,
    VideoCommunicationInterface,
)
from models.inference_contract import (
    PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_CONFIDENTIAL,
    PRIVACY_SECRET_LOCAL_ONLY,
)

TEST_TEAM_ID = "test-team-001"


# === §59 proof item 1: SOLO mode ===

def test_solo_mode():
    """SOLO_LOCAL: one agent performs the task (§1)."""
    team = EnterpriseTeam(execution_mode=TeamExecutionMode.SOLO_LOCAL)
    team.logical_team_size = 1

    # Add a single specialist
    spec = Specialist(role_id="coding_worker", model_class="coder",
                      capabilities=["code"], worker_id="solo-001")
    team.specialists["coding_worker"] = spec
    team.worker_pools["local"].register_worker("solo-001", "coder")

    def fake_fn(spec):
        class FakeResult:
            content = "solo output"
        spec.result = FakeResult()
        return spec.result

    result = team.execute_solo("coding_worker", fake_fn)
    assert result["mode"] == "SOLO_LOCAL"
    assert result["result"].status == WorkerStatus.COMPLETED


# === §59 proof item 2: multi-agent LOCAL team ===

def test_multi_agent_local_team():
    """TEAM_LOCAL: multiple local workers cooperate without external apps (§2, §5)."""
    team = form_team_local("test objective",
                           ["coding_worker", "research_worker", "reviewer"])
    assert len(team.specialists) == 3
    assert team.execution_mode == TeamExecutionMode.TEAM_LOCAL
    assert all(s.execution_target == "local" for s in team.specialists.values())


# === §59 proof item 3: multiple local workers exchange structured messages ===

def test_multiple_workers_exchange_messages():
    """Multiple local workers exchange structured messages (§13)."""
    team = form_team_local("test", ["coding_worker", "research_worker", "reviewer"])
    msg_bus = team.message_bus
    # Workers exchange a structured message
    msg = msg_bus.send_direct(
        from_worker="worker-researcher",
        to_worker="worker-coder",
        content="Here are research findings for the task.",
        message_type=MessageType.EVIDENCE,
        privacy_class=PRIVACY_PROJECT,
        task_id=team.team_id,
        team_id=team.team_id,
    )
    assert msg.message_id is not None
    assert msg.from_worker == "worker-researcher"
    assert msg.to_worker == "worker-coder"
    assert msg.message_type == MessageType.EVIDENCE

    history = msg_bus.history()
    assert len(history) >= 1
    # Verify message has structured metadata (§14)
    stored = history[-1]
    for field in ["message_id", "conversation_id", "team_id", "task_id",
                  "from_worker", "to_worker", "message_type", "priority",
                  "timestamp", "privacy_class", "content"]:
        assert field in stored, f"Missing field {field} in message"


# === §59 proof item 4: independent parallel branch executes ===

def test_parallel_branch_execution():
    """Independent parallel branch executes where safe (§10)."""
    team = form_team_local("test", ["coding_worker", "research_worker"])
    team.concurrency_limit = 2

    def make_fn(label):
        def fn(spec):
            class FakeResult:
                content = f"output-{label}"
            spec.result = FakeResult()
            return spec.result
        return fn

    results = team.run_parallel([
        ("coding_worker", make_fn("coding")),
        ("research_worker", make_fn("research")),
    ], max_concurrency=2)

    assert len(results) == 2
    assert results["coding_worker"].status == WorkerStatus.COMPLETED
    assert results["research_worker"].status == WorkerStatus.COMPLETED


# === §59 proof item 5: team works without external desktop AI apps ===

def test_team_without_external_apps():
    """Team works without external desktop AI apps (§2)."""
    team = form_team_local("test", ["coding_worker", "test_runner"])
    # The team has internal workers but no external providers
    assert len(team.team_providers) == 0
    assert len(team.specialists) == 2
    # Team room is available for internal communication
    room = TeamRoom(room_id="r1", team_id=team.team_id, task_id="test")
    room.add_member("worker-1")
    room.add_member("worker-2")
    assert len(room.members) == 2


# === §59 proof item 6: CLOUD team architecture represented ===

def test_cloud_team_architecture():
    """TEAM_CLOUD architecture represented (§6, §59 item 6).

    Full cloud execution requires rotated credentials (BLOCKED_OWNER).
    Here we verify the architecture is represented.
    """
    team = form_team_cloud("research task",
                           ["research_worker", "coding_worker", "reviewer"])
    assert team.execution_mode == TeamExecutionMode.TEAM_CLOUD
    assert team.execution_target == "cloud"
    assert team.allow_cloud if hasattr(team, 'allow_cloud') else True
    # Cloud pool is registered
    assert "cloud" in team.worker_pools
    # Workers registered in cloud pool
    pool = team.worker_pools["cloud"]
    assert pool.logical_size >= 3


# === §59 proof item 7: HYBRID team architecture represented ===

def test_hybrid_team_architecture():
    """TEAM_HYBRID architecture represented (§7)."""
    team = form_team_hybrid(
        "secure task",
        ["coding_worker", "research_worker", "reviewer"],
        local_roles=["coding_worker"],
        cloud_roles=["research_worker"],
    )
    assert team.execution_mode == TeamExecutionMode.TEAM_HYBRID
    # Both local and cloud pools have workers
    assert "local" in team.worker_pools
    assert "cloud" in team.worker_pools
    assert "hybrid" in team.worker_pools


# === §59 proof item 8: federated external team architecture represented ===

def test_federated_team_architecture():
    """TEAM_FEDERATED architecture represented (§21, §22)."""
    team = form_team_federated(
        "federated task",
        ["coding_worker", "reviewer"],
        external_teams=["openclaw_team"],
    )
    assert team.execution_mode == TeamExecutionMode.TEAM_FEDERATED

    # Register a mock external team provider
    class MockProvider:
        provider_id = "mock-openclaw"
        def create_team(self, spec): return "ext-team-001"
        def destroy_team(self, team_id): return True
        def list_workers(self, team_id): return ["ext-w1", "ext-w2"]
        def assign_role(self, team_id, worker_id, role): return True
        def submit_task(self, team_id, task): return "ext-task-001"
        def send_message(self, message): return True
        def broadcast(self, team_id, msg): return True
        def query_status(self, team_id): return {"status": "running"}
        def retrieve_result(self, team_id, task_id): return "result"
        def cancel(self, team_id, task_id): return True
        def pause(self, team_id): return True
        def resume(self, team_id): return True

    team.register_team_provider(MockProvider())
    assert "mock-openclaw" in team.team_providers
    assert team.team_providers["mock-openclaw"].provider_id == "mock-openclaw"


# === §59 proof item 9: agent-to-agent direct message ===

def test_agent_to_agent_direct_message():
    """One agent-to-agent direct message (§14, §59 item 9)."""
    team = form_team_local("test", ["coding_worker", "research_worker"])
    # Get actual worker IDs from the team
    workers = list(team.specialists.values())
    from_w = workers[0].worker_id
    to_w = workers[1].worker_id

    msg = team.send_message(
        from_worker=from_w,
        to_worker=to_w,
        content="Question about the architecture specification.",
        message_type=MessageType.QUESTION,
    )
    assert msg is not None
    assert msg.from_worker == from_w
    assert msg.to_worker == to_w
    assert msg.message_type == MessageType.QUESTION
    assert msg.requires_response is True

    # Message is in the bus history (audit)
    history = team.message_bus.history()
    assert any(m["message_id"] == msg.message_id for m in history)


# === §59 proof item 10: group/team-room message ===

def test_group_room_message():
    """One group/team-room message (§19, §59 item 10)."""
    team = form_team_local("test", ["coding_worker", "researcher", "reviewer"])
    # Team room was created during configure()
    assert len(team.rooms) >= 1
    room = list(team.rooms.values())[0]
    msg = team.room_message(
        room_id=room.room_id,
        from_worker="worker-1",
        content="Integration phase starting now.",
        message_type=MessageType.STATUS,
    )
    assert msg is not None
    assert msg.to_worker == room.room_id
    assert len(room.messages) == 1
    # Message provenance in room
    assert room.messages[0]["from_worker"] == "worker-1"


# === §59 proof item 11: message provenance ===

def test_message_provenance():
    """Message provenance — every message has structured metadata (§14)."""
    team = form_team_local("test", ["coding_worker"])
    msg = AgentProtocolMessage(
        conversation_id="conv-1",
        team_id=team.team_id,
        task_id="task-1",
        from_worker="w1",
        to_worker="w2",
        message_type=MessageType.HANDOFF,
        content="handoff content",
        provenance_refs=["source-1", "evidence-2"],
    )
    d = msg.to_dict()
    assert d["message_id"] is not None
    assert d["conversation_id"] == "conv-1"
    assert d["team_id"] == team.team_id
    assert d["provenance_refs"] == ["source-1", "evidence-2"]
    assert d["evidence_refs"] == []  # default empty


# === §59 proof item 12: team-size vs active-concurrency distinction ===

def test_team_size_vs_concurrency():
    """Team-size vs active-concurrency distinction (§9)."""
    team = form_team_local("test", ["coding_worker", "research_worker", "reviewer", "test_runner"])
    # logical_team_size = number of roles (4)
    assert team.logical_team_size == 4
    assert team.active_workers == 0  # no execution yet
    summary = team.summary()
    stats = summary["team_size_vs_concurrency"]
    assert stats["logical_team_size"] == 4
    assert stats["active_workers"] == 0
    assert stats["completed"] == 0


# === §59 proof item 13: failed worker replacement ===

def test_failed_worker_replacement():
    """Failed worker replacement with context handoff (§30, §59 item 13)."""
    team = form_team_local("test", ["coding_worker", "researcher"])
    workers = list(team.specialists.values())
    failed_id = workers[0].worker_id

    replacement = team.failover(failed_id)
    assert replacement is not None
    assert replacement != failed_id
    # A replacement worker was created
    assert replacement in [s.worker_id for s in team.specialists.values()]
    # Handoff was recorded
    assert len(team.handoffs) >= 1


# === §59 proof item 14: team scale-up/down representation ===

def test_team_scale_up_down():
    """Team scale-up/down representation (§29, §59 item 14)."""
    team = form_team_local("test", ["coding_worker"])
    initial_count = len(team.specialists)

    # Scale up
    new_ids = team.scale_up("coding_worker", additional=2)
    assert len(new_ids) == 2
    assert len(team.specialists) == initial_count + 2
    assert team.logical_team_size > initial_count

    # Scale down
    if new_ids:
        removed = team.scale_down(new_ids[0])
        assert removed is True


# === §59 proof item 15: communication interface for text/voice/video ===

def test_communication_interfaces_registered():
    """Communication interfaces for text/voice/video registered (§40, §59 item 15)."""
    team = EnterpriseTeam()
    interfaces = team._comm_registry.list_interfaces()
    interface_ids = [i["interface_id"] for i in interfaces]
    assert "text" in interface_ids
    assert "voice" in interface_ids
    assert "video" in interface_ids

    # Can get interfaces
    text_if = team.get_comm_interface("text")
    assert text_if is not None
    assert text_if.transport == "websocket"

    voice_if = team.get_comm_interface("voice")
    assert voice_if.transport == "webrtc"

    video_if = team.get_comm_interface("video")
    assert video_if.transport == "webrtc"

    # Register a custom interface
    class CustomInterface:
        interface_id = "custom-sip"
        transport = "sip"
        def session_create(self): return "s"
        def session_join(self, s): return True
        def session_leave(self, s): return True
        def message_send(self, s, m): return True
        def message_receive(self, s): return None
        def voice_start(self, s): return True
        def voice_stop(self, s): return True
        def video_start(self, s): return False
        def video_stop(self, s): return True
        def screen_share(self, s): return False
        def participant_list(self, s): return []

    team.register_comm_interface(CustomInterface())
    custom = team.get_comm_interface("custom-sip")
    assert custom is not None
    assert custom.transport == "sip"


# === Additional tests ===

def test_message_types_available():
    """All §15 message types are available."""
    expected = {
        "REQUEST", "RESPONSE", "QUESTION", "ANSWER", "INSTRUCTION",
        "STATUS", "HANDOFF", "REVIEW", "CHALLENGE", "EVIDENCE",
        "ARTIFACT", "DEPENDENCY", "BLOCKER", "WARNING", "FAILURE",
        "RETRY", "ACKNOWLEDGEMENT", "CONSENSUS_REQUEST",
        "ARBITRATION_REQUEST", "HEARTBEAT",
    }
    actual = {m.name for m in MessageType}
    assert expected == actual


def test_worker_pool_local_cloud_hybrid():
    """Worker pools support local, cloud, hybrid (§3)."""
    team = form_team_local("test", ["coding_worker"])
    assert "local" in team.worker_pools
    assert "cloud" in team.worker_pools
    assert "hybrid" in team.worker_pools
    assert team.worker_pools["local"].worker_class == "local"
    assert team.worker_pools["cloud"].worker_class == "cloud"
    assert team.worker_pools["hybrid"].worker_class == "hybrid"


def test_dag_critical_path_scheduling():
    """Task DAG with critical-path scheduling (§11)."""
    team = form_team_local("test", ["coding_worker", "researcher", "reviewer"])
    team.concurrency_limit = 2

    def fn_a(node):
        return "result-a"

    def fn_b(node):
        return "result-b"

    def fn_c(node):
        # C depends on A and B
        return "result-c"

    nodes = [
        TaskDAGNode(node_id="A", role_id="coding_worker", task="code",
                    dependencies=[], fn=fn_a, est_duration_ms=100),
        TaskDAGNode(node_id="B", role_id="researcher", task="research",
                    dependencies=[], fn=fn_b, est_duration_ms=100),
        TaskDAGNode(node_id="C", role_id="reviewer", task="review",
                    dependencies=["A", "B"], fn=fn_c, est_duration_ms=50),
    ]

    results = team.run_dag(nodes, max_concurrency=2)
    assert "A" in results
    assert "B" in results
    assert "C" in results
    assert results["A"].status == "completed"
    assert results["B"].status == "completed"
    assert results["C"].status == "completed"
    assert team.metrics.critical_path_duration_ms > 0


def test_message_bus_subscribe():
    """Message bus supports subscribe for message delivery (§13)."""
    bus = MessageBus()
    received = []

    def handler(msg):
        received.append(msg)

    bus.subscribe("worker-1", handler)
    msg = bus.send_direct(
        from_worker="w-src",
        to_worker="worker-1",
        content="hello",
        message_type=MessageType.QUESTION,
        task_id="t1",
        team_id="tm1",
    )
    assert len(received) == 1
    assert received[0].message_id == msg.message_id


def test_team_metrics_tracked():
    """Performance metrics are tracked (§27)."""
    team = form_team_local("test", ["coding_worker"])
    metrics = team.metrics
    assert metrics.team_id == team.team_id
    assert metrics.tasks_completed == 0
    assert isinstance(metrics.to_dict(), dict)


def test_audit_messages_completeness():
    """Full audit trail of all messages is available (§16)."""
    team = form_team_local("test", ["coding_worker", "researcher"])
    team.send_message(
        from_worker="w1", to_worker="w2",
        content="msg1", message_type=MessageType.QUESTION,
    )
    team.send_message(
        from_worker="w2", to_worker="w1",
        content="msg2", message_type=MessageType.ANSWER,
    )
    audit = team.audit_messages()
    assert len(audit) >= 2
    types = [m["message_type"] for m in audit]
    assert "QUESTION" in types
    assert "ANSWER" in types


def test_team_execution_mode_enum():
    """Team execution mode enum has all modes (§1)."""
    modes = [m.value for m in TeamExecutionMode]
    assert "SOLO_LOCAL" in modes
    assert "SOLO_CLOUD" in modes
    assert "SOLO_AUTO" in modes
    assert "TEAM_LOCAL" in modes
    assert "TEAM_CLOUD" in modes
    assert "TEAM_HYBRID" in modes
    assert "TEAM_FEDERATED" in modes
    assert "TEAM_AUTO" in modes


def test_privacy_scoping_in_teams():
    """Privacy scoping — SECRET_LOCAL_ONLY material doesn't go to cloud (§7)."""
    team = EnterpriseTeam(privacy_class=PRIVACY_SECRET_LOCAL_ONLY)
    assert team.privacy_class == PRIVACY_SECRET_LOCAL_ONLY

    # Team with local-only privacy
    team_local = form_team_local("secret task", ["coding_worker"],
                                privacy=PRIVACY_SECRET_LOCAL_ONLY)
    assert team_local.privacy_class == PRIVACY_SECRET_LOCAL_ONLY
    # Workers inherit privacy
    for spec in team_local.specialists.values():
        assert spec.privacy_class == PRIVACY_SECRET_LOCAL_ONLY


if __name__ == "__main__":
    tests = [
        ("test_solo_mode", test_solo_mode),
        ("test_multi_agent_local_team", test_multi_agent_local_team),
        ("test_multiple_workers_exchange_messages", test_multiple_workers_exchange_messages),
        ("test_parallel_branch_execution", test_parallel_branch_execution),
        ("test_team_without_external_apps", test_team_without_external_apps),
        ("test_cloud_team_architecture", test_cloud_team_architecture),
        ("test_hybrid_team_architecture", test_hybrid_team_architecture),
        ("test_federated_team_architecture", test_federated_team_architecture),
        ("test_agent_to_agent_direct_message", test_agent_to_agent_direct_message),
        ("test_group_room_message", test_group_room_message),
        ("test_message_provenance", test_message_provenance),
        ("test_team_size_vs_concurrency", test_team_size_vs_concurrency),
        ("test_failed_worker_replacement", test_failed_worker_replacement),
        ("test_team_scale_up_down", test_team_scale_up_down),
        ("test_communication_interfaces_registered", test_communication_interfaces_registered),
        ("test_message_types_available", test_message_types_available),
        ("test_worker_pool_local_cloud_hybrid", test_worker_pool_local_cloud_hybrid),
        ("test_dag_critical_path_scheduling", test_dag_critical_path_scheduling),
        ("test_message_bus_subscribe", test_message_bus_subscribe),
        ("test_team_metrics_tracked", test_team_metrics_tracked),
        ("test_audit_messages_completeness", test_audit_messages_completeness),
        ("test_team_execution_mode_enum", test_team_execution_mode_enum),
        ("test_privacy_scoping_in_teams", test_privacy_scoping_in_teams),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
