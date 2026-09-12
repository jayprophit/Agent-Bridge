"""Validated Git operations for OWNER_FULL_ACCESS (stdlib only).

Every mutation records repo/branch/before-HEAD/after-HEAD/command/result.
Success is never fabricated: exit codes and follow-up rev-parse decide.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

READ_OPS = ("status", "diff", "branch", "log")
WRITE_OPS = ("checkout", "add", "commit", "pull", "fetch", "merge",
             "rebase", "push")


class GitError(Exception):
    pass


def _run(repo: Path, args: list[str], timeout_s: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=str(repo), capture_output=True,
                          text=True, timeout=timeout_s, shell=False)


def _head(repo: Path) -> str:
    try:
        p = _run(repo, ["rev-parse", "HEAD"], 15)
        return p.stdout.strip().splitlines()[0] if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _branch(repo: Path) -> str:
    try:
        p = _run(repo, ["rev-parse", "--abbrev-ref", "HEAD"], 15)
        return p.stdout.strip().splitlines()[0] if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def operate(repo: str | Path, op: str, args: list[str] | None = None,
            message: str = "", timeout_s: int = 120) -> dict[str, Any]:
    repo = Path(repo).expanduser().resolve()
    if not (repo / ".git").exists():
        return {"ok": False, "error": f"not a git repository: {repo}"}
    op = op.strip().lower()
    if op not in READ_OPS + WRITE_OPS:
        return {"ok": False, "error": f"unsupported git op: {op!r}"}
    cmd: list[str] = []
    if op == "status":
        cmd = ["status", "--porcelain", "-b"]
    elif op == "diff":
        cmd = ["diff", "--stat"] + (args or [])
    elif op == "branch":
        cmd = ["branch", "--show-current"]
    elif op == "log":
        cmd = ["log", "--oneline", "-5"]
    elif op == "checkout":
        cmd = ["checkout"] + (args or [])
    elif op == "add":
        cmd = ["add"] + (args or ["."])
    elif op == "commit":
        if not message:
            return {"ok": False, "error": "commit needs a message"}
        cmd = ["commit", "-m", message]
    else:  # pull fetch merge rebase push
        cmd = [op] + (args or [])
    before, branch = _head(repo), _branch(repo)
    try:
        p = _run(repo, cmd, timeout_s)
    except FileNotFoundError:
        return {"ok": False, "error": "git executable not found"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "TIMEOUT: git op timed out"}
    after = _head(repo)
    branch = _branch(repo) or branch
    return {"ok": p.returncode == 0, "repo": str(repo), "branch": branch,
            "before_head": before, "after_head": after,
            "command": "git " + " ".join(cmd),
            "stdout": (p.stdout or "")[:4000],
            "stderr": (p.stderr or "")[:2000]}
