"""Deterministic fake model provider for v0.3 unit tests (no Ollama)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def tracked_files(root: Path | None = None) -> list[Path]:
    """Every file Git is tracking, as absolute paths.

    A check that says "the repository contains no secret" has to look at
    the repository and not at the directory. The working tree holds
    things the repository does not: a local intake, a virtualenv, a
    branch variant that was deliberately excluded from tracking, and the
    runtime state the bridge itself writes. Those are the machine's
    business and not the repository's, and a test that fails on them
    reports a fault that is not there.

    So the tracked tree is the subject, and the fallback to a file walk
    is only for a root that is not a repository at all.
    """
    base = Path(root) if root is not None else REPO_ROOT
    try:
        proc = subprocess.run(
            ["git", "-C", str(base), "ls-files", "-z"],
            capture_output=True, timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        proc = None
    if proc is not None and proc.returncode == 0 and proc.stdout:
        names = [n for n in proc.stdout.decode("utf-8", "replace").split("\0") if n]
        found = [base / n for n in names]
        if found:
            return found
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                        if d not in {".git", "__pycache__", ".bridge", "local",
                                     ".opencode", "node_modules", ".venv",
                                     "variants", "build", "dist"}]
        for name in filenames:
            out.append(Path(dirpath) / name)
    return out


class FakeProvider:
    def __init__(self, script: list[str], model: str = "fake-test-model"):
        self.script = list(script)
        self.model = model
        self.calls = 0

    def list_models(self) -> list[str]:
        return [self.model]

    def chat(self, messages, temperature: float = 0.1, num_predict: int = 640) -> str:
        self.calls += 1
        if self.script:
            return self.script.pop(0)
        return '{"action":"finish","message":"default-finish"}'


class RoleFakeProviders:
    """Per-role scripted providers: role -> FakeProvider."""

    def __init__(self, scripts: dict[str, list[str]], model: str = "fake-test-model"):
        self.providers = {r: FakeProvider(s, model) for r, s in scripts.items()}
        self.model = model

    def for_role(self, role: str) -> FakeProvider:
        if role not in self.providers:
            self.providers[role] = FakeProvider([], self.model)
        return self.providers[role]
