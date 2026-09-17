"""Debug Bridge execution more carefully."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge import BridgeConfig, run_bridge
from config import ContextSettings

workspace = Path.cwd()

# Create fixture
fixture_dir = workspace / "delegation_test_fixtures"
fixture_dir.mkdir(parents=True, exist_ok=True)
fixture_path = fixture_dir / "fibonacci.py"

content = '''"""Test."""

def calculate_fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 1)

def test_fibonacci():
    assert calculate_fibonacci(0) == 0
    assert calculate_fibonacci(1) == 1
    assert calculate_fibonacci(2) == 1
    assert calculate_fibonacci(5) == 5
    assert calculate_fibonacci(10) == 55
    return "ALL_TESTS_PASS"
'''

fixture_path.write_text(content, encoding="utf-8")

config = BridgeConfig(
    model="qwen2.5-coder:3b-instruct-q4_K_M",
    mode="hybrid",
    approval="AUTO_SAFE",
    workspace=workspace,
    ollama_url="http://127.0.0.1:11434",
    request_timeout_s=120,
    context=ContextSettings(budget_chars=8000, keep_recent_results=3),
    enable_reviewer=True,
    shell_profile="dev",
    non_interactive=True,
    dry_run=False,
    session_id="test-debug2",
    task_id="task-debug2",
    max_steps=10,  # More steps
)

task = (
    "Fix the Fibonacci function bug in delegation_test_fixtures/fibonacci.py. "
    "The function calculate_fibonacci(n) has a bug: it returns "
    "calculate_fibonacci(n-1) + calculate_fibonacci(n-1) instead of "
    "calculate_fibonacci(n-1) + calculate_fibonacci(n-2). "
    "Fix the bug so all test assertions pass."
)

print("Starting Bridge...")
try:
    result = run_bridge(config, task)
    print(f"Result type: {type(result)}")
    print(f"Result keys: {result.keys() if isinstance(result, dict) else 'not dict'}")
    print(f"Result ok: {result.get('ok') if isinstance(result, dict) else 'N/A'}")
    print(f"Result status: {result.get('status') if isinstance(result, dict) else 'N/A'}")
    print(f"Result error: {result.get('error') if isinstance(result, dict) else 'N/A'}")
    print(f"Result kind: {result.get('kind') if isinstance(result, dict) else 'N/A'}")
    print(f"Result steps: {result.get('steps') if isinstance(result, dict) else 'N/A'}")
    if isinstance(result, dict) and 'history' in result:
        print(f"History length: {len(result['history'])}")
        for h in result['history']:
            print(f"  Step {h.get('step')}: action={h.get('action')}, executed={h.get('executed')}, role={h.get('role')}, model={h.get('model')}")
    import json
    # Save full result for inspection
    (workspace / "bridge_result.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"Full result saved to bridge_result.json")
except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()