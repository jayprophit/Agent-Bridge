# Changelog

## v0.8.1 — Maintenance / Reliability / Repository-Hardening (branch maintenance/v0.8.1)

- One-root consolidation: history/harness/acceptance archives moved under `local/` (untracked); `local/` policy + `localdirs` resolution helper.
- Reliability fixes: Ollama think control (`think=` negotiated, never blind); evidence-aware completion (`VERIFIED_COMPLETE` vs `MODEL_CLAIMED_COMPLETE`); test-runner discovery (config → installed → stdlib unittest); safe-edit expected-hash conflicts with reconcile context.
- Session continuity investigated: no narrow defect (continuity = session id + files + completed-action dedup); conversational carryover documented as model-context-bound future work.
- Repository: pyproject metadata, SECURITY.md, ADRs, CI workflow, examples, release docs under docs/releases/v0.8.1/.
- Public contracts unchanged (runtime, agents, tools, providers, /v1 API, SDK, CLI, approvals, checkpoints).

## v0.8.0 — Pre-Autonomy Standardization Release (tag v0.8.0, frozen)

- 549 tests green; 370 tools; 450/450 traceability; real local-model autonomy proven.
- Frozen. See docs/releases/v0.8/.
