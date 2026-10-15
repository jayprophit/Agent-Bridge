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
}

# Mapping from old gap IDs to new (preserved as per V2 §5)
GAP_MAPPINGS = {
    "G26": "C01 — Persistent independent cloud execution",
    "G27": "D02 — Genesis persistent cloud existence/hierarchical supervision",
    "G28": "E01 — AI-native/semantic communication",
}
