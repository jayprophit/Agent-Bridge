"""Shared fixtures for the Bridge's suite.

The policy engine is a process-wide singleton, deliberately: "grants
persist across calls", so that a grant issued at session start is still
in force when the work happens. That is right for the product and
awkward for a suite, because fifteen test files use that engine and
each of them leaves grants behind for the next.

So the engine is reset before every test. A test then starts from the
default-deny state whatever ran before it, which is what a test of a
security decision needs: a decision that only holds because of what
another test left behind is not a decision the product makes.

Nothing here weakens a check. The grants are re-issued by the tests
that need them, in their own setUp, and the engine still denies
everything that has not been granted.
"""
from __future__ import annotations

import os
import sys

import pytest

# The suite imports the runtime by name, so the repository root has to
# be on the path.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _fresh_policy_engine():
    """Every test starts from the default-deny engine.

    The engine is a process-wide singleton so that grants persist
    across the calls of one job. In a suite that means a test sees
    whatever the test before it granted, and a security decision that
    only holds because of another test's leftovers is not a decision
    the product makes.
    """
    from aether_policy_bridge import reset_policy_engine
    reset_policy_engine()
    yield
    reset_policy_engine()
