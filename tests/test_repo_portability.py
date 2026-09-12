"""Repository portability tests (v0.8, convergence).

The product must run from the canonical repository root with no runtime
dependency on the old development tree. Old-path occurrences are
classified: HISTORICAL_DOC (release reports/progress), TEST_FIXTURE
(this file's own allowlist), BUG (anything else -> must fix).
"""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OLD_MARKERS = (
    "OpenCode-Agent-Test",
    "agent_bridge_v07",
    "agent_bridge_v08",
    "Desktop\\OpenCode",
    "Desktop/OpenCode",
)

# Release evidence files may cite historical source paths as provenance.
HISTORICAL_DOC_RE = re.compile(
    r"^(V07_.*|V08_.*|.*_REPORT\.md|.*_MATRIX\.md|.*_AUDIT\.md|"
    r".*_PROGRESS\.md|.*_SUMMARY\.md|.*_MANIFEST\.md|CHAT_WORK_UI\.md|"
    r".*_ARCHITECTURE\.md)$")


def _iter_source_files():
    for base, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", ".bridge", ".venv",
                                "venv", "node_modules")]
        for name in files:
            if name.endswith((".pyc", ".pyo", ".log")):
                continue
            yield os.path.join(base, name)


def classify(path: str) -> str:
    name = os.path.basename(path)
    if HISTORICAL_DOC_RE.match(name):
        return "HISTORICAL_DOC"
    if os.path.sep + "tests" + os.path.sep in path:
        if name == "test_repo_portability.py":
            return "TEST_FIXTURE"
        return "BUG"
    return "BUG"


class PortabilityTests(unittest.TestCase):
    def test_no_bug_old_path_references(self):
        bugs = []
        for path in _iter_source_files():
            if not path.endswith((".py", ".json", ".txt", ".html", ".js")):
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            hits = [m for m in OLD_MARKERS if m in text]
            if hits and classify(path) == "BUG":
                bugs.append(f"{os.path.relpath(path, REPO_ROOT)}: {hits}")
        self.assertEqual(bugs, [], f"BUG old-path references: {bugs[:5]}")

    def test_service_default_root_portable(self):
        with open(os.path.join(REPO_ROOT, "service.py"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("OpenCode-Agent-Test", text)
        self.assertIn("AGENT_BRIDGE_ROOT", text)
        self.assertIn("import os", text)

    def test_core_imports_from_repo_root(self):
        import sys
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        import runtime  # noqa: F401
        import agent.default_agent  # noqa: F401
        import resources.scheduler  # noqa: F401
        import voice.realtime  # noqa: F401
        import avatar.creator  # noqa: F401
        import avatar.capture  # noqa: F401

    def test_old_root_not_required(self):
        # Nothing at import time may probe the retired development tree.
        import sys
        mods = [m for m in sys.modules if "opencode_agent_test" in m.lower()]
        self.assertEqual(mods, [])


if __name__ == "__main__":
    unittest.main()
