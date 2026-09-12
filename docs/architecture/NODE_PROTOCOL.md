# Node Protocol (v0.7)

- `protocol_name`: `agent-bridge-node`
- `protocol_version`: `1.0` (min `1.0`, max `1.0`)
- Runtime: `0.7.0`; capabilities schema: `1.0`

## Handshake

Nodes exchange only: node ID, protocol/runtime versions, capability
summary, transport security status, pairing/trust status. Never: raw
credentials, environment variables, filesystem contents, secret config.

Incompatible versions return `PROTOCOL_VERSION_UNSUPPORTED`; no execution
is attempted afterwards.

## Task envelope (JSON-safe, minimum necessary context)

`protocol_version, delegation_id, task_id, session_id, source_node,
target_node, task_type, requirements, privacy_policy, requested
agent/model/provider/ide, required_tools, context_reference,
artifact_references, deadline_s, nonce, timestamp`.

No arbitrary Python objects. Large outputs travel as ArtifactRegistry
references (`ref, hash, size, origin_node, verified`), not giant bodies.

## Result envelope

`protocol_version, delegation_id, status, source/target node,
agent/model/provider/ide, tools_used, result_summary,
artifact_references, verification, timestamps, error_code`.
No raw stack traces cross nodes by default.

## Error codes

`NODE_OFFLINE, NODE_UNTRUSTED, NODE_NOT_PAIRED, AUTHENTICATION_FAILED,
PAIRING_REQUIRED, PAIRING_REJECTED, PAIRING_EXPIRED,
PROTOCOL_VERSION_UNSUPPORTED, TLS_REQUIRED, REMOTE_PLAINTEXT_DENIED,
PRIVACY_DENIED, CAPABILITY_UNAVAILABLE, TOOL_DENIED, DELEGATION_TIMEOUT,
DELEGATION_CANCELLED, REMOTE_EXECUTION_FAILED, REPLAY_REJECTED,
EMERGENCY_STOP_ACTIVE`.
