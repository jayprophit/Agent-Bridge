"""Dependency contract: what Agent Bridge needs to run, stated and checked.

Measured findings this test now pins (2026-09-30):

  * Every third-party import in the repository is either GUARDED (a
    module-scope ``try: import X except ImportError``) or declared in
    pyproject. There is no undeclared hard dependency, so
    ``dependencies = []`` is truthful rather than optimistic. That is a real
    property of this codebase and it is easy to lose by accident, so it is
    asserted rather than assumed.
  * The psutil version in pyproject and the version CI installs must be the
    SAME. They match today; nothing was checking, so they could drift apart
    and every CI run would still be green.
  * The test command declared in pyproject must actually discover the suite,
    so the documented command cannot rot into "runs nothing and passes".

The floating ``pyyaml>=6`` in the ``yaml`` extra is deliberately NOT changed
here: it is a declared optional extra whose two consumers both degrade to
NOT_INSTALLED, and tightening an owner's accepted version range is their
decision, not this test's. It is recorded as a bounded limitation instead.
"""
from __future__ import annotations

import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
CI = REPO / ".github" / "workflows" / "ci.yml"

SKIP_DIRS = {"node_modules", ".git", "local", "__pycache__", ".pytest_cache",
             "build", "dist", "integration-archive", ".bridge", "references"}

# Paths that are not importable from the runtime entry points but still have to
# run somewhere. A hard third-party import here is legitimate, but it must be
# DECLARED rather than accidental.
NON_RUNTIME_DIRS = {"benchmarks", "scripts", "examples"}

# Distribution name -> import name. They differ (PyYAML imports as `yaml`), and
# comparing them naively produces a false "declared but never used".
DIST_TO_IMPORT = {"pyyaml": "yaml"}


def repo_python_files():
    for path in REPO.rglob("*.py"):
        rel = path.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        yield path


def local_module_names():
    """Names importable from the repo root: first-party, not third-party.

    Includes the stem of EVERY tracked .py file, not just top-level ones, so a
    first-party helper living in a subdirectory (delegation_test_fixtures/
    closure_task.py) is not mistaken for a third-party package.
    """
    names = set()
    for path in repo_python_files():
        rel = path.relative_to(REPO)
        parts = list(rel.parts)
        names.add(path.stem)
        if len(parts) == 1:
            names.add(parts[0][: -len(".py")])
        else:
            names.add(parts[0])
            acc = ""
            for part in parts[:-1]:
                acc = f"{acc}/{part}" if acc else part
                names.add(part)
                names.add(acc)
    return names


def declared_packages(pyproject):
    project = pyproject["project"]
    packages = {}
    for name, spec in (project.get("dependencies") or []):
        packages[name] = spec
    for extra, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs:
            name = re.split(r"[<>=!~;\[ ]", spec, maxsplit=1)[0].strip()
            packages[f"{name} ({extra})"] = spec
    return packages


def module_scope_imports(tree):
    """(imported_top_level_name, is_guarded) for module-scope imports only.

    A function-local import is not a module requirement at all: it cannot stop
    the module from being imported, so it is not collected here at all. A
    module-scope import wrapped in try/except ImportError degrades honestly and
    is therefore also not a hard requirement. Only a bare module-scope import
    is a hard dependency.
    """
    guarded, hard = {}, {}

    def record(container, target):
        for node in container:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target[alias.name.split(".")[0]] = node.lineno
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import: first-party by construction
                    continue
                if node.module:
                    target[node.module.split(".")[0]] = node.lineno

    for node in tree.body:
        record([node], hard)
        if isinstance(node, ast.Try):
            handles_import_error = any(
                isinstance(h, ast.ExceptHandler)
                and h.type is not None
                and getattr(h.type, "id", None) == "ImportError"
                for h in node.handlers
            )
            if handles_import_error:
                record(node.body, guarded)
    return hard, guarded


class DependencyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with PYPROJECT.open("rb") as fh:
            cls.pyproject = tomllib.load(fh)
        cls.declared = declared_packages(cls.pyproject)
        cls.declared_names = {d.split(" ")[0] for d in cls.declared}
        cls.local = local_module_names()
        cls.hard_runtime = {}
        cls.hard_nonruntime = {}
        cls.hard_in_tests = {}
        cls.guarded = {}
        for path in repo_python_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            hard, guarded = module_scope_imports(tree)
            rel = path.relative_to(REPO)
            top = rel.parts[0]
            if top == "tests":
                bucket = cls.hard_in_tests
            elif top in NON_RUNTIME_DIRS:
                bucket = cls.hard_nonruntime
            else:
                bucket = cls.hard_runtime
            for name, line in hard.items():
                if name in sys.stdlib_module_names or name in cls.local:
                    continue
                bucket.setdefault(name, []).append(f"{rel}:{line}")
            for name, line in guarded.items():
                if name in sys.stdlib_module_names or name in cls.local:
                    continue
                cls.guarded.setdefault(name, []).append(f"{rel}:{line}")

    def _undeclared(self, bucket):
        return {n: s for n, s in bucket.items() if n not in self.declared_names}

    def test_no_undeclared_hard_third_party_dependency_in_shipped_code(self):
        """The property that makes `dependencies = []` true rather than lucky.

        Every optional package the runtime touches (psutil, wmi, pyyaml,
        win32com) is imported inside a function or behind try/except
        ImportError, so a clean clone without them still imports and runs - it
        just reports NOT_INSTALLED honestly. A bare module-scope third-party
        import in runtime code would break that guarantee, so there must be
        none, and none is undeclared.
        """
        self.assertEqual(
            self._undeclared(self.hard_runtime), {},
            "module-scope third-party import in runtime code that pyproject does "
            "not declare. Either declare it, or import it inside a function or "
            "behind try/except ImportError like the existing psutil/wmi/pyyaml "
            "sites do.",
        )

    def test_non_runtime_hard_imports_are_declared(self):
        """A benchmark harness may require a package, but must say so.

        This exists because the blanket claim "every third-party import is
        guarded" turned out to be too strong: benchmarks/benchmark_runner.py
        imports psutil at module scope because it genuinely needs it for
        measurements. That is legitimate - but it was undeclared, so the
        `benchmark` extra now states it instead of the claim hiding it.
        """
        self.assertEqual(
            self._undeclared(self.hard_nonruntime), {},
            f"non-runtime harness imports a package pyproject does not declare: "
            f"{self._undeclared(self.hard_nonruntime)}",
        )

    def test_runtime_optional_packages_are_not_promoted_to_hard_imports(self):
        """Runtime code must keep degrading instead of requiring these."""
        for pkg in ("wmi", "win32com", "yaml"):
            self.assertNotIn(
                pkg, self.hard_runtime,
                f"{pkg} is optional for the runtime and must not become a "
                f"module-scope import there",
            )

    def test_undeclared_hard_imports_in_tests_are_test_runner_only(self):
        """A test file may hard-import pytest; the declared command is unittest.

        That is a recorded exception rather than a gap: the declared
        test_command is `python -m unittest discover`, which never needs pytest,
        so a clean clone running the declared command does not either. Anything
        else hard-imported by a test IS a real gap.
        """
        undeclared = {n: s for n, s in self._undeclared(self.hard_in_tests).items()
                      if n != "pytest"}
        self.assertEqual(undeclared, {},
                         f"undeclared hard import(s) in tests: {undeclared}")

    def test_declared_extras_are_actually_used_somewhere(self):
        used = (set(self.guarded) | set(self.hard_runtime)
                | set(self.hard_nonruntime) | set(self.hard_in_tests))
        for name in self.declared_names:
            import_name = DIST_TO_IMPORT.get(name, name)
            self.assertIn(import_name, used,
                          f"declared dependency {name!r} is never imported")

    def test_psutil_pin_matches_ci(self):
        """Nothing enforced these agreeing. A drift would stay green forever."""
        spec = self.declared.get("psutil (telemetry)")
        self.assertIsNotNone(spec, "psutil must be declared under the telemetry extra")
        pinned = re.search(r"==\s*([0-9][^;\s]*)", spec)
        self.assertIsNotNone(pinned, f"psutil must be exactly pinned, got {spec!r}")
        self.assertIn(f'psutil=={pinned.group(1)}', CI.read_text(encoding="utf-8"),
                      "the psutil version installed by CI must equal the version "
                      "declared in pyproject")

    def test_declared_test_command_discovers_the_suite(self):
        """The documented command must run the tests, not just exit 0."""
        cmd = self.pyproject["tool"]["agent-bridge"]["test_command"]
        self.assertIn("unittest discover", cmd)
        self.assertIn("-s tests", cmd)
        modules = list((REPO / "tests").glob("test_*.py"))
        self.assertGreater(len(modules), 50,
                           "test discovery pattern no longer matches the suite")

    def test_ci_runs_a_meaningful_share_of_the_suite(self):
        """A gate that only runs 9 of 111 modules is not a gate.

        This asserts CI covers the suite it claims to gate. It is the check
        that would have caught a long period of core tests never running in CI.
        """
        text = CI.read_text(encoding="utf-8")
        total = len(list((REPO / "tests").glob("test_*.py")))
        if "unittest discover" in text:
            return  # the declared command runs everything
        listed = set(re.findall(r"tests\.(test_[a-z0-9_]+)", text))
        self.assertGreaterEqual(
            len(listed), total,
            f"CI runs {len(listed)} of {total} test modules; use the declared "
            f"'python -m unittest discover -s tests -p test_*.py' so the whole "
            f"suite gates merges",
        )


if __name__ == "__main__":
    unittest.main()
