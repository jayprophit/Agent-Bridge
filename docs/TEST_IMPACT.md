# Test Impact Prediction (REQ-p21-test-impact, P21)

Change-aware test selection: changed files → dependency graph →
historical failures → fast relevant test set. Owner: Agent-Bridge.

## Position (`test_impact.py`)

- `testmap.py` stays the heuristic single-file mapper (changed →
  tests with confidence). This module is the PLAN layer that did not
  exist: transitive traversal, history signals, mandatory tests,
  deterministic ordered plans with per-test reasons.
- `SessionMemory` failed[]/tests_run[] and `ProblemMemory` are history
  SOURCES through a plain-dict interface; this module stores nothing.
- `resultkit.py` scorecards record execution OUTCOMES; plan states live
  here. A plan is not a result.

## Contract

`predict(changed_files, universe, graph, history, mandatory)`:

- Changed files: explicit project-relative paths (absolute/traversal
  rejected). Universe: explicit test list (never invented).
- Direct dependents → RUN/DIRECT_DEPENDENCY; transitive → RUN with
  TRANSITIVE_DEPENDENCY + path; changed test files RUN themselves
  (SELF_TEST); weak `test_<stem>` matches recorded as NAME_MATCH.
- Cycles terminate via visited-dedup BFS; ordering deterministic.
- History is additional evidence only: failures on RUN tests add
  HISTORICAL_FAILURE; flaky adds HISTORICALLY_FLAKY metadata without
  forcing runs; no history proceeds with other signals
  (NO HISTORY != CLEAN HISTORY).
- Unknown code files implicate the universe conservatively
  (UNKNOWN_IMPACT → RUN); unknown non-code files are noted, never
  force runs. Deleted files work (string graph, no existence check).
- Mandatory list beats prediction (policy input, not hardcoded).
- States are exactly RUN / SKIPPED_BY_PREDICTION; skips stay visible
  with reasons — never converted to pass.
- `build_import_graph(root)`: bounded deterministic AST import graph
  (stdlib ignored, unparseable files contribute nothing, cycles fine).

## Boundaries

No model/cloud dependency. No execution inside prediction (plan →
existing runner). No universal score. Skipped != evidence of
correctness (EvidenceGate unchanged). Fast set != clean-room proof
(clean-room stays BLOCKED). Security tests are caller-mandatory, not
auto-skipped.

## Tests

`tests/test_test_impact.py` — 12 tests: input validation, cycle
termination, direct/transitive/self/deleted impact, conservative
unknowns, history-as-evidence, mandatory override, skip honesty,
graph builder determinism. Predictor validated by direct targeted
tests + the existing full baseline, never by its own selection.
