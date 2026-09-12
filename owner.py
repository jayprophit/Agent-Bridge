"""OWNER_FULL_ACCESS machinery (v0.6).

Explicit owner authorization for autonomous computer operation. Never
engaged by accident: requires BOTH profile selection AND an explicit
owner-authorized flag/token. Safe profiles are untouched.

Windows UAC remains authoritative: this module only REPORTS elevation
(ADMIN_ACTIVE / ADMIN_NOT_ACTIVE / ADMIN_UNKNOWN) and refuses to fake it.
"""
from __future__ import annotations

import ctypes
import datetime as _dt
import os
import threading
from pathlib import Path
from typing import Any

ADMIN_ACTIVE = "ADMIN_ACTIVE"
ADMIN_NOT_ACTIVE = "ADMIN_NOT_ACTIVE"
ADMIN_UNKNOWN = "ADMIN_UNKNOWN"

# process-wide emergency stop (no model cooperation required)
_estop = {"flag": False, "reason": "", "at": ""}


def emergency_stop(reason: str = "operator stop") -> dict[str, Any]:
    _estop.update(flag=True, reason=reason,
                  at=_dt.datetime.now().isoformat(timespec="seconds"))
    try:
        from bridge import request_cancel
        request_cancel()
    except Exception:
        pass
    try:
        import browser_cdp
        browser_cdp.stop_all("emergency stop")
    except Exception:
        pass
    return {"ok": True, "stopped": True, "reason": reason}


def emergency_clear() -> None:
    _estop.update(flag=False, reason="", at="")


def emergency_active() -> tuple[bool, str]:
    return bool(_estop["flag"]), str(_estop["reason"])


def admin_state() -> str:
    """Detect Windows elevation. Never claims more than it can prove."""
    if os.name != "nt":
        return ADMIN_UNKNOWN
    try:
        elevated = bool(ctypes.windll.shell32.IsUserAnAdmin())
        return ADMIN_ACTIVE if elevated else ADMIN_NOT_ACTIVE
    except Exception:
        return ADMIN_UNKNOWN


def _protected_prefixes() -> list[Path]:
    roots: list[Path] = []
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    for cand in (sysroot,
                 os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)",
                                r"C:\Program Files (x86)")):
        try:
            p = Path(cand).resolve()
            if p.exists():
                roots.append(p)
        except OSError:
            pass
    return roots


def requires_admin(target: Path) -> bool:
    """True when a mutation target genuinely needs Administrator (UAC).
    Honest heuristic: under Windows system/program locations."""
    if os.name != "nt":
        return False
    try:
        t = str(target.resolve()).lower()
    except OSError:
        return False
    return any(t == str(r).lower() or t.startswith(str(r).lower() + os.sep)
               for r in _protected_prefixes())


def check_admin(target: Path) -> dict[str, Any] | None:
    """Return an ADMIN_REQUIRED denial dict, or None when allowed."""
    if requires_admin(target) and admin_state() != ADMIN_ACTIVE:
        return {"ok": False,
                "error": "ADMIN_REQUIRED: target needs Administrator and "
                         "runtime is not elevated (UAC authoritative)"}
    return None


def machine_roots() -> list[Path]:
    """Accessible local filesystem scope: existing drive roots + user home."""
    roots: list[Path] = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            p = Path(f"{letter}:\\")
            try:
                if p.exists() and p.is_dir():
                    roots.append(p.resolve())
            except OSError:
                pass
    else:
        roots.append(Path("/"))
    try:
        home = Path.home().resolve()
        if home not in roots:
            roots.append(home)
    except Exception:
        pass
    return roots


def resolve_owner_path(user_path: str, base: Path | None = None) -> Path:
    """Canonicalize owner-mode paths. Validation stays ON: absolute or
    workspace-style paths on accessible drives; traversal that escapes to
    UNC paths outside granted access is refused. Audit files stay protected
    unless internal code passes allow_internal=True."""
    from executor import SandboxViolation
    if not isinstance(user_path, str) or not user_path.strip():
        raise SandboxViolation("blocked: empty path")
    if "\x00" in user_path:
        raise SandboxViolation("blocked: null byte in path")
    s = user_path.strip()
    p = Path(s)
    anchor = Path(base).expanduser().resolve() if base is not None else Path.cwd()
    try:
        cand = p.resolve() if p.is_absolute() else (anchor / p).resolve()
    except OSError as e:
        raise SandboxViolation(f"blocked: unresolvable path: {e}")
    # audit/internal files protected from model tampering
    parts = [part.lower() for part in cand.parts]
    if ".bridge" in parts:
        raise SandboxViolation("INTERNAL_PROTECTED: bridge audit files")
    if cand.drive:
        ok = any(str(cand).lower().startswith(str(r).lower())
                 for r in machine_roots() if r.drive)
        if not ok:
            # allow any local fixed drive root explicitly present
            raise SandboxViolation(f"blocked: drive not in owner scope: {s!r}")
    return cand


class OwnerActivation:
    """Explicit enablement record. Both conditions required."""

    def __init__(self):
        self.active = False
        self.session_id = ""
        self.start_time = ""
        self.profile = ""
        self.admin = ADMIN_UNKNOWN
        self.network = ""
        self.lock = threading.Lock()

    def enable(self, profile: str, session_id: str, network: str,
               owner_authorized: bool) -> dict[str, Any]:
        if profile != "OWNER_FULL_ACCESS" or not owner_authorized:
            raise PermissionError(
                "OWNER_FULL_ACCESS needs profile selection AND explicit "
                "owner authorization (--owner-authorized / owner_authorized)")
        with self.lock:
            self.active = True
            self.session_id = session_id
            self.start_time = _dt.datetime.now().isoformat(timespec="seconds")
            self.profile = profile
            self.admin = admin_state()
            self.network = network
            return self.record()

    def record(self) -> dict[str, Any]:
        return {"owner_authorization_active": self.active,
                "session_id": self.session_id, "start_time": self.start_time,
                "profile": self.profile, "administrator": self.admin,
                "network": self.network}

    def disable(self) -> None:
        with self.lock:
            self.active = False


OWNER = OwnerActivation()
