"""The lockfile pins the exact versions verification ran against.

pyproject deliberately keeps install ranges broad while the runtime stays
dependency-free. That is a valid packaging choice, but it leaves verification
unreproducible: two installs can satisfy the same ranges with different
packages. requirements-lock.txt closes that gap without touching the accepted
ranges. This test pins the lockfile's own contract.
"""
from __future__ import annotations

import re
import sys
import tomllib
import unittest
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCKFILE = REPO / "requirements-lock.txt"


def marker_applies(raw: str) -> bool:
    """Whether a requirement marker selects this verification environment.

    This intentionally supports only the simple markers pytest uses here.
    Anything else fails closed by counting as required: an unknown marker must
    expand the lock, never silently shrink it.
    """
    if ";" not in raw:
        return True
    marker = raw.split(";", maxsplit=1)[1].strip()
    if marker.startswith("extra =="):
        return False
    environment = {
        "sys_platform": sys.platform,
        "os_name": __import__("os").name,
        "platform_system": __import__("platform").system(),
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "python_full_version": __import__("platform").python_version(),
        "implementation_name": sys.implementation.name,
    }
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\s*(==|!=|<=|>=|<|>)\s*['\"]([^'\"]+)['\"]", marker)
    if not match:
        return True
    key, operator, wanted = match.groups()
    actual = environment.get(key)
    if actual is None:
        return True

    def version_tuple(value: str) -> tuple:
        return tuple(int(part) if part.isdigit() else part for part in re.split(r"[.-]", value))

    left, right = actual, wanted
    if key.startswith("python_"):
        left, right = version_tuple(actual), version_tuple(wanted)
    comparisons = {
        "==": left == right,
        "!=": left != right,
        "<=": left <= right,
        ">=": left >= right,
        "<": left < right,
        ">": left > right,
    }
    return comparisons[operator]


def lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCKFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.-]+)", line)
        if not match:
            raise AssertionError(f"lockfile entry is not an exact pin: {line!r}")
        pins[match.group(1).lower()] = match.group(2)
    return pins


class DependencyLockTests(unittest.TestCase):
    def test_lockfile_pins_the_verification_closure(self):
        pins = lock_pins()
        # Every declared optional package must have an exact locked version.
        with (REPO / "pyproject.toml").open("rb") as fh:
            pyproject = tomllib.load(fh)
        declared = set()
        for specs in pyproject["project"].get("optional-dependencies", {}).values():
            for spec in specs:
                declared.add(re.split(r"[<>=!~;\[ ]", spec, maxsplit=1)[0].strip().lower())
        for name in ("psutil", "pyyaml"):
            self.assertIn(name, pins)
            self.assertIn(name, declared)
        # The pytest runner's own dependencies must be locked too; omitting a
        # transitive test dependency would leave verification only half-pinned.
        required = set()
        for raw in metadata.requires("pytest") or []:
            name = re.split(r"[<>=!~;\s\[]", raw, maxsplit=1)[0].strip().lower()
            if marker_applies(raw):
                required.add(name)
        missing = {name for name in required if name not in pins}
        self.assertEqual(missing, set(), f"unlocked pytest dependencies: {sorted(missing)}")

    def test_locked_versions_match_this_verification_environment(self):
        for name, version in lock_pins().items():
            with self.subTest(package=name):
                self.assertEqual(metadata.version(name), version)


if __name__ == "__main__":
    unittest.main()
