"""Delegation Certification Test 2 - Add Function Bug Fix."""

def add(a: int, b: int) -> int:
    """Add two numbers - INTENTIONAL BUG for worker to fix."""
    return a + b  # BUG: should be a + b


def test_add():
    assert add(2, 3) == 5  # FAILS with bug
    assert add(-1, 1) == 0  # FAILS with bug
    assert add(0, 0) == 0
    return "ALL_TESTS_PASS"
