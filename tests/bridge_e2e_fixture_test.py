"""Deterministic unit test for compute.resource_governor.class_reserve."""
from compute.resource_governor import class_reserve


def test_class_reserve_ordering():
    assert class_reserve("LIGHT") < class_reserve("HEAVY") > 0