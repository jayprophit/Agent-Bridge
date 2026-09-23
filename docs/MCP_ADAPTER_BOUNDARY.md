# MCP Adapter Boundary (REQ-mcp-adapter-boundary, P21)

MCP is a versioned, replaceable Bridge adapter. MCP != Agent Bridge.

## Rule

The bridge speaks its own protocol (`protocol.py`). MCP servers speak MCP.
`mcp_adapter.py` is the ONLY place the two meet, and the meeting is
descriptive, never executive. The adapter never executes, never grants,
and imports neither executor, bridge, policy nor owner modules (tested by
source scan). Anything discovered through MCP still executes only via
`protocol.validate_action` + policy + deterministic executor — a forged
bridge action built from an MCP tool name fails validation (tested).

## Contents

- **Version negotiation**: `SUPPORTED_MCP_VERSIONS` (newest first);
  `negotiate_version` returns the highest common version or raises
  `MCPVersionError`. Fails closed on empty/unknown versions.
- **Capability discovery**: `parse_discovery` yields typed `MCPTool` /
  `MCPResource` / `MCPPrompt` records; unknown fields preserved opaque in
  `raw`. Malformed entries fail with `MCPDiscoveryError`.
- **Bridge projection**: `to_bridge_capabilities` maps records to
  capability DESCRIPTIONS namespaced `mcp.<server>.*` with `mcp:` source.
  Descriptions may be advertised; they carry no authority.
- **Transports**: one `MCPTransport` interface. `LoopbackTransport`
  (labeled simulated) serves canned discovery for tests. stdio/websocket/
  SSE exist as declared kinds raising `MCPUnavailable` with reasons —
  no live backend is pretended. Real transports are owner-authorized
  runtime work.

## Tests

`tests/test_mcp_adapter.py` — 9 tests: negotiation (match, preference
order, closed failures), discovery parsing + malformed payloads, loopback
scope, description namespacing, no-execution-surface (attribute + import
scan), forged-action rejection through `validate_action`, transport
unavailability.

## Suite status (honest)

`tests/test_mcp_adapter.py`: 9/9 pass. Full Bridge suite: 1124 passed +
9 new, with 14 pre-existing environment failures in
`test_state_integrity.py` (5), `test_maintenance_v081.py` (4),
`test_recycle_patch_diff.py` (4), `test_secret_hygiene.py` (1) —
verified identical on the clean tree without this change (Windows
file-behavior differences), unrelated to the adapter.
