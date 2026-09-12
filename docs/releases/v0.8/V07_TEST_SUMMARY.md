# v0.7 Test Summary (freeze)

- **Command**: `python -m unittest discover -s tests -p "test_*.py"`
- **Discovered**: 400 | **Passed**: 400 | **Failed**: 0 | **Errors**: 0 | **Skipped**: 0
- **Duration**: 455.273s | **Test files**: 45
- **Baseline**: 377/377 pre-convergence; +23 new this increment (11 node-transport,
  2 benchmark calibration-regression, 10 security-regression); no regressions.

## New coverage this increment

- `test_node_transport` (22→33): HTTPS E2E, remote-owner policy, version
  mismatch, capability/tool denial, result truncation.
- `test_benchmark` (13→15): calibration-engagement regression
  (import-cycle + full-profile fixes).
- `test_security_regression` (new, 10): path traversal, invented tools,
  adapter-less records, profile gates, plugin rejection, audit protection.
- `test_node_routing` (15), `test_registry_counts` (3): unchanged, re-verified.

## Per-module counts

- test_agent_discovery: 3, test_alternating: 4, test_benchmark: 15,
  test_browser: 7, test_collision_oracle: 11, test_commands_policy: 13,
  test_config_git: 5, test_device_runtime: 9, test_dryrun_replay: 5,
  test_events_approval: 6, test_executor_v01: 13, test_executor_v02: 7,
  test_failure_loops: 5, test_ide_discovery: 5, test_memory_cache_log: 5,
  test_memory_context: 3, test_milestones: 6, test_modes_approval: 6,
  test_node_routing: 15, test_node_transport: 33, test_oracle_conflict: 8,
  test_owner_activation: 11, test_owner_tools: 18, test_progress_mapping: 8,
  test_progress_semantic: 4, test_prompts_presets: 11, test_protocol_v01: 11,
  test_protocol_v02: 6, test_recycle_patch_diff: 11, test_registry_counts: 3,
  test_rerun_gui_genesis: 5, test_routing_review: 12, test_runtime_api: 8,
  test_runtime_owner: 8, test_runtime_v05: 15, test_sandbox_adversarial: 8,
  test_scorecard_export: 6, test_security_regression: 10,
  test_security_v03: 12, test_service_sdk: 15, test_service_v05: 7,
  test_shell_contract: 9, test_shell_e2e: 5, test_verification_e2e: 4,
  test_versions_cleanup: 9.
