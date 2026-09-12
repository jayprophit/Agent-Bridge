"""Approval levels + policy engine (v0.3, extends v0.2).

Levels: AUTO_SAFE < ASK_RISKY < ASK_ALL_WRITES < READ_ONLY.
Command classes (commands.py) map to auto/approve/deny:
  READ_ONLY      -> auto in every level except explicit deny contexts
  SAFE_BUILD     -> auto in AUTO_SAFE/ASK_RISKY, ask in ASK_ALL_WRITES
  TEST           -> auto if matches test profile, else ask
  NETWORK/INSTALL/DESTRUCTIVE/UNKNOWN -> ask in AUTO_SAFE/ASK_RISKY
      (UNKNOWN never auto), deny when non-interactive; permanent delete
      always needs explicit elevated approval.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from commands import (DESTRUCTIVE, INSTALL, NETWORK, READ_ONLY, SAFE_BUILD,
                      TEST, UNKNOWN, classify_command, matches_profile)
from protocol import MUTATING_ACTIONS

LEVELS = ("AUTO_SAFE", "ASK_RISKY", "ASK_ALL_WRITES", "READ_ONLY",
          "OWNER_AUTO_APPROVE")
OWNER_DECISION = "OWNER_AUTO_APPROVED"
DECIDE_APPROVE_ONCE = "approve-once"
DECIDE_APPROVE_SESSION = "approve-session"
DECIDE_DENY = "deny"

_ElevatedNote = "permanent deletion needs explicit elevated approval"


def classify_risk(action: dict[str, Any], large_write_bytes: int = 102_400,
                  test_profile: str = "python") -> tuple[str, str]:
    from protocol import OWNER_ONLY_ACTIONS
    act = action.get("action", "")
    if act not in MUTATING_ACTIONS:
        return "SAFE", "read-only inspection"
    if act in OWNER_ONLY_ACTIONS:
        return "RISKY", f"owner-only action {act!r} (needs OWNER profile)"
    if act == "delete":
        if action.get("permanent"):
            return "RISKY", _ElevatedNote
        return "RISKY", "delete is destructive (recycled by default, still gated)"
    if act == "write" and len(action.get("content", "")) > large_write_bytes:
        return "RISKY", f"large overwrite (>{large_write_bytes} bytes)"
    if act in ("shell", "test"):
        cls, why = classify_command(action.get("command", ""))
        if cls in (DESTRUCTIVE, INSTALL, NETWORK, UNKNOWN):
            return "RISKY", f"command class {cls}: {why}"
        if act == "test" and not matches_profile(action.get("command", ""), test_profile):
            return "RISKY", f"test command outside '{test_profile}' profile"
        return "SAFE", f"command class {cls}: {why}"
    if act == "restore":
        return "SAFE", "restore from bridge recycle (reversible)"
    return "SAFE", f"{act} inside workspace (still sandbox-checked)"


class ApprovalInterface(ABC):
    @abstractmethod
    def request(self, action: dict[str, Any], context: dict[str, Any]) -> str:
        """Return approve-once | approve-session | deny. Must not fake input."""
        ...


class ConsoleApproval(ApprovalInterface):
    """Real CLI provider: [Y] once / [S] session / [N] deny / [V] details."""

    def __init__(self, detail_fn: Callable[[dict], str] | None = None):
        self.detail_fn = detail_fn

    def request(self, action: dict[str, Any], context: dict[str, Any]) -> str:
        import json as _j
        print("—" * 60)
        print("APPROVAL REQUIRED")
        print(f"  action : {_j.dumps(action)[:600]}")
        print(f"  reason : {context.get('reason', '')}")
        print(f"  target : {context.get('target', '')}")
        print(f"  risk   : {context.get('risk', '')}")
        if action.get("command"):
            print(f"  command: {action['command'][:400]}")
        if context.get("diff_preview"):
            print("  diff preview:")
            print("  " + context["diff_preview"][:1500].replace("\n", "\n  "))
        while True:
            try:
                c = input("[Y] approve once / [S] session / [N] deny / [V] details: "
                          ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return DECIDE_DENY
            if c in ("y", "yes"):
                return DECIDE_APPROVE_ONCE
            if c in ("s", "session"):
                return DECIDE_APPROVE_SESSION
            if c in ("n", "no", ""):
                return DECIDE_DENY
            if c in ("v", "details"):
                print(_j.dumps(action, indent=2)[:3000])
                if self.detail_fn:
                    print(self.detail_fn(action)[:3000])
                continue
            print("please answer Y, S, N or V.")


class PreApprovedApproval(ApprovalInterface):
    """Deterministic approvals for tests/E2E (injectable test provider)."""

    def __init__(self, approved: list[str] | None = None, default: str = DECIDE_DENY):
        self.approved = set(approved or [])
        self.default = default
        self.requests: list[dict[str, Any]] = []

    @staticmethod
    def fingerprint(action: dict[str, Any]) -> str:
        import json as _j
        return _j.dumps(action, sort_keys=True)

    def request(self, action: dict[str, Any], context: dict[str, Any]) -> str:
        self.requests.append({"action": dict(action), "context": dict(context)})
        if self.fingerprint(action) in self.approved:
            return DECIDE_APPROVE_ONCE
        return self.default


class ApprovalManager:
    def __init__(self, level: str = "AUTO_SAFE",
                 interface: ApprovalInterface | None = None,
                 non_interactive: bool = True,
                 large_write_bytes: int = 102_400,
                 test_profile: str = "python",
                 on_event: Callable[[str, dict], None] | None = None):
        if level not in LEVELS:
            raise ValueError(f"approval level must be one of {LEVELS}")
        self.level = level
        self.interface = interface or PreApprovedApproval()
        self.non_interactive = non_interactive
        self.large_write_bytes = large_write_bytes
        self.test_profile = test_profile
        self.on_event = on_event
        self.session_approved: set[str] = set()

    def _emit(self, name: str, payload: dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(name, payload)
            except Exception:
                pass

    def decide(self, action: dict[str, Any],
               diff_preview: str = "",
               force_ask: bool = False) -> dict[str, Any]:
        import json as _j
        fp = _j.dumps(action, sort_keys=True)
        risk, reason = classify_risk(action, self.large_write_bytes, self.test_profile)
        act = action.get("action", "")
        targets = [v for k, v in action.items()
                   if k in ("path", "src", "dest") and isinstance(v, str)]
        context = {"reason": f"{self.level}: {reason}",
                   "target": ", ".join(targets),
                   "risk": risk,
                   "command": action.get("command", ""),
                   "diff_preview": diff_preview}
        if self.level == "READ_ONLY":
            if act in MUTATING_ACTIONS:
                self._emit("approval.denied", {"action": action, "context": context})
                return {"approved": False, "level": self.level, "risk": risk,
                        "reason": "READ_ONLY: all mutations denied",
                        "decision": DECIDE_DENY}
            return {"approved": True, "level": self.level, "risk": risk,
                    "reason": "read-only allowed", "decision": DECIDE_APPROVE_ONCE}
        from protocol import OWNER_ONLY_ACTIONS
        if act in OWNER_ONLY_ACTIONS and self.level != "OWNER_AUTO_APPROVE":
            self._emit("approval.denied", {"action": action, "context": context})
            return {"approved": False, "level": self.level, "risk": risk,
                    "reason": f"owner-only action {act!r} refused outside OWNER profile",
                    "decision": DECIDE_DENY}
        if self.level == "OWNER_AUTO_APPROVE":
            # explicit owner authorization: resolve immediately, no human
            # interaction — but always recorded for auditability.
            self._emit("approval.approved",
                       {"action": action, "context": context,
                        "decision": OWNER_DECISION})
            return {"approved": True, "level": self.level, "risk": risk,
                    "reason": f"OWNER_AUTO_APPROVED ({reason})",
                    "decision": OWNER_DECISION}
        needs_ask = (
            force_ask or
            (self.level == "ASK_ALL_WRITES" and act in MUTATING_ACTIONS) or
            (self.level in ("AUTO_SAFE", "ASK_RISKY") and risk == "RISKY")
        )
        if not needs_ask:
            return {"approved": True, "level": self.level, "risk": risk,
                    "reason": f"auto-approved ({reason})", "decision": DECIDE_APPROVE_ONCE}
        if fp in self.session_approved:
            return {"approved": True, "level": self.level, "risk": risk,
                    "reason": "session-approved", "decision": DECIDE_APPROVE_SESSION}
        self._emit("approval.requested", {"action": action, "context": context})
        if self.non_interactive:
            verdict = {"approved": False, "level": self.level, "risk": risk,
                       "reason": f"approval required ({reason}) but non-interactive: denied",
                       "decision": DECIDE_DENY}
            self._emit("approval.denied", {"action": action, "context": context})
            return verdict
        d = self.interface.request(action, context)
        if d == DECIDE_APPROVE_SESSION:
            self.session_approved.add(fp)
        verdict = {"approved": d in (DECIDE_APPROVE_ONCE, DECIDE_APPROVE_SESSION),
                   "level": self.level, "risk": risk,
                   "reason": f"user decision: {d} ({reason})", "decision": d}
        self._emit("approval.approved" if verdict["approved"] else "approval.denied",
                   {"action": action, "context": context, "decision": d})
        return verdict
