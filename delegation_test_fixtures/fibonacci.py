"""Delegation Certification Test - Fibonacci Bug Fix.

This file will be modified by the WORKER MODEL via Agent Bridge.
Supervisor must NOT modify this directly.
"""

def calculate_fibonacci(n: int) -> int:
    """Calculate nth Fibonacci number - INTENTIONAL BUG for worker to fix."""
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        # BUG: should be n-1 + n-2, not n-1 + n-1
        return calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2)


def test_fibonacci():
    """Test cases - will fail until bug is fixed."""
    assert calculate_fibonacci(0) == 0
    assert calculate_fibonacci(1) == 1
    assert calculate_fibonacci(2) == 1  # FAILS with bug
    assert calculate_fibonacci(5) == 5  # FAILS with bug
    assert calculate_fibonacci(10) == 55  # FAILS with bug
    return "ALL_TESTS_PASS"
