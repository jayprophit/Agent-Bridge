"""Per-file pytest timing harness.

Runs each test file individually with a wall-clock timeout wrapper so a
hanging test cannot block the whole suite.  Writes a JSON registry of
timings + outcomes to scripts/test_timing_registry.json.

Usage:  uv run python scripts/run_per_file_timing.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO / "tests"
OUT = REPO / "scripts" / "test_timing_registry.json"

# Per-file wall-clock budget.  A file that exceeds this is flagged HANG.
FILE_TIMEOUT_S = 45
# Per-test pytest-timeout (catches individual slow tests).
PYTEST_TIMEOUT = 15

files = sorted(p for p in TESTS_DIR.glob("test_*.py"))
results: list[dict] = []

for f in files:
    rel = str(f.relative_to(REPO))
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(f.relative_to(REPO)),
                f"--timeout={PYTEST_TIMEOUT}",
                "--timeout-method=thread",
                "-q", "--tb=no", "--no-header",
                "-p", "no:cacheprovider",
            ],
            cwd=str(REPO),
            capture_output=True, text=True,
            timeout=FILE_TIMEOUT_S,
        )
        elapsed = time.monotonic() - t0
        stdout = proc.stdout
        stderr = proc.stderr
        # Parse summary line like "12 passed in 1.23s" or "1 failed, 5 passed in 2.34s"
        # or timeout-related messages
        last_line = ""
        for line in reversed(stdout.strip().splitlines()):
            if line.strip():
                last_line = line.strip()
                break
        if "Timeout" in stdout or "Timeout" in stderr:
            status = "HANG_TIMEOUT"
        elif proc.returncode in (0, 5):  # 5 = no tests collected, 0 = all passed
            if "passed" in last_line or "no tests ran" in last_line:
                status = "OK"
            else:
                status = "UNKNOWN"
        else:
            status = "FAILED"
        results.append({
            "file": rel,
            "elapsed_s": round(elapsed, 2),
            "status": status,
            "tests_collected": stdout.count("::") if "::" in stdout else None,
            "summary_line": last_line[:200],
            "returncode": proc.returncode,
            "stderr_tail": stderr[-500:] if stderr else "",
        })
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - t0
        results.append({
            "file": rel,
            "elapsed_s": round(elapsed, 2),
            "status": "HANG",
            "tests_collected": None,
            "summary_line": "WALL_CLOCK_TIMEOUT",
            "returncode": -1,
            "stderr_tail": "",
        })
    print(f"[{status:>12}] {rel:60s} {elapsed:>6.1f}s", flush=True)

# Write registry
OUT.parent.mkdir(parents=True, exist_ok=True)
with open(OUT, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nRegistry written to {OUT}")

# Summary
by_status = {}
for r in results:
    by_status.setdefault(r["status"], []).append(r)
print("\n=== SUMMARY ===")
for status, items in sorted(by_status.items()):
    print(f"  {status}: {len(items)} files")
hangs = by_status.get("HANG", []) + by_status.get("HANG_TIMEOUT", [])
if hangs:
    print("\n=== HANGING FILES ===")
    for h in hangs:
        print(f"  {h['file']} ({h['status']}, {h['elapsed_s']}s)")
