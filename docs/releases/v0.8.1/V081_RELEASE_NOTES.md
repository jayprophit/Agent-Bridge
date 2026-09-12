# Agent Bridge v0.8.1 — Reliability and Repository Hardening

Classification: MAINTENANCE / RELIABILITY / REPOSITORY-HARDENING PATCH.
Not v0.9. Public contracts unchanged (runtime, agents, tools, providers,
/v1 API, SDK, CLI, approvals, checkpoints).

## One-root consolidation

`Agent-Bridge-History-Archive/` → `local/history/`,
`OpenCode-Harness-Archive/` → `local/harness/`,
`Agent-Bridge-Local-Acceptance/` → `local/acceptance/v0.8.0-owner-acceptance/`
(all hash-verified identical, sources gone). New canonical `local/`
tree (acceptance/archives/captures/cache/downloads/history/harness/logs/
models/runtime/sessions/temp/workspaces), git-ignored and enforced by
test, with `localdirs.py` resolution (explicit > AGENT_BRIDGE_LOCAL /
AGENT_BRIDGE_ROOT env > repo root; no hard-coded home/Desktop).

## Repository shape (deliberately incremental)

Kept: flat top-level runtime modules (ADR-001), flat `tests/`
(ADR-002), schemas beside docs (frozen reports pin the paths).
Added: `pyproject.toml` (no `[tool.pytest]`, so stdlib discovery stays
default), `SECURITY.md`, `CHANGELOG.md`, `docs/adr/`, `.github/workflows/ci.yml`
(fast subset), `examples/{basic,local-model,tool-use,integrations}`,
`docs/releases/v0.8.1/`.

## Reliability fixes (from real local-model acceptance)

1. **Ollama think control**: `think=True/False/None` negotiated through
   generate/stream/tool_call; omitted unless explicitly passed (older
   models unaffected); `thinking_chars` surfaced in metadata.
   qwen3:0.6b + qwen3:1.7b verified non-empty through the adapter.
2. **Verified completion**: `expected_artifacts` + `verify_command` config;
   finish yields VERIFIED_COMPLETE only on evidence, else
   MODEL_CLAIMED_COMPLETE (never falsified). Defaults preserve old behavior.
3. **Test-runner discovery**: project config → installed runners → stdlib
   unittest; configured-but-missing pytest reported as a dependency
   requirement instead of a confusing failure.
4. **Safe-edit repair**: `expected_hash` optimistic concurrency — stale
   reads return EDIT_CONFLICT with current hash + preview (no mutation);
   misses return EDIT_MISS with hash + preview; successes chain hashes.

## Session continuity finding

Investigated: no narrow defect. Continuity = stable session id + shared
files + completed-action dedup (crash-safe, no double execution).
Conversational carryover across separate runs is model-context-bound and
belongs to later memory/IDE work — documented, not redesigned here.

## Known model limitations (unchanged, honest)

Weak small-model reasoning/planning, cold load latency, 0.6B engineering
limits, 1.7B general limits. Routing + task sizing handle these; the
bridge does not pretend otherwise.

## Verification

- Targeted: think control (live qwen3), completion, runner discovery,
  safe edit, localdirs, portability, hygiene, approvals, rollback.
- Live retest (coder-3b, disposable workspace under local/acceptance/):
  WRITE → TEST → FAIL (real) → DIAGNOSE → REPAIR → RETEST → PASS (4/4)
  → VERIFY → FINISH with VERIFIED_COMPLETE.
- Full regression: see manifest (all discovered tests green).
