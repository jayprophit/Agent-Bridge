"""Command risk classification + test profiles (v0.3, stdlib only).

Classes: READ_ONLY < SAFE_BUILD < TEST < NETWORK < INSTALL < DESTRUCTIVE,
plus UNKNOWN (never safe). Policy maps each class to auto/approve/deny.
Profiles are allowlist-based: a command runs only if its executable/prefix
is listed. Install/network patterns always escalate regardless of profile.
"""
from __future__ import annotations

import os
import shlex

READ_ONLY = "READ_ONLY"
SAFE_BUILD = "SAFE_BUILD"
TEST = "TEST"
NETWORK = "NETWORK"
INSTALL = "INSTALL"
DESTRUCTIVE = "DESTRUCTIVE"
UNKNOWN = "UNKNOWN"

CLASSES = (READ_ONLY, SAFE_BUILD, TEST, NETWORK, INSTALL, DESTRUCTIVE, UNKNOWN)

_INSTALL_HINTS = ("pip install", "pip3 install", "npm install", "npm ci",
                  "apt-get", "apt install", "choco install", "winget install",
                  "conda install", "poetry add", "cargo add", "go get")
_NETWORK_HINTS = ("curl", "wget", "invoke-webrequest", "ssh ", "scp ",
                  "ftp ", "telnet", "nc ", "--upload", "http://", "https://")
_DESTRUCTIVE_HINTS = ("rm -rf", "rm ", "del /", "del ", "rd /s", "rmdir /s",
                       "format ", "mkfs", "shutdown", "reboot",
                       "git reset --hard", "git clean -fd", "git clean -fdx")
_TEST_HINTS = ("pytest", "unittest", "npm test", "npm run test", "jest",
               "mocha", "vitest", "tox")

# Allowlisted safe test/build commands per profile (prefix match on argv).
TEST_PROFILES: dict[str, list[tuple[str, ...]]] = {
    "python": [("python", "-m", "unittest"), ("python", "-m", "pytest"),
               ("python", "-m", "tox"), ("pytest",), ("python",)],
    "node": [("npm", "test"), ("npm", "run", "lint"), ("npm", "run", "build"),
             ("npm", "run", "test"), ("node",), ("npx", "jest")],
    "generic": [("echo",), ("ls",), ("dir",), ("cat",), ("type",), ("pwd",)],
}

# Strict shell executables per profile (executor allowlist source).
SHELL_ALLOWLISTS: dict[str, frozenset] = {
    "strict": frozenset({"python", "python3", "py"}),
    "dev": frozenset({"python", "python3", "py", "dir", "ls", "echo", "type",
                      "cat", "pwd", "where", "whoami", "dotnet", "node", "npm"}),
}


def _argv(command: str) -> list[str] | None:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return None
    return parts or None


def _exe(parts: list[str]) -> str:
    base = os.path.basename(parts[0].strip().strip('"').strip("'")).lower()
    return base[:-4] if base.endswith(".exe") else base


def classify_command(command: str) -> tuple[str, str]:
    """Return (class, reason). UNKNOWN is never safe."""
    if not command or not command.strip():
        return UNKNOWN, "empty command"
    low = command.lower()
    for hint in _DESTRUCTIVE_HINTS:
        if hint in low:
            return DESTRUCTIVE, f"destructive pattern {hint!r}"
    for hint in _INSTALL_HINTS:
        if hint in low:
            return INSTALL, f"install pattern {hint!r}"
    for hint in _NETWORK_HINTS:
        if hint in low:
            return NETWORK, f"network pattern {hint!r}"
    parts = _argv(command)
    if parts is None:
        return UNKNOWN, "unparseable command"
    exe = _exe(parts)
    joined = " ".join(p.lower() for p in parts)
    for hint in _TEST_HINTS:
        if hint in joined:
            return TEST, f"test pattern {hint!r}"
    if exe in ("dir", "ls", "echo", "type", "cat", "pwd", "where", "whoami"):
        return READ_ONLY, f"read-only helper {exe!r}"
    if exe in ("python", "python3", "py", "node", "npm", "dotnet"):
        return SAFE_BUILD, f"build runner {exe!r}"
    return UNKNOWN, f"unknown executable {parts[0]!r}"


def matches_profile(command: str, profile: str) -> bool:
    """True if command argv starts with an allowlisted profile prefix."""
    prefixes = TEST_PROFILES.get(profile, TEST_PROFILES["generic"])
    parts = _argv(command)
    if not parts:
        return False
    norm = [os.path.basename(p.strip('"').strip("'")).lower() for p in parts]
    norm = [n[:-4] if n.endswith(".exe") else n for n in norm]
    for prefix in prefixes:
        if tuple(norm[:len(prefix)]) == tuple(prefix):
            return True
    return False
