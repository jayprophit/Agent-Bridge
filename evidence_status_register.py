"""Aetherius Evidence Status Register — Authoritative module/feature status.

Source of truth for IMPLEMENTED / TESTED / VERIFIED / NOT_LOCATED / BLOCKED etc.
Status vocabulary (from AETHERIUS_GENESIS_MASTER_HANDOFF V2 §10):
  PROPOSED | FOUND | IMPLEMENTED | TESTED | INTEGRATED | DEPLOYED |
  INDEPENDENTLY_VERIFIED | NOT_LOCATED | BLOCKED

Correction date: 2026-10-15 (OpenCode handoff §11)
These corrections supersede older reports that claimed broader Genesis
autonomous execution than is currently verified.
"""
from __future__ import annotations

REGISTRY = {
    "P25_authority_engine": {
        "status": "VERIFIED",
        "evidence": "P25 authority engine is the existing aether_policy_bridge.py engine. Verified by "
                    "evaluate_capability_request() integration tests (tests/test_cost_policy_boundary.py: "
                    "15 acceptance tests A-J for B04 £0 guard).",
        "last_updated": "2026-10-15",
        "source": "code inspection + test suite",
    },
    "external_worker_autonomous_assignment": {
        "status": "FAILED",
        "correction": "EXTERNAL_WORKER_AUTONOMOUS_ASSIGNMENT = FAILED. "
                      "worker = opencode-primary. "
                      "reason = OWNER_HAD_TO_MANUALLY_DELIVER_TASK. "
                      "Jonathan had to manually paste the prompt into OpenCode and start execution. "
                      "Therefore OPENCODE_AUTONOMOUS_CONTROL = FAILED and "
                      "EXTERNAL_WORKER_ASSIGNMENT = NOT_LIVE_VERIFIED. "
                      "Do not claim OpenCode is IMPLEMENTING merely because OpenCode is open, "
                      "its process is alive, its session is recent, a prompt was copied to clipboard, "
                      "a click/key sequence was attempted, a task file exists, or Hermes intended to send work. "
                      "Only task-specific execution evidence counts. "
                      "The fix: Agent Communications Bridge (compute/agent_message.py + "
                      "compute/agent_message_bus.py + compute/worker_bridge_adapters.py + "
                      "compute/bridge_supervisor.py) — a first-party typed message protocol with "
                      "durable delivery, ACK lifecycle, and receiver-side verification.",
        "last_updated": "2026-10-15",
        "source": "owner manual intervention observation + bridge implementation",
    },
    "bridge_h03_skill_intake": {
        "status": "IMPLEMENTED",
        "evidence": "H03 skill discovery is wired INTO the bridge: "
                    "AgentMessageBus.submit_skill_candidate() converts a "
                    "SKILL_CANDIDATE message into an H03 SkillPipeline candidate. "
                    "Workers SUBMIT but CANNOT self-install — publication requires the "
                    "full provenance → sandbox → security → benchmark → approval "
                    "pipeline (§22). Tested end-to-end in "
                    "tests/test_bridge_integrations.py::TestSkillCandidateIntake "
                    "(4 tests: no-pipeline no-op, candidate-not-installed, "
                    "missing app_id rejection, full promotion path from a bridge "
                    "candidate to a published genesis_solo skill).",
        "last_updated": "2026-10-15",
        "source": "implementation + tests",
    },
    "agent_communications_bridge": {
        "status": "IMPLEMENTED",
        "evidence": "Agent Communications Bridge v1 (aetherius.agent-message.v1) implemented across "
                    "4 modules: compute/agent_message.py (canonical envelope, 27 typed intents, "
                    "7 claim types, idempotency keys), compute/agent_message_bus.py (SQLite WAL "
                    "durable bus, JSONL audit log, inbox/outbox, recovery), "
                    "compute/worker_bridge_adapters.py (OpenCodeAdapter via CLI, CodexAdapter via "
                    "rollout+exec, InternalAgentAdapter, GuiAgentAdapter), compute/bridge_supervisor.py "
                    "(task lifecycle: assign → verify_ack → verify_start → handoff). "
                    "43 tests in tests/test_agent_bridge.py cover schema, state machine, durability, "
                    "adapters, supervisor lifecycle, and manual relay detection (§44).",
        "last_updated": "2026-10-15",
        "source": "implementation + 43 passing tests",
    },
    "bridge_live_delivery_test": {
        "status": "TWO_TASK_AUTONOMOUS_LOOP_VERIFIED",
        "evidence": "The Hermes↔OpenCode bridge sustained TWO consecutive autonomous "
                    "engineering tasks with ZERO owner keyboard input (2026-10-15 21:47). "
                    "E2E-004: brief rendered from canonical envelope → OpenCode ACK'd, "
                    "STARTED, created tests/bridge_e2e_fixture_test.py, verified, "
                    "TASK_COMPLETE + HANDOFF (supervisor committed). "
                    "E2E-005: OpenCode created tests/bridge_control_contract_test.py, "
                    "ran 3 contract assertions (all passed), COMMITTED ITSELF (commit "
                    "3f14c49), TASK_COMPLETE + HANDOFF. Full lifecycle proven: "
                    "ASSIGN→DELIVERED→ACK→START→PROGRESS→file change→test→commit→"
                    "COMPLETE→HANDOFF→Hermes QA→next ASSIGN→ACK→START. "
                    "Bridge remains NOT fully LIVE_VERIFIED only in the sense that the "
                    "PROCESS_ALIVE≠RUNNING distinction is enforced in code but the "
                    "continuous multi-task scheduler still runs per-task, not as a "
                    "standing daemon loop (§30 wants automatic TASK-B after TASK-A).",
        "last_updated": "2026-10-15",
        "source": "live opencode run × 2 + git commit evidence 3f14c49 + QA re-runs",
    },
    "bridge_h06_integration": {
        "status": "IMPLEMENTED",
        "evidence": "H06 conflict resolution is wired INTO the message bus: "
                    "AgentMessageBus.submit_claim() registers typed claims in the "
                    "ClaimRegistry, detects contradictions between claims on the same "
                    "task, auto-creates a conflict case preserving BOTH views, and "
                    "proposes a QA-VERIFY verification task (§21). Resolution requires "
                    "evidence, never voting. 5 integration tests in "
                    "tests/test_bridge_integrations.py.",
        "last_updated": "2026-10-15",
        "source": "implementation + tests",
    },
    "bridge_h02_control": {
        "status": "IMPLEMENTED",
        "evidence": "H02 control commands implemented over the bridge in "
                    "compute/bridge_control.py: PAUSE, RESUME, CANCEL, RECALL, "
                    "REVOKE, REVOKE_CAPABILITY, REVOKE_PROVIDER, EMERGENCY_HALT. "
                    "Short-lived leases (§24) fail closed on expiry; RECALL cascades "
                    "to all transitive descendants (§25); authority is re-checked at "
                    "EXECUTION time so stale responses from recalled workers cannot "
                    "trigger side effects (§25). New intents added: REVOKE, "
                    "REVOKE_CAPABILITY, REVOKE_PROVIDER, EMERGENCY_HALT. "
                    "12 control tests in tests/test_bridge_integrations.py.",
        "last_updated": "2026-10-15",
        "source": "implementation + tests",
    },
    "worker_runtime_leases_heartbeat_checkpoints": {
        "status": "VERIFIED",
        "evidence": "worker.py implements WorkerHeartbeat, WorkerLease, checkpoint() save/load cycle. "
                    "Verified at current evidence level by P0-A/P0-B/P0-C tests and supervisor_runtime.py "
                    "state versioning (commit 45a76ae).",
        "last_updated": "2026-10-15",
        "source": "code inspection + commit evidence",
    },
    "B04_0_spend_guard": {
        "status": "INDEPENDENTLY_VERIFIED",
        "evidence": "Fixed at commit 2701b24 ('security: enforce the zero-spend guard at two independent "
                    "boundaries'). Independent QA completed: 28 NEW tests in tests/test_b04_independent_qa.py "
                    "(written from scratch, no imports from existing B04 test file) verify checks A-J across "
                    "CostClass, CostPolicyEngine, and Orchestrator.dispatch(). Additional bug found and fixed: "
                    "evaluate_provider() was not unpacking cc.is_allowed() tuple (consistent with evaluate_execution) "
                    "— would have returned truthy (False, reason) instead of False. All 49 tests pass (28 new + "
                    "15 existing B04 + 6 policy bridge regression). Commit: pending.",
        "last_updated": "2026-10-15",
        "source": "independent test authorship + code inspection + runtime verification",
    },
    "genesis_universal_autonomous_execution": {
        "status": "NOT_CURRENTLY_VERIFIED",
        "correction": "Earlier claims that Genesis can execute any task alone are NOT CURRENTLY VERIFIED. "
                      "genesis_bridge.py is contracts-only ('Contracts only; no runtime behavior here'). "
                      "genesis_action_bridge.py provides a thin ActionProposal→POST /v1/actions module, "
                      "NOT standalone execution capability. Subagents are required for actual task "
                      "execution.",
        "last_updated": "2026-10-15",
        "source": "OpenCode handoff §11",
    },
    "genesis_skill_registry": {
        "status": "SKELETON / NOT_PRODUCTION_INTEGRATED",
        "evidence": "No production Genesis skill registry exists in the live tree. genesis_bridge.py "
                    "defines abstract GenesisMemory and GenesisBridge contracts only. No shared "
                    "skills registry that Genesis can invoke directly.",
        "last_updated": "2026-10-15",
        "source": "code inspection",
    },
    "genesis_agent_bridge_transport": {
        "status": "EXISTS_IN_ARCHIVED_INTEGRATION_CODE",
        "evidence": "Genesis/integration-archive not found as a directory. However, the transport "
                    "contract exists in client.py (AgentRuntimeClient.submit_action → POST /v1/actions) "
                    "and actions.py (typed action intake adapter). genesis_action_bridge.py (new, v1) "
                    "provides the thin Genesis→AgentBridge module. derived_from: genesis_bridge.py + client.py.",
        "last_updated": "2026-10-15",
        "source": "code inspection + new module genesis_action_bridge.py",
    },
    "P16_to_P31_modules": {
        "status": "PROPOSED / PENDING_SOURCE_RECOVERY",
        "correction": "P16-P31 modules (P17 model/provider fabric, P19 workflows/skills, P20 worker "
                      "fabric, P21 Agent Bridge, P22 Genesis, P23 IDE, P25 authority, P26 knowledge/"
                      "memory, P27 transport, P30 resource placement, P31 provenance/evaluation/"
                      "observability) were discussed in the handoff but are NOT verified as deployed. "
                      "Treat all prior implementation claims as leads to inspect. If not found, "
                      "classify NOT_LOCATED rather than NOT_IMPLEMENTED.",
        "last_updated": "2026-10-15",
        "source": "OpenCode handoff §11 / V2 §4",
    },
    "lifecycle_recovery_tests": {
        "status": "LOCATED (9/9) + CLASSIFIED",
        "evidence": "After thorough search (original subagent search was incomplete due to "
                    "Nous Portal rate-limiting), all 9 claimed lifecycle/recovery scenarios "
                    "are found across 4 test files — NOT a single dedicated suite, but "
                    "scattered across: (1) heartbeat loss: test_hybrid_cloud_p0.py::test_instance_registry_gc_stale "
                    "(stale instances garbage collected); (2) worker crash: test_supervised_workers.py::test_killed_worker_is_detected_reconciled_and_retried_to_verified "
                    "(worker killed mid-run, detected STALLED, retried); (3) supervisor crash: test_supervised_workers.py::test_supervisor_crash_leaves_state_a_new_supervisor_can_continue "
                    "(supervisor dies, new supervisor attaches via SupervisedTask.attach and continues); "
                    "(4) restart: test_bridge_contract.py::test_restart_reloads_shared_ledger; "
                    "(5) checkpoint recovery: test_autonomous_loop.py::test_checkpoint_resume; "
                    "(6) stale lock: test_cross_process_state.py::test_the_lock_is_released_when_the_holder_dies; "
                    "(7) interrupted task: test_supervised_workers.py recover() returns 'INTERRUPTED' "
                    "(lines 84, 188); (8) handoff recovery: test_supervised_workers.py::test_supervisor_crash_leaves_state_a_new_supervisor_can_continue "
                    "(SupervisedTask.attach takes over existing task); "
                    "(9) power-loss-like interruption: test_supervised_workers.py::test_supervisor_and_worker_both_dead_recovers_from_checkpoint "
                    "(both processes killed, state recovered from durable files). "
                    "SUITE-CLASSIFICATION task: pytest-timeout NOT installed (config warnings expected); "
                    "test_fallback_skips_dead_model (120s socket timeout) now marked @pytest.mark.slow; "
                    "tests/conftest.py registers markers; TEST_CLASSIFICATION.md documents full suite.",
        "last_updated": "2026-10-15",
        "source": "code inspection + test suite search (corrected from NOT_LOCATED)",
    },
    "E2E007_lifecycle_evidence_fusion": {
        "status": "IMPLEMENTED + TESTED (11 passing)",
        "evidence": "Structured lifecycle evidence + evidence fusion (compute/bridge_lifecycle.py). "
                    "The supervisor can independently derive DELIVERED/ACKNOWLEDGED/STARTED/PROGRESSING/"
                    "COMPLETED/HANDOFF_READY from MULTIPLE evidence channels — transport evidence (adapter "
                    "created invocation, sent brief, obtained session, received output), task-specific action "
                    "(file/tool/test evidence), model declarations (ACK/START/COMPLETE), and independent QA. "
                    "Model markers are ONE optional channel among several — never mandatory. "
                    "Completion requires artifacts + tests + commit + INDEPENDENT QA (never the worker's "
                    "own word). Tested in tests/test_bridge_e2e007_lifecycle_evidence.py (11 tests).",
        "last_updated": "2026-10-16",
        "source": "compute/bridge_lifecycle.py + tests/test_bridge_e2e007_lifecycle_evidence.py",
    },
    "E2E008_standing_autonomous_loop": {
        "status": "IMPLEMENTED + TESTED (6 passing)",
        "evidence": "Standing autonomous loop (compute/bridge_standing_loop.py). Start the supervisor daemon "
                    "ONCE; it drains a READY queue through the bridge with NO manual runner invocation, "
                    "prompt insertion, task-B command, continue command, or owner input. Scheduler auto-selects "
                    "TASK-B after TASK-A is verified. Replaces per-task one-shot to the standing multi-task "
                    "supervisor (§30 gap closed). Tested in tests/test_bridge_e2e008_standing_loop.py (6 tests).",
        "last_updated": "2026-10-16",
        "source": "compute/bridge_standing_loop.py + tests/test_bridge_e2e008_standing_loop.py",
    },
    "H02_live_nested_worker_recall": {
        "status": "LIVE_VERIFIED (7 tests)",
        "evidence": "Real nested-worker recall acceptance over the ACTUAL BridgeControlChannel: "
                    "parent continues correctly after a child's recall; target team recalled; RECALL cascades "
                    "to all descendants; active/queued authority expires; late stale response from a recalled "
                    "worker is recorded but its side effects are DENIED (authorize_side_effects fails closed); "
                    "EMERGENCY_HALT denies all, lift is owner-only. Tested in "
                    "tests/test_bridge_h02_live_recall.py (7 tests), all PASSED.",
        "last_updated": "2026-10-16",
        "source": "compute/bridge_control.py + tests/test_bridge_h02_live_recall.py",
    },
    "H06_live_contradictory_claims": {
        "status": "LIVE_VERIFIED (6 tests)",
        "evidence": "Live contradictory-claims acceptance: two real contradictory claims → conflict detected "
                    "→ both preserved → resolution by INDEPENDENT EVIDENCE (no majority vote; no shorter-message "
                    "wins; no most-confident wins) → consistent result received. Only a VERIFIED_CONCLUSION can "
                    "supersede both; a newer claim alone does NOT win (no recency bias). Tested in "
                    "tests/test_bridge_h06_live_conflict.py (6 tests), all PASSED. Includes the full AT-26 path: "
                    "two claims → conflict → evidence-based resolution.",
        "last_updated": "2026-10-16",
        "source": "compute/conflict_resolution.py + tests/test_bridge_h06_live_conflict.py",
    },
    "programme_acceptance_gate_h12": {
        "status": "IMPLEMENTED (compute/programme_gate.py + build_h12_programme_gate)",
        "evidence": "Programme acceptance gate for V2 H12 minimum deployment. Evaluates live evidence: "
                    "orchestration+state, shared model gateway, two free inference routes, remote execution "
                    "target, genesis solo capability (NOT CURRENTLY VERIFIED — owner blocked), supervised live "
                    "team, INVARIANT_15 degradation safeguard, £0/free guard, durable message bus, evidence "
                    "register. Outputs MILESTONE_REACHED or NOT_YET with blocking failures. Success = completed "
                    "tasks + verifiable artefacts, NOT counts of providers/subagents/frameworks (H12).",
        "last_updated": "2026-10-16",
        "source": "compute/programme_gate.py",
    },
    "bridge_generic_transport": {
        "status": "IMPLEMENTED",
        "evidence": "Agent Communications Bridge is first-party generic (compute/worker_bridge_adapters.py): "
                    "OpenCodeAdapter (CLI, §13), CodexAdapter (rollout+exec, §31), InternalAgentAdapter (in-process, "
                    "$32), GuiAgentAdapter (GUI fallback, §14). Same canonical envelope across all transports. "
                    "Genesis uses the thin ActionProposal→POST intake module. Bridge scope guard (owner/workspace/tenant) "
                    "implemented in compute/bridge_scope.py.",
        "last_updated": "2026-10-16",
        "source": "compute/worker_bridge_adapters.py + compute/bridge_scope.py",
    },
    "full_agent_bridge_suite": {
        "status": "NOT_YET_VERIFIED_GREEN",
        "evidence": "Previous reports of 1,407 Agent Bridge tests and 1407+ acceptance tests are "
                    "NOT_YET_VERIFIED. The current fast suite (excluding slow mutation tests) shows "
                    "195 passing tests. The full suite (with slow tests) requires separate verification.",
        "last_updated": "2026-10-15",
        "source": "test suite run",
    },
    "worker_self_model_switch": {
        "status": "CORRECTED + SCHEMA_EXTENDED",
        "evidence": "Workers cannot switch their own models. OpenCode confirmed: '/models is user-side.' "
                    "Hermes owns model routing. WorkerInfo schema in task_dag.py extended with "
                    "supports_model_selection (can be launched with a selected model) and "
                    "supports_self_model_selection (can change model at runtime). OpenCode: "
                    "supports_model_selection=True, supports_self_model_selection=False. "
                    "Ollama: supports_model_selection=True, supports_self_model_selection=True. "
                    "Codex/Codex CLI: supports_model_selection=True, supports_self_model_selection=False "
                    "(owner gate for model changes). Agent Bridge: both False (tool executor, not model).",
        "last_updated": "2026-10-15",
        "source": "OpenCode handoff §9 + schema extension in task_dag.py",
    },
    "policy_bridge_network_origin_device_trust": {
        "status": "FIXED + TESTED + INDEPENDENTLY_VERIFIED",
        "evidence": "aether_policy_bridge.py EvalContext (line 287) previously discarded "
                    "network_origin and device_trust by setting them to None in __init__ "
                    "despite accepting them as constructor parameters. executor.py (line 323-324) "
                    "supplies network_origin='local' and device_trust=100. Fix: changed lines 296-297 "
                    "to store the constructor parameters. Regression tests: tests/test_policy_bridge_fields.py "
                    "(6 tests, all pass in 0.51s). Existing B04 tests: 15/15 pass (no regressions). "
                    "Commit: 798dcb0.",
        "last_updated": "2026-10-15",
        "source": "code inspection + runtime verification",
    },
    "H01_multitenant_isolation_design": {
        "status": "DESIGN_SPEC + CODE_INSPECTED + TESTED",
        "evidence": "H01 design document created (docs/H01_TENANT_ISOLATION_DESIGN.md): code "
                    "inspection report documenting 6 isolation gaps. tenant_id: str = '' field added "
                    "to 5 data models (TaskRecord, WorkerInfo, PrincipalContext, TeamRecord, "
                    "WorkerCareerRecord). All default to '' for backward-compatible single-owner mode. "
                    "AT-22 simulation tests: 12 tests, all pass. 86 tests pass across H01 + existing "
                    "suites with no regressions.",
        "last_updated": "2026-10-15",
        "source": "design document + code changes + test suite verification",
    },
    "BLOCKED_OWNER_CREDENTIAL_ROTATION": {
        "status": "NARROW_GATE_IMPLEMENTED + MODEL_CONFIG_FIXED + ROTATION_CHECKLIST_CREATED",
        "evidence": "Root cause of all 8 blocked tasks: profile model config pointing to "
                    "'stealth/space-bunny-alpha' (HTTP 404 model not found on Nous Portal). "
                    "Fixed: config.yaml model.default changed to 'poolside/laguna-s-2.1:free' "
                    "(free Nous Portal model, same as this session). All blocked tasks unblocked. "
                    "Rotation checklist created: HF_TOKEN first (read-only), then GROQ, GEMINI, "
                    "OPENROUTER last. Narrow gate: cloud routing uses provider=nous not openrouter, "
                    "so exposure only affects cloud provider routing, not local/Git work.",
        "last_updated": "2026-10-15",
        "source": "config fix + task unblocking + rotation checklist creation",
    },
}

# Mapping from old gap IDs to new (preserved as per V2 §5)
GAP_MAPPINGS = {
    "G26": "C01 — Persistent independent cloud execution",
    "G27": "D02 — Genesis persistent cloud existence/hierarchical supervision",
    "G28": "E01 — AI-native/semantic communication",
}
