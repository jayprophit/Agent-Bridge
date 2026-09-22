"""OWNER_FULL_CONTROL broad-grant profile (P25/1).

A canonical, versioned, explicitly-activated broad grant for ordinary
reversible workstation operations. This is NOT a policy bypass:

- the policy engine stays authoritative (default-deny outside grants);
- protected actions are classified, never auto-granted;
- unknown future capabilities are never implicitly included;
- workers never inherit the grant (grants are session-bound);
- activation requires an explicit owner-authorized call that models,
  skills, workflows, routines, workers and external agents cannot forge:
  they can request it, only the trusted owner path grants it.

Ordinary reversible operations proceed without per-action approval once the
profile is active; protected operations still require owner approval
through the existing approval system + approval-mode grants.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

PROFILE_VERSION = "1"
PROFILE_ID = "OWNER_FULL_CONTROL"
GRANT_TAG_PREFIX = "owner-full-control-v1"

# Explicit ordinary capability set. Each entry is resolved against the real
# ACTION_CAPABILITY vocabulary at issue time; unknown entries fail closed
# instead of widening. Future capabilities are NOT inherited: a V2 profile
# definition is required to add them.
CAPABILITY_SET_V1 = [
    ("filesystem", "read"),
    ("filesystem", "list"),
    ("filesystem", "write"),
    ("filesystem", "edit"),
    ("filesystem", "patch"),
    ("filesystem", "mkdir"),
    ("filesystem", "move"),
    ("filesystem", "copy"),
    ("shell", "execute"),
]


@dataclass
class OwnerFullControlRecord:
    """Durable activation record (in-memory runtime state)."""
    owner_id: str
    scope_roots: list
    issued_at: int
    expires_at: Optional[int]
    provenance: str
    state: str = "ACTIVE"
    revoked_at: Optional[int] = None


# owner_id -> record. Session/device binding is expressed by issuing
# session-scoped grants per activation; the record itself is owner-scoped.
_records: dict[str, OwnerFullControlRecord] = {}


def classify_protection(service: str, action: str, flags: Optional[dict] = None) -> str:
    """Classify an action: ORDINARY, PROTECTED, or FORBIDDEN.

    - PROTECTED: destructive/permanent deletes, credential-bearing targets,
      security-policy changes. Never auto-granted, even under full control.
    - FORBIDDEN: outside the explicit V1 set (including unknown future
      capabilities). Denied, never silently allowed.
    - ORDINARY: covered reversible workstation operations.
    """
    flags = flags or {}
    capability = (service, action)
    if action in ("delete",) and flags.get("permanent"):
        return "PROTECTED"
    if flags.get("credential") or flags.get("security_policy"):
        return "PROTECTED"
    if flags.get("finance") or flags.get("firmware") or flags.get("physical"):
        return "PROTECTED"
    known = set(CAPABILITY_SET_V1)
    if capability in known:
        return "ORDINARY"
    return "FORBIDDEN"


def activate(owner_id: str, scope_roots: list, owner_authorized: bool,
             provenance: str = "", expires_in_s: Optional[int] = None,
             now: Optional[int] = None) -> OwnerFullControlRecord:
    """Explicit owner activation. owner_authorized=True is mandatory and can
    only be supplied by the trusted owner path — models, skills, workflows,
    routines, workers and external agents cannot set it for themselves."""
    if not owner_authorized:
        raise PermissionError("OWNER_FULL_CONTROL requires explicit owner authorization")
    if not owner_id or not owner_id.strip():
        raise ValueError("owner_id is required")
    if not scope_roots:
        raise ValueError("at least one scope root is required")
    now_s = now if now is not None else int(time.time())
    record = OwnerFullControlRecord(
        owner_id=owner_id.strip(),
        scope_roots=[str(Path(r).resolve()) if isinstance(r, (str, Path)) else r for r in scope_roots],
        issued_at=now_s,
        expires_at=(now_s + expires_in_s) if expires_in_s is not None else None,
        provenance=provenance or "explicit-owner-activation",
        state="ACTIVE",
    )
    _records[record.owner_id] = record
    return record


def is_active(owner_id: str, now: Optional[int] = None) -> bool:
    """True only for ACTIVE, unexpired, unrevoked records."""
    record = _records.get(owner_id or "")
    if record is None or record.state != "ACTIVE":
        return False
    if record.expires_at is not None:
        now_s = now if now is not None else int(time.time())
        if now_s >= record.expires_at:
            return False
    return True


def revoke(owner_id: str, now: Optional[int] = None) -> bool:
    """Revoke the profile AND remove its session grants. History (journal,
    evidence) is preserved by callers; revocation only stops future grants."""
    record = _records.get(owner_id or "")
    if record is None:
        return False
    record.state = "REVOKED"
    record.revoked_at = now if now is not None else int(time.time())
    remove_profile_grants(owner_id)
    return True


# Full canonical capability vocabulary (mirrors ACTION_CAPABILITY values plus
# the executor-level filesystem mutations the approval system risk-assesses).
# The profile may ONLY contain entries from this set; anything else fails
# closed at issue time, and future capabilities are never inherited.
CANONICAL_VOCABULARY = {
    ("shell", "execute"),
    ("filesystem", "read"),
    ("filesystem", "list"),
    ("filesystem", "write"),
    ("filesystem", "edit"),
    ("filesystem", "patch"),
    ("filesystem", "mkdir"),
    ("filesystem", "delete"),
    ("filesystem", "restore"),
    ("filesystem", "move"),
    ("filesystem", "copy"),
    ("shell", "install"),
    ("git", "commit"),
    ("git", "push"),
    ("owner", "browser"),
    ("owner", "net"),
    ("owner", "proc"),
    ("owner", "git"),
}


def issue_profile_grants(session_id: str, workspace_path: str, owner_id: str,
                         now: Optional[int] = None) -> int:
    """Issue the V1 ordinary set as session-scoped grants tagged for later
    revocation. Requires an ACTIVE profile; anything else raises.

    Grants use the SAME session-bound subject the executor and bridge gate
    already evaluate, so no policy-path changes are needed: the profile
    only changes WHICH grants exist, never how they are enforced.
    """
    if not is_active(owner_id, now):
        raise PermissionError("OWNER_FULL_CONTROL is not active for this owner")
    from aether_policy_bridge import Grant, PermissionId, ResourceId, Subject, get_policy_engine, workspace_subject
    for capability in CAPABILITY_SET_V1:
        if capability not in CANONICAL_VOCABULARY:
            raise ValueError(f"profile capability not in canonical vocabulary: {capability[0]}:{capability[1]}")
    engine = get_policy_engine()
    ws = Path(workspace_path).resolve()
    ws_prefix = f"workspace:{ws}"
    full_subject = workspace_subject(str(ws), session_id)
    kind, _, value = full_subject.partition(":")
    subject = Subject(kind=kind, value=value)
    now_s = now if now is not None else int(time.time())
    tag = f"{GRANT_TAG_PREFIX}:{owner_id}"
    count = 0
    for service, action in CAPABILITY_SET_V1:
        engine.add_grant(Grant(
            subject=subject,
            permission=PermissionId(service, action),
            resource=ResourceId(f"{ws_prefix}/**"),
            conditions=[],
            granted_by=tag,
            granted_at=now_s,
        ))
        count += 1
    return count


def remove_profile_grants(owner_id: str) -> int:
    """Remove every grant tagged for this owner's profile. Returns count."""
    from aether_policy_bridge import get_policy_engine
    engine = get_policy_engine()
    tag = f"{GRANT_TAG_PREFIX}:{owner_id}"
    removed = 0
    for key in list(engine.grants.keys()):
        kept = []
        for grant in engine.grants.get(key, []):
            if getattr(grant, "granted_by", "") == tag:
                removed += 1
            else:
                kept.append(grant)
        if kept:
            engine.grants[key] = kept
        else:
            engine.grants.pop(key, None)
    return removed


def summarize(owner_id: str, now: Optional[int] = None) -> dict:
    """Machine-readable profile state for operator surfaces (no secrets)."""
    record = _records.get(owner_id or "")
    if record is None:
        return {"profile": PROFILE_ID, "state": "DISABLED", "owner": owner_id}
    active = is_active(owner_id, now)
    return {
        "profile": PROFILE_ID,
        "state": "ACTIVE" if active else record.state,
        "owner": record.owner_id,
        "scope": list(record.scope_roots),
        "capability_set": f"v{PROFILE_VERSION}",
        "capabilities": [f"{s}:{a}" for s, a in CAPABILITY_SET_V1],
        "protected_policy": "ACTIVE",
        "expires_at": record.expires_at,
        "issued_at": record.issued_at,
        "provenance": record.provenance,
    }


def reset_profile_state() -> None:
    """Test isolation only."""
    _records.clear()
