"""Debug Bridge execution."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge import BridgeConfig, run_bridge
from config import ContextSettings

workspace = Path.cwd()

# Create fixture
fixture_dir = workspace / ".bridge" / "delegation_cert"
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
    session_id="test-debug",
    task_id="task-debug",
)

task = (
    "Fix the Fibonacci function bug in .bridge/delegation_cert/fibonacci.py. "
    "The function calculate_fibonacci(n) has a bug: it returns "
    "calculate_fibonacci(n-1) + calculate_fibonacci(n-1) instead of "
    "calculate_fibonacci(n-1) + calculate_fibonacci(n-2). "
    "Fix the bug so all test assertions pass."
)

print("Starting Bridge...")
try:
    result = run_bridge(config, task)
    print(f"Result keys: {result.keys() if isinstance(result, dict) else 'not dict'}")
    print(f"Result: {result}")
except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()