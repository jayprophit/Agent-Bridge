"""Live closure fixture: off-by-one bug for the worker to fix."""

def total(items):
    """Sum a list - INTENTIONAL BUG for worker to fix."""
    s = 0
    for i in range(len(items)):   # BUG: skips last element
        s += items[i]
    return s


def test_total():
    assert total([]) == 0
    assert total([4]) == 4  # FAILS with bug
    assert total([1, 2, 3]) == 6  # FAILS with bug
    return "ALL_TESTS_PASS"
