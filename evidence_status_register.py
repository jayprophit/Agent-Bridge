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
        "status": "FIXED_PENDING_INDEPENDENT_QA",
        "evidence": "Fixed at commit 2701b24 ('security: enforce the zero-spend guard at two independent "
                    "boundaries'). Requires independent QA verification (task B04-INDEPENDENT-QA) "
                    "before ACCEPTED.",
        "last_updated": "2026-10-15",
        "source": "git commit 2701b24",
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
        "status": "NOT_LOCATED",
        "correction": "Claimed 9 lifecycle/recovery tests (heartbeat loss, worker crash, supervisor "
                      "crash, restart, checkpoint recovery, stale lock, interrupted task, handoff "
                      "recovery, power-loss-like interruption) were NOT located in the test suite. "
                      "This is NOT the same as NOT_IMPLEMENTED — source may exist but was not found. "
                      "Task H-SA-PROVENANCE was created to search for and create these tests.",
        "last_updated": "2026-10-15",
        "source": "OpenCode handoff §11",
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
        "status": "FALSE",
        "evidence": "Workers cannot switch their own models. OpenCode confirmed: '/models is user-side.' "
                    "Hermes owns model routing. Worker abstraction must distinguish "
                    "supports_model_selection (can be launched with a selected model) from "
                    "supports_self_model_selection (can change model at runtime). For OpenCode, "
                    "the latter is FALSE.",
        "last_updated": "2026-10-15",
        "source": "OpenCode handoff §9",
    },
    "policy_bridge_network_origin_device_trust": {
        "status": "FIXED",
        "evidence": "aether_policy_bridge.py EvalContext (line 287) previously discarded "
                    "network_origin and device_trust by setting them to None in __init__ "
                    "despite accepting them as constructor parameters. executor.py (line 323-324) "
                    "supplies network_origin='local' and device_trust=100. Fix: changed lines 296-297 "
                    "to store the constructor parameters. Verified: EvalContext now correctly "
                    "preserves network_origin='local' and device_trust=100.",
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
