# Bridge 21-Failure Release Disposition (2026-09-25)

Full-suite baseline: 1174 passed, 21 failed, 1 skipped. All 21 fail
identically on the clean tree (pre-existing). Pre-existing means NOT
caused by current work — it does NOT mean release-acceptable. Per-test
disposition below. No test deleted, xfailed, or weakened for this
analysis.

## A. 14 file-behaviour failures (Windows filesystem semantics)

| Test | Cause (evidence) | Release effect | Required action |
|---|---|---|---|
| test_state_integrity (5: journal_backup, exact_write, interrupted_multistep, parallel_safe, never_torn) | Atomic-write/journal semantics differ on Windows (exact-write/partial-file expectations) | Environment-specific: release on Windows needs these passing or scoped | Fixture/expectation correction for Windows semantics, or scope to POSIX; BLOCKED until dispositioned |
| test_maintenance_v081 SafeEdit (4) | Same family: hash/match/reconcile file expectations | Same as above | Same as above |
| test_recycle_patch_diff (4) | Multi-hunk patch/dry-run file expectations | Same as above | Same as above |
| test_secret_hygiene :: test_no_bridge_runtime_state | Machine-specific runtime state present | Environment-specific hygiene | Scope to clean-room/CI or fix fixture isolation |

Disposition: ENVIRONMENT-SPECIFIC, release-blocking for any release
whose scope includes Windows file behaviour (i.e. current scope).
Fix the fixtures/expectations or scope the environments — do not
weaken assertions to go green.

## B. 7 Ollama-down failures (optional-backend semantics)

| Test | Cause | Release effect | Required action |
|---|---|---|---|
| device_runtime :: ollama_protocol_detection | Ollama daemon stopped → UNKNOWN | Backend-absent behaviour | Keep: proves honest UNKNOWN |
| genesis_runtime :: live_rotation_granite_to_qwen | No live models | Requires live backend | HUMAN_REQUIRED env-gated; not a release signal without models |
| acquisition_queue :: fallback_skips_dead_model | Dead model endpoint | Fallback path untestable without backend | Same as above |
| prompts_presets :: unavailable_model_surfaced | Same family | Same | Same |
| runtime_v05 :: diagnostics_selfcheck + inventory_shape (2) | Inventory without models | Shape assertions need backend | Same |
| service_v05 :: models_sessions_schema | Same family | Same | Same |

Disposition: Ollama is OPTIONAL for current scope (NOT_INSTALLED /
UNAVAILABLE behaviour is the product contract). These 7 must either
run in a models-present CI lane or be explicitly scoped as
backend-gated — but must not be silently dropped from the release
report. Release scope decision (owner) determines whether a
models-present lane is release-critical.

## Unresolved release impact

Until the file-behaviour class is fixed/scoped AND the Ollama class
is lane-scoped by owner decision, the Bridge suite cannot support a
release claim. This document is disposition, not acceptance.
