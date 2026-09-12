# Cross-Device Architecture (v0.7)

Capability-based routing across heterogeneous nodes. Not every node runs a
full runtime: watches/phones offload to desktops/servers via explicit policy.

## Pipeline

`Task → TaskRequirements → Privacy/Policy → NodeRouter → AgentRouter →
ModelRouter → IDERouter (if required) → ToolRouter → Execution`.

Each router owns its domain; NodeRouter never duplicates model/tool logic.

## Node model

`NodeDescriptor` carries device class, two orthogonal dimensions —
resource class (`resource_class`: `CONSTRAINED_RUNTIME` vs `FULL_RUNTIME`,
what the hardware can sustain) and runtime role (`FULL_RUNTIME`,
`CLIENT_NODE`, `DELEGATION_NODE`, `SENSOR_NODE`, `DISPLAY_NODE`, what
function the node serves) — plus hardware, models/providers/agents/IDEs/tools
(concise advertisements, never full schemas), I/O presence, locality metadata,
and limits. No serial numbers or unnecessary hardware IDs.

Why this PC is role `FULL_RUNTIME` with resource class `CONSTRAINED_RUNTIME`:
it is desktop-class and runs the complete runtime stack (role), while 16 GB
RAM / 4 GB VRAM keeps it under the full-capacity hardware bar (resource).
`DELEGATION_NODE` is a separate role for high-resource server/workstation
nodes that accept offloaded work; a constrained box may still serve
delegated tasks within its budgets, but routers must not assume server-class
headroom from the role alone.

Local registration: `DeviceProfiler → DeviceCapabilityProfile →
node_from_device_profile() → NodeRegistry` (no duplicated probing).

## Privacy and locality

Privacy overrides performance. `LOCAL_ONLY`/`CURRENT_DEVICE_ONLY` mean the
current device only. `LOCAL_FIRST` prefers local/trusted execution and falls
back only where policy allows — private data is never silently sent to a
cloud provider, untrusted node, or unknown agent. Data locality
(`local`/`can_delegate`/`restricted`) routes tasks to where the data lives
(e.g. a watch asking about the MAT repo routes to the desktop); private
repositories are never auto-copied between nodes.

## Trust

Discovery ≠ trust; pairing ≠ authorization. Every remote delegation is
re-validated on the target (trust, pairing, privacy, capabilities, tool
authorization, audit). See PAIRING_AND_TRUST.md.

## Status

- REAL_NETWORK_LOCALHOST_VERIFIED: two-process loopback pairing, delegation,
  cancel, emergency-stop, replay/privacy/revocation rejections.
- REAL_CROSS_DEVICE_VERIFIED: NOT claimed; separate physical devices remain
  DEVICE_REQUIRED.
