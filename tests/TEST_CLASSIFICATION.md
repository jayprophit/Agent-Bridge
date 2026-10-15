# Test Suite Classification

Classification of all test files in `tests/` into FAST, SLOW, INTEGRATION, and LIVE_DEPENDENCY categories.

## Categories

- **FAST**: No external dependencies. Tests run in <5s each. Safe to run on every commit.
- **SLOW**: Tests that may take 30s–180s. Marked `@pytest.mark.slow`. Deselect with `-m "not slow"`.
- **INTEGRATION**: Tests that require external services (Ollama, OpenCode API, network access).
- **LIVE_DEPENDENCY**: Tests that spawn subprocesses or make real HTTP calls.

## Command Reference

```bash
# FAST only (recommended for CI):
python3 -m pytest tests/ -m "not slow" -x

# All non-live tests (no subprocess/network):
python3 -m pytest tests/ -m "not live_dependency" -v

# Full suite including slow (requires 75+ min):
python3 -m pytest tests/ -v

# Specific categories:
python3 -m pytest tests/ -m "slow"      # slow tests only
python3 -m pytest tests/ -m "integration"  # integration tests only
```

## Classification Table

| File | Tests | Markers | Category | Notes |
|---|---|---|---|---|
| `test_acquisition_queue.py` | 11 | 1 slow | FAST/SLOW | `test_fallback_skips_dead_model` is SLOW (120s socket timeout) |
| `test_action_id_uniqueness.py` | 9 | 0 | FAST | |
| `test_action_matrix.py` | 17 | 0 | FAST | |
| `test_actions_intake.py` | 41 | 0 | FAST | |
| `test_actions_intake_mutations.py` | 1 | 0 | FAST | |
| `test_agent_build.py` | 11 | 0 | FAST | |
| `test_agent_discovery.py` | 3 | 0 | FAST | |
| `test_ai_gateway_and_knowledge_fabric.py` | 23 | 0 | INTEGRATION | Knowledge fabric wiring tests |
| `test_ai_gateway_and_knowledge_fabric_v2.py` | 24 | 0 | INTEGRATION | |
| `test_alternating.py` | 4 | 0 | FAST | |
| `test_app_registry.py` | 9 | 0 | FAST | |
| `test_approved_grant_mutations.py` | 1 | 0 | FAST | |
| `test_autonomous_loop.py` | 8 | 0 | SLOW | Checkpoint/recovery tests |
| `test_avatar.py` | 6 | 0 | FAST | |
| `test_avatar_capture.py` | 9 | 0 | FAST | |
| `test_avatar_creator.py` | 16 | 0 | FAST | |
| `test_avatar_ui.py` | 16 | 0 | FAST | |
| `test_b04_independent_qa.py` | 28 | 0 | FAST | Independent B04 QA tests |
| `test_benchmark.py` | 15 | 0 | LIVE_DEPENDENCY | Requires psutil, benchmarks |
| `test_blender_adapter.py` | 8 | 0 | INTEGRATION | Blender subprocess |
| `test_bridge_contract.py` | 11 | 0 | INTEGRATION | Bridge restart/reload tests |
| `test_browser.py` | 7 | 0 | INTEGRATION | Browser automation |
| `test_business_rules.py` | 15 | 0 | FAST | |
| `test_circuit_breaker.py` | 11 | 0 | FAST | |
| `test_collision_oracle.py` | 11 | 0 | FAST | |
| `test_commands_policy.py` | 13 | 0 | FAST | |
| `test_comms.py` | 10 | 0 | INTEGRATION | Communication protocol tests |
| `test_compat.py` | 20 | 0 | FAST | |
| `test_compute_routing.py` | 11 | 0 | INTEGRATION | Compute routing with subprocess |
| `test_compute_runtime_audit.py` | 21 | 0 | INTEGRATION | Runtime audit tests |
| `test_config_git.py` | 8 | 0 | INTEGRATION | Git config tests |
| `test_conversation_and_ollama_v2.py` | 14 | 0 | LIVE_DEPENDENCY | Spawns Ollama |
| `test_cost_policy_boundary.py` | 15 | 0 | FAST | B04 boundary tests |
| `test_cross_process_state.py` | 6 | 0 | SLOW | Process lifecycle (locks, recovery) |
| `test_desktop_e2e.py` | 12 | 0 | LIVE_DEPENDENCY | End-to-end desktop tests |
| `test_device_runtime.py` | 8 | 0 | FAST | |
| `test_distributed_tracing.py` | 9 | 0 | INTEGRATION | |
| `test_dryrun_replay.py` | 7 | 0 | FAST | |
| `test_genesis_runtime.py` | 18 | 0 | FAST | |
| `test_hybrid_cloud_p0.py` | 15 | 0 | INTEGRATION | Network + registry GC |
| `test_local_team_execution.py` | 22 | 1 slow | FAST/SLOW | |
| `test_migration_provenance.py` | 42 | 8 skipif | FAST/SLOW | Many skipif for catalog |
| `test_node_routing.py` | 10 | 0 | FAST | |
| `test_policy_bridge_fields.py` | 6 | 0 | FAST | |
| `test_runtime_v05.py` | 14 | 0 | INTEGRATION | |
| `test_supervised_workers.py` | 15 | 6 slow | FAST/SLOW | 6 tests marked slow (model workers) |
| `test_supervisor_runtime.py` | 8 | 0 | INTEGRATION | Supervisor runtime tests |

## Known Slow Gate

`test_acquisition_queue.py::TestRouterFallbackReal::test_fallback_skips_dead_model` —
spawns an Ollama model probe with a 120s uncatchable socket timeout. This is the
primary cause of the "suite hang" misdiagnosis. Properly marked `@pytest.mark.slow`
and deselectable with `-m "not slow"`.

## pytest-timeout Status

The `pyproject.toml` configures `timeout = 120` and `timeout_method = "thread"`,
plus `[tool.pytest.mark.slow]` with `timeout = 180`. However, the `pytest-timeout`
plugin is **NOT installed** in the current venv. Installing it requires:

```bash
python3 -m pip install pytest-timeout
```

Until installed, the timeout config options produce "Unknown config option" warnings.
The `@pytest.mark.slow` marker still works for test selection (`-m "not slow"`),
but there is no hard execution timeout guard.
