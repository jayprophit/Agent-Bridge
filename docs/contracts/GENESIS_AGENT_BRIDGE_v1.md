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

## 6. Principal context (P22/1)

Actions may carry `principal: {kind, id, on_behalf_of?}` where kind is
genesis, worker or owner. Principals are validated input plus journal
evidence only: unknown/malformed kinds, empty ids, worker-impersonates-
Genesis and owner/Genesis collapse are denied before grant evaluation, and
a principal can never grant, approve or widen. Executor journal entries
retain the validated principal; idempotent resubmission preserves it.

## 7. Deterministic execution boundary (P21)

Probabilistic intelligence ends where typed execution begins. Model output
is parsed into validated structured actions (protocol.validate_action
rebuilds allowlisted dicts — prose is never authority; unknown capabilities
fail closed). Principals, grants and approvals travel only through trusted
runtime paths, never inside model payloads. Dispatch over the registered
capability set is deterministic; unavailable adapters fail honestly, never
with simulated success. Writes verify by read-back hash compare and
mismatches surface as VERIFICATION_FAILED, distinct from execution success.
Journal entries carry deterministic evidence hashes. Timeouts on mutating
operations yield UNKNOWN_OUTCOME (never assumed); read-only timeouts yield
TIMED_OUT. Idempotent replay never duplicates side effects. Proven by
tests/test_deterministic_execution.py (15 tests).

## 8. OWNER_FULL_CONTROL profile v1 (P25/1)

A versioned explicit owner grant for ordinary reversible operations
(filesystem read/list/write/edit/patch/mkdir/move/copy, shell execute).
It is not a bypass: default-deny stands, protected actions (permanent
delete, credential/security-policy/finance/firmware/physical flags) are
never auto-granted, unknown future capabilities are never inherited, and
session-bound grants isolate sessions (workers never inherit the grant).
Activation requires an explicit owner-authorized call no model, skill,
workflow, routine, worker or external agent can forge. Revocation removes
the tagged grants (history preserved); expiry is clock-checked. Proven by
tests/test_owner_full_control.py (21 tests).
