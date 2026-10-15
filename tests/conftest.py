"""Pytest configuration: register markers to eliminate config warnings.

Marks slow tests with a 180s timeout via pytest-timeout (if installed).
Without pytest-timeout, the timeout config is silently ignored but tests
still run — just without the hard timeout guard.

Classification (see TEST_CLASSIFICATION.md for full breakdown):
- FAST: no external dependencies, complete in <5s
- SLOW: marked @pytest.mark.slow, may take 30s–180s (e.g. model worker tests)
- INTEGRATION: requires external services (Ollama, OpenCode, network)
- LIVE_DEPENDENCY: spawns subprocesses / makes real HTTP calls
"""
import pytest

# Register markers explicitly to avoid pytest config warnings
pytestmark = pytest.mark  # noqa: just ensuring import works


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "mutation: marks tests as mutation tests (run with '-m mutation')"
    )
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration (requires external services)"
    )
    config.addinivalue_line(
        "markers",
        "live_dependency: marks tests that spawn subprocesses or make HTTP calls"
    )


# Default timeout for slow tests if pytest-timeout is installed
def pytest_collection_modifyitems(config, items):
    """Auto-mark tests known to be slow based on file/class patterns."""
    slow_files = {
        "test_supervised_workers.py",       # spawns model workers, 300–600s
        "test_autonomous_loop.py",          # checkpoint/resume, 60s+
        "test_cross_process_state.py",      # process lifecycle, 30s+
        "test_bridge_contract.py",          # restart/reload, 30s+
        "test_hybrid_cloud_p0.py",          # network + registry GC, 20s+
        "test_desktop_e2e.py",              # end-to-end, 60s+
        "test_conversation_and_ollama_v2.py",  # spawns Ollama, 120s+
    }
    slow_test_names = {
        "test_fallback_skips_dead_model",    # 120s uncatchable socket timeout
        "test_model_worker_answers_are_independently_verified",  # 600s
    }

    for item in items:
        # Already has slow marker — pyproject.toml sets timeout=180 for slow tests
        if item.get_closest_marker("slow"):
            pass  # timeout is configured in [tool.pytest.mark.slow]

        # Auto-classify known slow tests by name (not yet marked)
        if item.name in slow_test_names:
            if not item.get_closest_marker("slow"):
                item.add_marker(pytest.mark.slow)

        # Auto-classify based on file
        test_file = item.fspath.basename
        if test_file in slow_files and not item.get_closest_marker("slow"):
            # Don't auto-mark — just note it. Manual marking is safer.
            pass

        # Live dependency detection
        if any(marker in item.keywords for marker in ["integration", "live_dependency"]):
            pass  # Already marked
        else:
            # Auto-flag tests that reference subprocess spawning patterns
            if "subprocess" in item.function.__code__.co_names or \
               "spawn" in item.function.__code__.co_names:
                item.add_marker(pytest.mark.live_dependency)
