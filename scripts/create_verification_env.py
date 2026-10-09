"""Create the declared Aetherius verification environment (owner decision: Option 2).

WHY THIS EXISTS

The dependency-lock test asserts that every pin in requirements-lock.txt
matches the interpreter that is running pytest. Running it from a tooling venv
guarantees a mismatch: kdbx313 carries pytest 9.1.1, which pulls iniconfig
2.3.1, while the lockfile pins 2.3.0.

The owner explicitly chose NOT to weaken the gate and NOT to skip on auxiliary
environments. So the correct fix is to give the gate the environment it
describes: a dedicated venv whose installed closure IS the lockfile.

This script does not install packages by name — it installs FROM THE LOCKFILE,
so the venv's contents are the lockfile's contents by construction rather than
by a hand-maintained list that can drift.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import venv
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOCKFILE = REPO / "requirements-lock.txt"

# §2: kept deliberately separate from the KeePass tooling venv. kdbx313 is a
# specialist environment for the KeePass bridge and is NOT the canonical
# project verification environment.
VENV_ROOT = Path.home() / ".aetherius" / "venvs"
ENV_NAME = "agent-bridge-verify"
ENV_ID = "aetherius-agent-bridge-verify-1"
MANIFEST = REPO / "verification" / "verification_environment.json"


def venv_python(env_path: Path) -> Path:
    """Resolve the venv's interpreter without relying on PATH (§5)."""
    candidates = [
        env_path / "Scripts" / "python.exe",   # Windows
        env_path / "bin" / "python",           # POSIX
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"no interpreter found in {env_path}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("  $ " + " ".join(str(c) for c in cmd[:6]) +
          (" ..." if len(cmd) > 6 else ""), flush=True)
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def main() -> int:
    if not LOCKFILE.exists():
        print(f"lockfile not found: {LOCKFILE}")
        return 1

    env_path = VENV_ROOT / ENV_NAME
    print(f"verification environment: {env_path}")

    # §2 reconcile: reuse an existing venv rather than creating a duplicate.
    if env_path.exists():
        print("  exists — reusing (refreshing pinned closure)")
    else:
        print("  creating")
        builder = venv.EnvBuilder(with_pip=True, clear=False)
        builder.create(str(env_path))

    py = venv_python(env_path)
    print(f"  interpreter: {py}")
    version = run([str(py), "--version"])
    print(f"  {version.stdout.strip() or version.stderr.strip()}")

    # §3 install the ENTIRE pinned closure from the lockfile, not a subset.
    print("\ninstalling exact pinned closure from requirements-lock.txt")
    install = run([str(py), "-m", "pip", "install", "--disable-pip-version-check",
                   "--no-input", "-r", str(LOCKFILE)])
    if install.returncode != 0:
        print(install.stdout[-3000:])
        print(install.stderr[-3000:])
        print("INSTALL FAILED")
        return 1
    print("  install complete")

    # Verify the closure actually matches — do not trust the install alone.
    print("\nverifying installed closure against lockfile")
    pins: dict[str, str] = {}
    for line in LOCKFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, ver = line.partition("==")
        pins[name.strip().lower()] = ver.strip()

    check = run([str(py), "-c",
                 "import importlib.metadata as m, json, sys;"
                 "print(json.dumps({d.metadata['Name'].lower(): d.version "
                 "for d in m.distributions()}))"])
    installed = json.loads(check.stdout) if check.returncode == 0 else {}

    mismatched = {name: {"locked": ver, "installed": installed.get(name)}
                  for name, ver in pins.items() if installed.get(name) != ver}
    missing = sorted(name for name in pins if name not in installed)

    print(f"  pins checked : {len(pins)}")
    print(f"  missing      : {missing or 'none'}")
    print(f"  mismatched   : {mismatched or 'none'}")

    # §4 manifest — record everything needed to reproduce this environment.
    manifest = OrderedDict([
        ("environment_id", ENV_ID),
        ("path", str(env_path)),
        ("python_version", (version.stdout.strip() or version.stderr.strip())
         .replace("Python ", "")),
        ("lockfile_path", "requirements-lock.txt"),
        ("lockfile_sha256", sha256(LOCKFILE)),
        ("pin_count", len(pins)),
        ("pins", pins),
        ("installed_count", len(installed)),
        ("missing", missing),
        ("mismatched", mismatched),
        ("created_at", datetime.now(timezone.utc).isoformat()),
        # §5 the canonical command — explicit interpreter, no PATH reliance.
        ("verification_command",
         f"{py} -m pytest tests/ -p no:cacheprovider --tb=line -q -rf"),
        ("venv_committed", False),
        ("commit_policy", "Commit scripts, manifests and lock metadata only. "
                          "Never the venv itself."),
    ])
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    print(f"\nmanifest written: {MANIFEST.relative_to(REPO)}")

    if missing or mismatched:
        print("\nCLOSURE MISMATCH — the environment does not match the lockfile.")
        return 2
    print("\nclosure matches the lockfile exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
