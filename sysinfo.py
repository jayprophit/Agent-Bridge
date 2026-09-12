"""Machine capability inventory for OWNER mode (no secrets)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from owner import admin_state, machine_roots


def _tool_version(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           shell=False)
        out = (p.stdout or p.stderr or "").strip().splitlines()
        return out[0][:120] if out else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def inventory() -> dict[str, Any]:
    try:
        import ctypes as _ct

        class _MS(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong),
                        ("memory_load", ctypes.c_ulong),
                        ("total_phys", ctypes.c_ulonglong),
                        ("avail_phys", ctypes.c_ulonglong)]
        ms = _MS()
        ms.length = ctypes.sizeof(_MS)
        ram_mb = None
        if os.name == "nt" and ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
            ram_mb = int(ms.total_phys // (1024 * 1024))
    except Exception:
        ram_mb = None
    tools: dict[str, Any] = {}
    for name, probe in (("python", ["python", "--version"]),
                        ("node", ["node", "--version"]),
                        ("npm", ["npm", "--version"]),
                        ("git", ["git", "--version"]),
                        ("winget", ["winget", "--version"]),
                        ("choco", ["choco", "--version"]),
                        ("ollama", ["ollama", "--version"]),
                        ("code", ["code", "--version"])):
        path = shutil.which(name.split()[0])
        tools[name] = {"present": bool(path), "path": path or "",
                       "version": _tool_version(probe) if path else ""}
    browsers = []
    for label, cand in (("edge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                        ("edge64", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
                        ("chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe")):
        if Path(cand).exists():
            browsers.append({"browser": label, "path": cand})
    try:
        import ssl as _ssl  # noqa: F401
        tls = True
    except ImportError:
        tls = False
    return {
        "windows": platform.platform(),
        "admin": admin_state(),
        "cpu": platform.machine() or os.cpu_count(),
        "ram_mb": ram_mb,
        "drives": [str(d) for d in machine_roots() if d.drive],
        "tools": tools,
        "browsers": browsers,
        "tls": tls,
        "note": "no secrets included",
    }
