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

## 2026-10-25: external proofs split from the repository gate

The 2026-09-25 baseline above counted 21 failures. The suite has since grown
to 2,370 tests. The 2026-10-25 pass addressed a different problem: the path
called "fast" still launched desktop applications, a real browser, hardware
probes and a live model runtime, so it measured this workstation rather than
the repository.

Disposition, with no test deleted, xfailed or weakened:

- **Whole module `slow`**: `test_actions_intake_mutations`,
  `test_approved_grant_mutations`, `test_desktop_e2e`, `test_ui_acceptance`.
  The first is the 35-40 minute mutation proof; the other three launch desktop
  applications or a real browser.
- **Per-test `slow`**: 3 Blender, 3 FreeCAD, 1 Cura, 1 OpenModelica, 5
  `TestBrowserReal` and 4 forced-refresh `test_device_runtime` tests. These
  prove an installed application or device; they are scheduled proofs.
- **Live Ollama is opt-in**: the live classes in
  `test_local_team_execution.py`, `test_model_lifecycle_leases.py` and
  `test_conversation_and_ollama_v2.py` require
  `AETHERIUS_LIVE_OLLAMA=1` as well as a reachable runtime. Without the
  variable they skip before any weights are loaded. On 2026-10-25
  `test_integration_step_ran` ran three real 3B inferences and held the gate at
  45% for more than eight minutes; `py-spy` showed the provider still polling
  `/api/ps` from its release path. That is a models-present proof, not a
  repository gate.
- **Kept fast on purpose**: refusal and safety tests that need no external
  process, including the keepass bridge tests (they use throwaway databases in
  the OS temp directory). `test_collision_oracle` was unmarked after measuring
  15.39 s for the module, below the 45 s budget.

`python -m pytest tests -m "not slow"` is the repository gate.
`python -m pytest tests` is the scheduled full proof; it additionally needs the
desktop applications, browsers and devices named above. Deselection is
reported, never silent: the fast run states the deselected count in its
collection line.

Measured fast gate on this host, 2026-10-25:

**Fast gate (repository-proof tests)**: 2,301 passed, 18 skipped, 1 failed, 50 deselected, 18 subtests passed in 2,158.66s (35:58).

- Sole fast-gate failure: `tests/test_policy_deny_gate.py::MatUnavailableTests::test_unknown_symbol_reports_not_found`
  (subprocess.TimeoutExpired after 120s) due to the MAT slow marker.

- Slow markers refined:
  - Whole-module: `test_actions_intake_mutations`, `test_approved_grant_mutations`, `test_desktop_e2e`, `test_ui_acceptance`
  - Per-test: 3 Blender, 3 FreeCAD, 1 Cura, 1 OpenModelica, 5 `TestBrowserReal`, 4 `test_device_runtime` tests
  - Live Ollama opt-in: requires `AETHERIUS_LIVE_OLLAMA=1` + `slow` marker

- KeePass module improved: 44 passed in 132.97s (down from 531s) after module-scoped templates and reduced fixture KDF cost

### Mutation-proof progress (2026-10-27)

The mutation proof now prints a start line for each mutation and a completion
line with the per-mutation and elapsed seconds:

```text
[mutation-proof] 23 mutations; progress follows
[mutation-proof] 1/23 start: intake bypasses protocol.validate_action
[mutation-proof] 1/23 done in 86.4s (elapsed 86.4s)
```

The documented full gate runs with `-s` (`python -m pytest tests -s`) so those
lines are not captured by pytest. The slow marker remains, so the default fast
gate does not run the proof. This closes the "looks hung" ambiguity: a watcher
sees which mutation is running and when it finished.

**Full gate** (includes desktop apps, browsers, hardware probes, live models) remains scheduled separately.

## Unresolved release impact

Until the file-behaviour class is fixed/scoped AND the Ollama class
is lane-scoped by owner decision, the Bridge suite cannot support a
release claim. This document is disposition, not acceptance.
