# GENESIS ↔ AGENT BRIDGE binding — v1.0.0

Status: EFFECTIVE 2026-09-19. Owner: Agent-Bridge repo (protocol authority).
Genesis repo holds its own side (agent definition); this doc binds versions.

Rule: ONE Genesis identity. Models/tools/workers never become identities.
Bridge is external reach, not Genesis anatomy.

## 1. Version pins (enforced by tests/test_genesis_bridge_binding.py)

| Artifact | File | Pin |
|----------|------|-----|
| Wire protocol | protocol.py PROTOCOL_VERSION | 0.4 (accepts 0.1–0.4) |
| HTTP API | docs/api_schema.json api + compat | api v1, runtime 0.6, protocol 0.4, sdk 0.6, config_schema 2 |
| Execution states | execution_contract.py | RECEIVED … VERIFIED + FAILED/REEVALUATING/CONTINUE_CURRENT_PLAN |
| Genesis agent definition | Genesis schemas/agent-definition.schema.json | schemaVersion const "1.0" |

Bump this doc's major version whenever a pin changes.

## 2. Request envelope (REQUIRED fields, P2 contract)

request_id, session_id, identity (Genesis EntityAddress), capability,
input (schema-validated), authority (approval outcome), resource_budget
(maxRuntimeMs, maxSteps, maxToolCalls, maxMemoryBytes per agent-def limits).

Response: result | error, receipt (audit), provenance, timestamps,
cancellation + timeout + retry semantics per execution_contract states.

Wire coverage of every field is VERIFIED in P5 against protocol.py actions;
fields not yet on the wire are CONTRACT-DECLARED, not implemented.

## 3. Approval mapping (DECLARED, verified in P5)

Genesis approvalMode never → autonomous low-risk only.
risky_actions → Bridge approval gate (approvals_pending) before execute.
always → every capability requires approval.
OWNER-only actions (browser/net/proc/git per protocol.py) always gate.

## 4. Explicitly deferred (not in v1)

- Genesis runtime EventEnvelope/LogicalClock mapping (include/genesis/runtime/runtime.hpp).
- Bridge runtime version alignment (bridge.py v0.4 vs api compat runtime 0.6).
- docs/api_schema_v05.json duplicate resolution.
- Genesis schemas/agent-definition vs agents/platform.hpp manual sync.
- Version negotiation handshake.

## 5. Safety invariants

Fail-closed on unknown capability, unsigned/expired authority, budget
exhaustion, or policy denial. Intelligence never implies authority.
Local-first: Bridge unreachable → Genesis continues without external reach.
