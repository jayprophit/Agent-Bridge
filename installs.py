"""Software installation support (OWNER_FULL_ACCESS only).

Capability is always probed first; nothing is invented. Actual results
are recorded. Keep test usage to probes + non-mutating operations
(e.g. pip download) unless the owner explicitly approves an install.
"""
from __future__ import annotations

import shutil
import subprocess
from typing import Any

from proc import launch


def probe() -> dict[str, Any]:
    """Report which package managers actually exist. No changes."""
    out: dict[str, Any] = {}
    for name in ("pip", "npm", "winget", "choco"):
        exe = shutil.which(name if name != "pip" else "pip")
        if name == "pip" and not exe:
            exe = shutil.which("pip3")
        out[name] = {"present": bool(exe), "path": exe or ""}
    out["note"] = "probe only; no installation performed"
    return {"ok": True, "managers": out}


def run_install(command: str, cwd: str | None = None,
                timeout_s: int = 600) -> dict[str, Any]:
    """Run a real install command the owner authorized. Records evidence."""
    import os as _os
    first = command.strip().split()[0].lower() if command.strip() else ""
    base = _os.path.basename(first).lower()
    if base.endswith(".exe"):
        base = base[:-4]
    known = ("pip", "pip3", "npm", "winget", "choco", "poetry",
             "conda", "cargo", "dotnet", "uv")
    if base not in known:
        return {"ok": False, "error": f"refused: not a package-manager command: {command[:80]!r}"}
    res = launch(command, cwd=cwd, timeout_s=timeout_s)
    return {"ok": res.get("ok", False), "command": command,
            "exit_code": res.get("exit_code"), "stdout": res.get("stdout", ""),
            "stderr": res.get("stderr", ""), "duration_s": res.get("duration_s", 0)}


def pip_download(package: str, dest: str, timeout_s: int = 300) -> dict[str, Any]:
    """Non-mutating capability proof: download without installing."""
    if not package or any(c in package for c in " ;&|$()`"):
        return {"ok": False, "error": "refused: bad package name"}
    pip = shutil.which("pip") or shutil.which("pip3") or "pip"
    return run_install(f"{pip} download --no-deps --dest {dest} {package}",
                       timeout_s=timeout_s)
