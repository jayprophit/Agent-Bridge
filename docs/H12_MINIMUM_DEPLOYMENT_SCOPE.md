# H12: Minimum Useful Deployment & Architectural Safeguard Invariant

**Maps to:** V2 H12, A01, B04, C01, D01-D04, AT-05
**Status:** IMPLEMENTED + TESTED

## H12 Architectural Safeguard (hard-coded as runtime invariant)

> "Aetherius must never lose essential capabilities merely because a third-party
> service, model, cloud account, worker, or development tool becomes unavailable."

This safeguard is now hard-coded as **INVARIANT_15_DEGRADATION_RESILIENCE** in
`compute/supervisor_invariants.py`. It runs every scheduler cycle via
`check_all()` → `check_invariants()` in `compute/supervisor_runtime.py`.
If violated (a CRITICAL severity), the supervisor refuses to clear
`continuation_required` until a fallback is restored.

### How it works

The invariant consumes an `availability` block in the runtime snapshot
(`SupervisorRuntime._availability_snapshot()`), which classifies all
workers/providers into tier buckets:

| Tier | Meaning | Example |
|------|---------|---------|
| `local` | No network, no credentials | Ollama, git, local filesystem |
| `owned_free` | Nous Portal (owned entitlement) | poolside/laguna-s-2.1:free |
| `free_cloud` | Third-party free tiers | OpenRouter free, Groq free |
| `paid` | Paid tiers (never default) | OpenRouter paid |

Essential capabilities are mapped to their backing tier:

| Essential Capability | Required Tier |
|---------------------|---------------|
| `local_execution` | `local` |
| `free_inference` | `owned_free` |
| `git_access` | `local` |
| `local_storage` | `local` |

If any tier that backs an essential capability goes fully `OFFLINE` and no
other tier can cover it, the invariant fires a CRITICAL violation with
evidence and a fix suggestion.

### Minimum Useful Deployment Boundary

The current checkpoint (verified against `compute/supervisor_runtime.py`)
provides the following minimum deployment scope:

1. **Aetherius orchestration** — `SupervisorRuntime` with `HiveScheduler`
   + `ResourceGovernor` + `KnowledgeIndex` (all present in the checkpoint)
2. **One authenticated shared model gateway** — Nous Portal
   (`poolside/laguna-s-2.1:free`, authenticated via OAuth)
3. **Two authorized free inference routes** — Nous Portal (owned free tier)
   + Ollama (local, no network)
4. **One real remote execution target** — OpenCode CLI (local adapter in
   `supervisor_runtime.py`) + Codex CLI (fallback worker adapter)
5. **Genesis solo capability** — `genesis_action_bridge.py` (thin
   ~130 LOC module that bridges Genesis identity to Agent Bridge actions)
6. **One small supervised live team** — 3-role validation team (HERMES
   supervisor / OLLAMA_REVIEWER / OLLAMA_CODER)

### Degradation Scenarios

| Scenario | Behaviour |
|----------|-----------|
| Nous Portal offline | Ollama local inference still works (free_inference → owned_free fails, but local_execution preserved) |
| Both cloud + local offline | Supervisor refuses to clear `continuation_required`; H12 invariant fires CRITICAL |
| Provider credential rotated/exposed | §P0-E narrow gate blocks cloud routing, local work continues |
| Worker crash | §INVARIANT_4 worker stop handling re-spawns from checkpoint |

### Commercial Boundary

Personal non-commercial free tiers (Nous Portal free, OpenRouter free,
Groq free) must NOT be used for commercial Aetherius services. The current
deployment is single-owner/private per H12 requirement: "Keep first
deployment single-owner/private."

### Test Coverage

`tests/test_supervisor_invariants.py` includes:
- `test_invariant_15_stubs_when_no_availability_block` — STUBBED when block absent
- `test_invariant_15_stubs_when_no_essentials` — STUBBED when no essential_capabilities
- `test_invariant_15_passes_when_local_available` — PASS when local tier has an active provider
- `test_invariant_15_fails_when_local_fully_offline` — CRITICAL FAIL when essential tier is fully offline
- `test_invariant_15_passes_when_fallback_available` — PASS when a fallback tier covers the essential capability
