# v0.8 Folder Reconciliation (final consolidation, non-destructive)

Old root: `C:/Users/jpowe/Desktop/OpenCode-Agent-Test` (15 top-level items,
READ ONLY, nothing deleted).
New repo: `C:/Users/jpowe/Desktop/Agent-Bridge` (canonical product root).
Machine detail: V08_FOLDER_RECONCILIATION.json (per-file hashes).

## Old-root top level

| Old path | Classification | Files | Bytes | Action |
|---|---|---|---|---|
| .git | CACHE | 42 | 16966237 | LEAVE (old-root VCS metadata) |
| .qodo | CACHE | 0 | 0 | LEAVE (empty tool dir) |
| MAT_integration_01 | MAT_OR_EXTERNAL_PROJECT | 15722 | 181984157 | LEAVE (MAT project; never inside Agent-Bridge) |
| agent_bridge_v01..v06 | HISTORICAL_AGENT_BRIDGE_SOURCE | 11..122 ea | — | LEAVE (history via git/tags/docs) |
| agent_bridge_v07 | HISTORICAL_AGENT_BRIDGE_SOURCE | 240 | 4059264 | LEAVE (frozen v0.7.0 ref) |
| agent_bridge_v08 | ACTIVE_AGENT_BRIDGE_SOURCE | 301 | 6082439 | MIGRATED (per-file below) |
| agent_test.py | TEMPORARY | 1 | 45 | LEAVE (45-byte scratch print) |
| genesis_integration_01 | MAT_OR_EXTERNAL_PROJECT | 137 | 156127 | LEAVE (Genesis-side sandbox) |
| opencode_bridge_test_01 | MAT_OR_EXTERNAL_PROJECT | 11 | 28626 | LEAVE (scratch bridge test) |
| test_output.txt | LOG | 1 | 3960 | LEAVE (stale UTF-16 traceback) |

No `Agent-Bridge/OpenCode-Agent-Test/...` or
`Agent-Bridge/agent_bridge_v08/...` nesting was created. No historic tree
was dumped into the active repo. No MAT/Genesis file was modified.

## v0.8 per-file reconciliation (301 files)

| Migration status | Count | Meaning |
|---|---|---|
| DUPLICATE_ALREADY_MIGRATED | 278 | byte-identical copy already in repo |
| MIGRATED-WITH-PORTABILITY-FIX | 8 | service.py, cli.py, 3 bridge configs, 2 old E2E scripts, hardware_profiler.py |
| DIVERGED-NEWER-IN-REPO | 8 | README (repo's own), regenerated matrices/reports/progress, avatar exports |
| TEMPORARY (excluded) | 4 | test_output.txt, integrity_current.json, dxdiag_output.txt, e2e_plan_script.txt |
| AGENT_BRIDGE_FIXTURE (excluded) | 3 | owner_full_access_test/, review_fix_e2e_ws/ scratch workspaces |
| **MISSING-FROM-REPO** | **0** | nothing required left behind |

New-repo-only additions (convergence): avatar/creator.py, avatar/capture.py,
voice/realtime.py, 5 new test files, 3 real acceptance scripts + reports,
audit/verification reports, .gitignore hardening.

## Retirement inputs

- Agent Bridge source: fully migrated, 0 missing, 0 BUG path deps.
- MAT/external projects: all remain in old root (MAT untouched by design).
- See final verdict for SAFE_TO_RETIRE determination.
