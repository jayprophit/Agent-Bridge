"""Public repository secret/privacy hygiene tests (v0.8, convergence).

No passwords, API keys, tokens, cookies, private keys, pairing secrets,
captures or personal absolute paths in tracked source. .gitignore must
prevent accidental commit of runtime/private data. No open-source
license may be added without owner approval.
"""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bapi[_-]?key\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)\bpassword\b\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
    re.compile(r"(?i)\bpasswd\b\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
)

ALLOWLIST_FILES = {"test_secret_hygiene.py"}

RAW_CAPTURE_EXTS = (".wav", ".mp3", ".mp4", ".mov", ".avi", ".pcm")

REQUIRED_GITIGNORE = (
    "__pycache__/", ".venv", "venv/", ".env", ".bridge", "*.log",
)


class HygieneTests(unittest.TestCase):
    def _source_files(self):
        # local/ holds ignored non-product archives; hygiene guards product.
        for base, dirs, files in os.walk(REPO_ROOT):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__", ".bridge", "local")]
            for name in files:
                if name.endswith((".pyc", ".pyo")):
                    continue
                yield os.path.join(base, name)

    def test_no_hardcoded_secrets(self):
        hits = []
        for path in self._source_files():
            if not path.endswith((".py", ".json", ".js", ".html", ".txt")):
                continue
            if os.path.basename(path) in ALLOWLIST_FILES:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            for rx in SECRET_PATTERNS:
                m = rx.search(text)
                if m:
                    hits.append(f"{os.path.relpath(path, REPO_ROOT)}: "
                                f"{m.group(0)[:24]}...")
                    break
        self.assertEqual(hits, [], f"secret hits: {hits[:5]}")

    def test_no_committed_raw_captures(self):
        found = []
        for path in self._source_files():
            if path.lower().endswith(RAW_CAPTURE_EXTS):
                found.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(found, [], f"raw captures in tree: {found[:5]}")

    def test_no_bridge_runtime_state(self):
        self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, ".bridge")),
                         ".bridge runtime state must not be committed")

    def test_local_tree_is_git_ignored(self):
        import subprocess
        for area in ("history", "sessions", "captures", "logs", "cache",
                     "workspaces", "acceptance", "harness"):
            p = subprocess.run(
                ["git", "check-ignore", "-q", os.path.join("local", area)],
                capture_output=True, cwd=REPO_ROOT)
            self.assertEqual(p.returncode, 0,
                             f"local/{area} must be git-ignored")

    def test_gitignore_covers_private_data(self):
        with open(os.path.join(REPO_ROOT, ".gitignore"), encoding="utf-8") as f:
            text = f.read()
        missing = [entry for entry in REQUIRED_GITIGNORE if entry not in text]
        self.assertEqual(missing, [], f".gitignore missing: {missing}")

    def test_no_open_source_license_added(self):
        for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING",
                     "UNLICENSE"):
            self.assertFalse(os.path.exists(os.path.join(REPO_ROOT, name)),
                             f"{name} must not exist without owner approval")
        with open(os.path.join(REPO_ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        for grant in ("MIT License", "Apache License", "GNU GENERAL PUBLIC",
                      "BSD 3-Clause", "The Unlicense"):
            self.assertNotIn(grant, readme)

    def test_no_personal_absolute_paths_in_source(self):
        hits = []
        for path in self._source_files():
            if not path.endswith(".py"):
                continue
            if os.path.sep + "tests" + os.path.sep in path:
                continue
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    text = f.read()
            except OSError:
                continue
            if "C:\\Users\\jpowe" in text or "C:/Users/jpowe" in text:
                hits.append(os.path.relpath(path, REPO_ROOT))
        self.assertEqual(hits, [], f"personal paths in source: {hits[:5]}")


if __name__ == "__main__":
    unittest.main()
