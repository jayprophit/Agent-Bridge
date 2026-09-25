"""Full post-operation world-state audit (P21, REQ-p21-world-state-audit).

Generalizes detexec read-back verification (executor.do_write writes,
then independently re-reads and compares, VERIFICATION_FAILED on
mismatch) into a reusable post-operation audit:

    execute(action) -> operation result -> independently read world
    -> audit(expected, observed)

AGENT CLAIM != WORLD-STATE VERIFICATION. Tool success, exit codes, API
responses and UI completions are claims; only independent read-back
counts as evidence.

The auditor never mutates: observations arrive through an injected
read function (filesystem adapter provided). Policy is consumed as
evidence, never decided (P25 remains authority). No LLM judge, no
simulated world, no event bus, no evidence database. Clean-room proof
is explicitly out of scope (clean-room stays BLOCKED).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable


# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

VERIFIED = "VERIFIED"
FAILED = "FAILED"
INCONCLUSIVE = "INCONCLUSIVE"

CHECK_EXPECTED = "EXPECTED_EFFECT"
CHECK_UNCHANGED = "UNCHANGED_INVARIANT"
CHECK_PROHIBITED = "PROHIBITED_EFFECT"
CHECK_POLICY = "POLICY_ASSERTION"
CHECK_READBACK = "READBACK_AVAILABILITY"


class WorldAuditError(Exception):
    """Malformed audit input."""


# --------------------------------------------------------------------------
# Contracts
# --------------------------------------------------------------------------

@dataclass
class ExpectedEffect:
    """One object that must hold an expected state after the operation."""
    object_ref: str
    expected: Any = None
    expected_hash: str = ""
    comparison: str = "exact"  # exact | hash | subset


@dataclass
class UnchangedInvariant:
    """One object that must equal its pre-operation state."""
    object_ref: str
    pre_state: Any = None
    pre_hash: str = ""


@dataclass
class ProhibitedEffect:
    """Something that must NOT have happened."""
    object_ref: str
    forbidden: str = "changed"  # changed | created | deleted


@dataclass
class PolicyEvidence:
    """Consumed policy result. Decided elsewhere (P25), referenced here."""
    decision_ref: str
    allowed: bool
    principal: str = ""
    capability: str = ""


@dataclass
class Observation:
    object_ref: str
    observed: Any = None
    observed_hash: str = ""
    observed_at: str = ""
    source: str = ""
    evidence_ref: str = ""


@dataclass
class AuditCheck:
    object_ref: str
    check_type: str
    expected: Any = None
    observed: Any = None
    verdict: str = FAILED
    reason: str = ""


@dataclass
class WorldAuditReport:
    operation_id: str
    verdict: str
    checks: list[AuditCheck] = field(default_factory=list)
    scope_checked: list[str] = field(default_factory=list)
    scope_not_checked: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self, hash_values: bool = False) -> dict[str, Any]:
        def maybe(value: Any) -> Any:
            if hash_values and isinstance(value, (str, bytes)):
                raw = value.encode() if isinstance(value, str) else bytes(value)
                return "sha256:" + hashlib.sha256(raw).hexdigest()
            return value

        return {
            "operation_id": self.operation_id,
            "verdict": self.verdict,
            "checks": [
                {"object_ref": c.object_ref, "check_type": c.check_type,
                 "expected": maybe(c.expected), "observed": maybe(c.observed),
                 "verdict": c.verdict, "reason": c.reason}
                for c in self.checks
            ],
            "scope_checked": list(self.scope_checked),
            "scope_not_checked": list(self.scope_not_checked),
            "unresolved": list(self.unresolved),
            "evidence_refs": list(self.evidence_refs),
        }


Reader = Callable[[str], Observation]


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def _sha256_str(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def audit_world(
    operation_id: str,
    expected: list[ExpectedEffect] | None = None,
    unchanged: list[UnchangedInvariant] | None = None,
    prohibited: list[ProhibitedEffect] | None = None,
    policy: PolicyEvidence | None = None,
    observations: dict[str, Observation] | None = None,
    scope: list[str] | None = None,
    require_policy: bool = True,
) -> WorldAuditReport:
    """Pure audit: compare expectations against independent observations.

    observations maps object_ref -> Observation (caller reads the world
    through adapters; missing entries mean NOT OBSERVED, never unchanged).
    scope lists object refs the audit was allowed to observe; anything
    outside scope lands in scope_not_checked. Policy evidence is required
    by default (require_policy): without it the audit cannot claim full
    VERIFIED status. Pass require_policy=False only for audits with no
    policy dimension.
    """
    if not isinstance(operation_id, str) or not operation_id.strip():
        raise WorldAuditError("operation_id is required")
    expected = list(expected or [])
    unchanged = list(unchanged or [])
    prohibited = list(prohibited or [])
    observations = dict(observations or {})
    scope_list = sorted(scope) if scope is not None else None

    seen_effects: set[str] = set()
    for item in expected:
        if not item.object_ref.strip():
            raise WorldAuditError("expected effect needs an object_ref")
        if item.object_ref in seen_effects:
            raise WorldAuditError(f"duplicate expectation for {item.object_ref}")
        seen_effects.add(item.object_ref)
        if item.comparison not in ("exact", "hash", "subset"):
            raise WorldAuditError(f"unknown comparison {item.comparison}")
    for item in unchanged:
        if not item.object_ref.strip():
            raise WorldAuditError("unchanged invariant needs an object_ref")
    for item in prohibited:
        if not item.object_ref.strip():
            raise WorldAuditError("prohibited effect needs an object_ref")
        if item.forbidden not in ("changed", "created", "deleted"):
            raise WorldAuditError(f"unknown prohibited effect {item.forbidden}")

    checks: list[AuditCheck] = []
    unresolved: list[str] = []
    evidence_refs: list[str] = []

    def observe(ref: str) -> Observation | None:
        return observations.get(ref)

    for item in sorted(expected, key=lambda e: e.object_ref):
        obs = observe(item.object_ref)
        if obs is None:
            checks.append(AuditCheck(item.object_ref, CHECK_READBACK, item.expected, None,
                                     INCONCLUSIVE, "no independent read-back for expected object"))
            unresolved.append(item.object_ref)
            continue
        if obs.evidence_ref:
            evidence_refs.append(obs.evidence_ref)
        if item.comparison == "hash":
            ok = bool(item.expected_hash) and obs.observed_hash == item.expected_hash and obs.observed_hash != ""
            checks.append(AuditCheck(
                item.object_ref, CHECK_EXPECTED, f"sha256:{item.expected_hash}",
                f"sha256:{obs.observed_hash}" if obs.observed_hash else obs.observed,
                VERIFIED if ok else FAILED,
                "hash matches" if ok else "hash mismatch or missing"))
        elif item.comparison == "subset":
            ok = (isinstance(item.expected, dict) and isinstance(obs.observed, dict)
                  and all(obs.observed.get(k) == v for k, v in item.expected.items()))
            checks.append(AuditCheck(
                item.object_ref, CHECK_EXPECTED, item.expected, obs.observed,
                VERIFIED if ok else FAILED,
                "expected subset holds" if ok else "expected subset not satisfied"))
        else:
            # exact: CORRECT VALUE ON WRONG OBJECT is impossible here by
            # construction (observation keyed by ref); mismatch fails.
            ok = obs.observed == item.expected
            checks.append(AuditCheck(
                item.object_ref, CHECK_EXPECTED, item.expected, obs.observed,
                VERIFIED if ok else FAILED,
                "value matches" if ok else "value mismatch"))

    for item in sorted(unchanged, key=lambda e: e.object_ref):
        obs = observe(item.object_ref)
        if obs is None:
            checks.append(AuditCheck(item.object_ref, CHECK_READBACK, "(pre-state)", None,
                                     INCONCLUSIVE, "protected object not observed; NOT OBSERVED != UNCHANGED"))
            unresolved.append(item.object_ref)
            continue
        if obs.evidence_ref:
            evidence_refs.append(obs.evidence_ref)
        if item.pre_hash:
            ok = obs.observed_hash == item.pre_hash and obs.observed_hash != ""
            checks.append(AuditCheck(
                item.object_ref, CHECK_UNCHANGED, f"sha256:{item.pre_hash}",
                f"sha256:{obs.observed_hash}" if obs.observed_hash else obs.observed,
                VERIFIED if ok else FAILED,
                "unchanged" if ok else "UNEXPECTED_CHANGE"))
        else:
            ok = obs.observed == item.pre_state
            checks.append(AuditCheck(
                item.object_ref, CHECK_UNCHANGED, item.pre_state, obs.observed,
                VERIFIED if ok else FAILED,
                "unchanged" if ok else "UNEXPECTED_CHANGE"))

    for item in sorted(prohibited, key=lambda e: e.object_ref):
        obs = observe(item.object_ref)
        if obs is None:
            checks.append(AuditCheck(item.object_ref, CHECK_READBACK, f"not {item.forbidden}", None,
                                     INCONCLUSIVE, "prohibited scope not observed"))
            unresolved.append(item.object_ref)
            continue
        if item.forbidden == "created":
            # Must not exist: absent observation satisfies, presence violates.
            violated = obs.observed is not None
        elif item.forbidden == "deleted":
            # Must still exist: presence satisfies, absence violates.
            violated = obs.observed is None
        elif item.forbidden == "changed":
            # Change needs pre-state to judge; without it stay honest.
            checks.append(AuditCheck(item.object_ref, CHECK_PROHIBITED, "unchanged", obs.observed,
                                     INCONCLUSIVE, "change needs pre-state; use an unchanged invariant"))
            unresolved.append(item.object_ref)
            continue
        else:  # unreachable: validated upfront
            raise WorldAuditError(f"unknown prohibited effect {item.forbidden}")
        checks.append(AuditCheck(
            item.object_ref, CHECK_PROHIBITED, f"not {item.forbidden}", obs.observed,
            FAILED if violated else VERIFIED,
            "PROHIBITED_EFFECT observed" if violated else "prohibited effect absent"))

    if policy is not None:
        if not policy.decision_ref.strip():
            raise WorldAuditError("policy evidence needs a decision_ref")
        if policy.allowed:
            checks.append(AuditCheck("(policy)", CHECK_POLICY, "allowed", "allowed",
                                     VERIFIED, f"decision {policy.decision_ref}"))
            evidence_refs.append(f"policy:{policy.decision_ref}")
        else:
            checks.append(AuditCheck("(policy)", CHECK_POLICY, "allowed", "denied",
                                     FAILED, f"POLICY_VIOLATION in {policy.decision_ref}"))
    else:
        unresolved.append("(policy)")

    verdict = VERIFIED
    for check in checks:
        if check.verdict == FAILED:
            verdict = FAILED
            break
        if check.verdict == INCONCLUSIVE:
            verdict = INCONCLUSIVE
    if verdict == VERIFIED and require_policy and policy is None:
        # Policy dimension required but absent: cannot claim full VERIFIED.
        verdict = INCONCLUSIVE

    checked = sorted({c.object_ref for c in checks if c.object_ref != "(policy)"})
    if scope_list is not None:
        not_checked = sorted(set(scope_list) - set(checked) - set(observations))
    else:
        not_checked = []
    return WorldAuditReport(
        operation_id=operation_id.strip(),
        verdict=verdict,
        checks=checks,
        scope_checked=checked,
        scope_not_checked=not_checked,
        unresolved=sorted(set(unresolved)),
        evidence_refs=sorted(set(evidence_refs)),
    )


# --------------------------------------------------------------------------
# Filesystem reader (independent read-back adapter)
# --------------------------------------------------------------------------

def read_filesystem(path: str, source: str = "filesystem") -> Observation:
    """Read a file independently (content + hash). No mutation."""
    from pathlib import Path
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        return Observation(object_ref=path, observed=None, observed_hash="",
                           source=source, evidence_ref="",
                           )
    try:
        text: Any = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    return Observation(
        object_ref=path,
        observed=text if text is not None else f"<{len(data)} binary bytes>",
        observed_hash=hashlib.sha256(data).hexdigest(),
        source=source,
    )
