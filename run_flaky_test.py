#!/usr/bin/env python3
import subprocess
import sys

results = []
for i in range(10):
    result = subprocess.run(
        ['python', '-m', 'pytest', 'tests/test_state_integrity.py::ConcurrentWriteTests::test_same_file_never_torn', '-v'],
        capture_output=True, text=True
    )
    passed = 'PASSED' in result.stdout
    results.append(passed)
    status = "PASS" if passed else "FAIL"
    print(f"Run {i+1}: {status}")

passed_count = sum(results)
print(f"\nResults: {passed_count}/10 passed")
if passed_count == 10:
    print("CONSISTENTLY PASSES - not flaky on v0.8.2")
elif passed_count == 0:
    print("CONSISTENTLY FAILS - likely a regression")
else:
    print(f"FLAKY - {passed_count}/10 passes")