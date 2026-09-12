# v0.7 Capability Summary (freeze)

## ToolRegistry (live audit, exact)

- TOTAL_REGISTERED_TOOLS: 350
- IMPLEMENTED_VERIFIED: 4 (strict: exact tool_id test reference; the 4th is
  node.delegate, evidenced by router-resolution + profile-gate denial test —
  not execution)
- IMPLEMENTED_UNVERIFIED: 262
- INTERFACE_ONLY: 0 (no AVAILABLE definition lacks a backend)
- PROVIDER_REQUIRED: 67
- MODEL_REQUIRED: 0
- NOT_INSTALLED: 13 (audio/video/speech backends)
- DEVICE_REQUIRED: 0
- ADMIN_REQUIRED: 0 (admin gating lives in profiles/policy)
- UNSUPPORTED_PLATFORM: 0
- DEGRADED: 0
- DISABLED: 4 (approval-gated pairing ops)

43 families, from 3 application/chart/graph to 26 browser. Full matrix:
`TOOL_CAPABILITY_MATRIX.json`.

## Registries (separate counts, never conflated)

- ToolRegistry: 350 | ModelRegistry: 7 | ProviderRegistry: 1 (ollama)
- AgentRegistry: 0 (external agents only; DefaultAgent is runtime-owned)
- IDERegistry: 2 (VS Code, Cursor) | NodeRegistry: 1 (local owner node)
- WorkspaceRegistry: 0 fresh (session-scoped) | ArtifactRegistry: 0 fresh

## Model capabilities (evidence-qualified)

- qwen3:0.6b: tool_calling BENCHMARK_VERIFIED (BRIDGE_STRUCTURED_ACTION)
- qwen3:1.7b: tool_calling BENCHMARK_VERIFIED (BRIDGE_STRUCTURED_ACTION)
- hhao/qwen2.5-coder-tools:3b: coding BENCHMARK_VERIFIED; tool_calling
  FAILED_PROBE (content-embedded format; native field never observed)
- qwen3.5:2b-q4_K_M: vision PROVIDER_REPORTED; live probe FAILED
- granite3.3:2b, qwen2.5-coder:3b-instruct, qwen3:latest: PROVIDER_REPORTED
  (never benchmarked)
- Native (provider-API) tool calling: NOT verified for any local model.

## Versions

runtime 0.7.0, api v1, session protocol 0.4 (wire-compatible), config
schema 2, prompts 1, benchmark schema/suite 1.0.0, node protocol
agent-bridge-node 1.0, capabilities schema 1.0.
