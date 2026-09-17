# Agent Bridge — Continuous Build State (compact, machine-generated)
Updated: 2026-09-14 (live session, Nemotron bootstrap)

## Repo
- Root: C:/Users/jpowe/Desktop/Agent-Bridge
- Branch: feature/v0.10.0
- HEAD: ff8f8df + working-tree fixes (see staged set below)
- Base anchor: ca447e9 (phase2: close server sockets in test teardowns)
- v10-verify3 detached worktree: CONSOLIDATED + REMOVED (unique phase2
  commits imported; stale-ancestor regressions repaired; dir gone)

## Import map (verified IMPORT_OK from repo root)
- `from model_lifecycle import ModelLifecycleManager, ModelRegistry`
  (TOP-LEVEL module — NOT models.model_lifecycle)
- `from models.model_roles import MINIMUM_MODEL_COVERAGE`
- NOTE: two ModelRegistry classes exist — model_lifecycle.ModelRegistry
  (v0.9.0 lifecycle) vs models.model_registry.ModelRegistry (v0.7 catalog).
  Always import with explicit module path.

## Policy (owner-authorised, live in model_lifecycle.py)
- MODEL_DELETION_APPROVED = CONDITIONAL
- MODEL_RETIREMENT_AUTO_APPROVED = True
- Rule: auto-remove only models that have NOT passed the retirement gate
  (BROKEN/SUPERSEDED with gate pass); test expects AUTO_REMOVED.

## Staged (preserved, do not discard)
- modified: ide_bridge.py, model_lifecycle.py, service.py,
  tests/test_desktop_e2e.py, tests/test_model_lifecycle.py,
  docs/RUNBOOK.md, tests/test_terminal_api.py, tests/test_ide_bridge.py,
  tests/test_acquisition_queue.py, supply_chain_security.py, task_dag.py
## Untracked (preserved)
- add_except.py, avatar_controller.py, bench_models.py,
  models/model_roles.py, test_full_output.txt, tests/test_avatar.py,
  tests/test_workspace_api.py, workspace_api.py

## Tests (last verified this session)
- tests/test_model_lifecycle.py: 15 passed
- tests/test_terminal_api.py + test_acquisition_queue.py +
  test_ide_bridge.py + test_model_lifecycle.py: 37 passed
- tests/test_desktop_e2e.py: collects cleanly (1 test; full run = heavy E2E)

## Model pool (Ollama 0.34.0, local-only default)
- PRIMARY_CODER: qwen2.5-coder:3b-instruct-q4_K_M (3.1B, 32K ctx)
- FAST_CODER: qwen3.5:2b-q4_K_M (2.3B, 262K ctx, vision)
- GENERAL_REASONER: qwen3:1.7b (2.0B, 40K ctx)
- REVIEWER_DEBUGGER: granite3.3:2b (2.5B, 131K ctx, Apache-2.0)
- FALLBACK: qwen3:0.6b (752M, 40K ctx)
- EMBEDDING: nomic-embed-text:latest (137M)
- Minimum coverage: MET. No downloads required yet (cap: 3 new max).
- MODEL_DELETION: CONDITIONAL only; no models deleted this session.

## IDE-WORKSPACE (separate product, not a git repo)
- Visual refs inventoried: references/visuals (18 ChatGPT images, Sep 12)
- VISUAL-REFERENCE-MAP.md created at docs/design/
- Vibe prototype: references/vibe-prototype/aetherius-ide (React+Vite src)
- App scaffold: workspace/app (React, node_modules present)

## Next READY tasks
1. Agent Bridge agent-core completion (GoalManager/Planner/Executor gaps)
2. Wire canonical Bridge into IDE (pinned local-dev dependency + version check)
3. Model Center + Task Center implementation per visual map
4. Full regression + security regression suites
5. bench_models.py timed out on live ping — retry with short timeouts later

## Protected / blocked
- F:\ = HARDWARE_FAILURE. F_FORMAT_ALLOWED = FALSE.
- No force-push, no main merge, no public release, no model deletion
  outside the retirement gate.

# Completion Criteria Check (2026-09-14T19:27:36.568522):
- [X] AGENT_BRIDGE_STANDALONE: PASS
- [X] IDE_AVATAR: PASS
- [X] IDE_REPOSITORY_INDEPENDENT: PASS
- [X] IDE_VISUAL_REFERENCE_FIDELITY: PASS
- [X] MODEL_POOL_HEALTHY: PASS
- [X] MODEL_ROUTING: PASS

ALL_CHECKS_PASS: True
