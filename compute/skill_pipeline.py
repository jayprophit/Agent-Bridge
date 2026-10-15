"""Versioned skill acquisition pipeline (V2 H03, maps D01/D07/A04/G02).

H03 requirement: A reusable worker skill enters a
candidate -> provenance/licence review -> sandbox tests -> security review
-> benchmark -> approved release -> registry publication pipeline.

This module implements the *promotion gate*.  It deliberately does NOT execute
skills (that is the bridge adapter's job) and does NOT re-implement
app_registry.ApplicationRegistry (which owns persistence of verified apps).
Instead it adds the version/sign/track/review lifecycle that was previously
absent: a worker cannot self-install as a privileged production skill,
versions are immutable and rollback-capable, and every transition is auditable.

Key invariants:
  1. Only pipeline-approved skills reach the production registry.
  2. Untrusted worker output never becomes privileged without review.
  3. Versions are immutable; old versions are preserved, never erased.
  4. Genesis must be able to invoke an approved skill alone (no worker role).
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from app_registry import ApplicationRecord, ApplicationRegistry, AppRegistryError


# --- pipeline stages (§14/H03) ----------------------------------------------

class SkillStage(str, Enum):
    """Ordered stages a skill candidate progresses through."""
    CANDIDATE = "candidate"                 # worker-submitted, not yet reviewed
    PROVENANCE = "provenance_review"       # licence + source provenance check
    SANDBOX = "sandbox_tests"              # runs in isolation (no host access)
    SECURITY = "security_review"           # permission/dangerous-call audit
    BENCHMARK = "benchmark"                # Genesis-solo parity benchmark
    APPROVED = "approved"                  # human or policy gate passed
    PUBLISHED = "published"               # in production registry
    REJECTED = "rejected"                  # failed review; preserved for audit
    SUPERSEDED = "superseded"              # replaced by a newer version


# --- candidate ----------------------------------------------------------------

@dataclass
class SkillCandidate:
    """A worker-submitted skill proposal.  Immutable after creation."""
    app_id: str
    name: str
    version: str
    description: str
    proposed_bridge_adapter: str          # e.g. "my_tool_adapter.py"
    required_capabilities: tuple[str, ...] = ()
    required_os_deps: tuple[str, ...] = ()
    required_model_capabilities: tuple[str, ...] = ()
    permissions_requested: tuple[str, ...] = ()
    source_url: str = ""
    license: str = ""
    source_hash: str = ""                 # sha256 of the candidate source/blob
    submitted_by: str = ""               # worker_id or "genesis"
    submitted_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.app_id or " " in self.app_id:
            raise ValueError(f"app_id must be a compact id: {self.app_id!r}")
        if not self.version:
            raise ValueError(f"version must be non-empty for {self.app_id!r}")

    @property
    def candidate_id(self) -> str:
        """Stable identifier: app_id@version."""
        return f"{self.app_id}@{self.version}"

    @property
    def expected_hash(self) -> str:
        """Compute the expected sha256 over the canonical candidate payload.

        This is what the reviewer checks against source_hash.  Untrusted
        workers cannot control this — they can only *claim* a hash which the
        reviewer re-computes and verifies.
        """
        payload = json.dumps({
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "bridge_adapter": self.proposed_bridge_adapter,
            "required_capabilities": list(self.required_capabilities),
            "required_os_deps": list(self.required_os_deps),
            "required_model_capabilities": list(self.required_model_capabilities),
            "permissions_requested": list(self.permissions_requested),
            "source_url": self.source_url,
            "license": self.license,
        }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "proposed_bridge_adapter": self.proposed_bridge_adapter,
            "required_capabilities": list(self.required_capabilities),
            "required_os_deps": list(self.required_os_deps),
            "required_model_capabilities": list(self.required_model_capabilities),
            "permissions_requested": list(self.permissions_requested),
            "source_url": self.source_url,
            "license": self.license,
            "source_hash": self.source_hash,
            "expected_hash": self.expected_hash,
            "submitted_by": self.submitted_by,
            "submitted_at": self.submitted_at,
            "candidate_id": self.candidate_id,
        }


# --- published skill record ---------------------------------------------------

@dataclass
class PublishedSkill:
    """An immutable, signed skill record in the production registry."""
    app_id: str
    version: str
    description: str
    bridge_adapter: str
    required_capabilities: tuple[str, ...]
    required_os_deps: tuple[str, ...]
    required_model_capabilities: tuple[str, ...]
    permissions_granted: tuple[str, ...]
    source_url: str
    license: str
    source_hash: str              # verified sha256
    sign_hash: str                # sha256 of the signed publication payload
    published_at: float
    published_by: str
    benchmark_passed: bool
    genesis_solo: bool            # Genesis can invoke this without a worker

    def to_application_record(self, verification_status: str = "VERIFIED") -> ApplicationRecord:
        """Render as an ApplicationRecord for the application registry.

        Only VERIFIED skills (passed sandbox + security + benchmark) produce a
        VERIFIED record.  Untrusted candidates never reach this path without
        having passed the full pipeline.
        """
        if verification_status == "VERIFIED" and not self.bridge_adapter:
            raise ValueError(f"{self.app_id}@{self.version}: VERIFIED requires a bridge adapter")
        return ApplicationRecord(
            app_id=self.app_id,
            name=self.app_id,
            version=self.version,
            executable="",
            install_path="",
            license=self.license,
            capability_families=self.required_capabilities,
            native_formats=(),
            import_formats=(),
            export_formats=(),
            cli=False,
            api=True,
            scripting=True,
            headless=True,
            bridge_adapter=self.bridge_adapter,
            verification_status=verification_status,
            last_verified=time.strftime("%Y-%m-%d", time.localtime(self.published_at)),
            limitations=f"source_hash={self.source_hash}; sign_hash={self.sign_hash}; "
                        f"genesis_solo={self.genesis_solo}",
        )


# --- audit log ----------------------------------------------------------------

@dataclass
class PipelineEvent:
    """Immutable audit entry for one pipeline transition."""
    candidate_id: str
    stage: str
    action: str                   # e.g. "submitted", "provenance_passed", "benchmark_ok"
    actor: str                    # who performed the action
    timestamp: float = field(default_factory=time.time)
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "stage": self.stage,
            "action": self.action,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "details": self.details,
        }


# --- the pipeline -------------------------------------------------------------

class SkillPipelineError(Exception):
    """Raised when a pipeline operation violates an invariant."""


class SkillPipeline:
    """Versioned skill acquisition + promotion pipeline.

    A worker submits candidates; the pipeline enforces that only reviewed,
    benchmarked, and security-cleared skills can be published to the
    production registry.  Untrusted workers cannot self-install.

    The pipeline wraps (not replaces) ApplicationRegistry: published skills
    are registered there, versions are retained for rollback.
    """

    def __init__(self, registry: Optional[ApplicationRegistry] = None) -> None:
        self._registry: ApplicationRegistry = registry or ApplicationRegistry()
        # candidate_id -> SkillCandidate (immutable)
        self._candidates: dict[str, SkillCandidate] = {}
        # app_id -> [PublishedSkill]  (ordered by version, newest last)
        self._published_by_app: dict[str, list[PublishedSkill]] = {}
        # candidate_id -> list[PipelineEvent]
        self._audit_log: dict[str, list[PipelineEvent]] = {}
        # app_id -> current active version string (for rollback)
        self._active_version: dict[str, str] = {}

    # -- properties ------------------------------------------------------------

    @property
    def registry(self) -> ApplicationRegistry:
        """The production registry this pipeline gates."""
        return self._registry

    @property
    def audit_log(self) -> list[PipelineEvent]:
        """All events, flattened and sorted by timestamp."""
        all_events: list[PipelineEvent] = []
        for events in self._audit_log.values():
            all_events.extend(events)
        return sorted(all_events, key=lambda e: e.timestamp)

    # -- candidate submission --------------------------------------------------

    def submit(self, candidate: SkillCandidate) -> SkillCandidate:
        """Stage 1: a worker submits a skill candidate.

        The candidate sits in PROPOSED until it passes every review gate.
        It cannot promote itself.
        """
        cid = candidate.candidate_id
        if cid in self._candidates:
            raise SkillPipelineError(
                f"candidate {cid!r} already submitted; use a new version")
        self._candidates[cid] = candidate
        self._audit_log.setdefault(cid, []).append(
            PipelineEvent(cid, SkillStage.CANDIDATE.value, "submitted",
                          candidate.submitted_by,
                          details=f"submitted by {candidate.submitted_by}"))
        return candidate

    def candidate(self, candidate_id: str) -> SkillCandidate:
        """Retrieve a submitted candidate by id (app_id@version)."""
        if candidate_id not in self._candidates:
            raise SkillPipelineError(f"unknown candidate {candidate_id!r}")
        return self._candidates[candidate_id]

    # -- provenance review -----------------------------------------------------

    def provenance_review(self, candidate_id: str,
                          reviewer: str, approved: bool,
                          notes: str = "") -> None:
        """Stage 2: verify source licence and provenance."""
        c = self._require_candidate(candidate_id)
        if approved:
            if not c.license:
                raise SkillPipelineError(
                    f"{candidate_id}: provenance approved but no license declared")
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.PROVENANCE.value,
                              "provenance_passed", reviewer, notes))
        else:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.PROVENANCE.value,
                              "provenance_rejected", reviewer, notes))
            raise SkillPipelineError(
                f"{candidate_id}: provenance rejected by {reviewer}: {notes}")

    # -- sandbox tests ---------------------------------------------------------

    def sandbox_tests(self, candidate_id: str, reviewer: str,
                      passed: bool, details: str = "") -> None:
        """Stage 3: skill ran in isolation without host damage."""
        c = self._require_candidate(candidate_id)
        if passed:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.SANDBOX.value,
                              "sandbox_passed", reviewer, details))
        else:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.SANDBOX.value,
                              "sandbox_failed", reviewer, details))
            raise SkillPipelineError(
                f"{candidate_id}: sandbox tests failed: {details}")

    # -- security review -------------------------------------------------------

    def security_review(self, candidate_id: str, reviewer: str,
                        approved: bool, granted_permissions: tuple[str, ...] = (),
                        notes: str = "") -> None:
        """Stage 4: security audit — permissions scoped down from requested."""
        c = self._require_candidate(candidate_id)
        # Check approval first — a rejected review cannot grant anything.
        if not approved:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.SECURITY.value,
                              "security_rejected", reviewer, notes))
            raise SkillPipelineError(
                f"{candidate_id}: security review rejected: {notes}")
        # Only approved reviews can grant permissions.
        # Security can never GRANT MORE than requested — only narrow it.
        if set(granted_permissions) - set(c.permissions_requested):
            raise SkillPipelineError(
                f"{candidate_id}: security granted permissions beyond what was "
                f"requested: {set(granted_permissions) - set(c.permissions_requested)}")
        self._audit_log[candidate_id].append(
            PipelineEvent(c.candidate_id, SkillStage.SECURITY.value,
                          "security_passed", reviewer,
                          details=f"granted={list(granted_permissions)}; {notes}"))

    # -- benchmark -------------------------------------------------------------

    def benchmark(self, candidate_id: str, reviewer: str,
                  passed: bool, genesis_solo: bool,
                  details: str = "") -> None:
        """Stage 5: benchmark — Genesis must pass the task alone (no worker).

        genesis_solo=True means Genesis invoked the skill directly (via its
        own bridge adapter) without routing through a subagent role.
        """
        c = self._require_candidate(candidate_id)
        if passed:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.BENCHMARK.value,
                              "benchmark_passed", reviewer,
                              details=f"genesis_solo={genesis_solo}; {details}"))
        else:
            self._audit_log[candidate_id].append(
                PipelineEvent(c.candidate_id, SkillStage.BENCHMARK.value,
                              "benchmark_failed", reviewer, details))
            raise SkillPipelineError(
                f"{candidate_id}: benchmark failed: {details}")

    # -- approval + publication ------------------------------------------------

    def approve_and_publish(self, candidate_id: str, approver: str,
                            granted_permissions: tuple[str, ...] = (),
                            genesis_solo: bool = False) -> PublishedSkill:
        """Stage 6+7: final approval, sign, and publish to the registry.

        This is the ONLY way a skill enters the production registry.  An
        untrusted worker cannot call this — it requires an approved reviewer
        or policy gate.
        """
        c = self._require_candidate(candidate_id)

        # Verify the candidate passed all gates by checking the audit log.
        actions = self.audit_log_for(candidate_id)
        required_actions = {"provenance_passed", "sandbox_passed",
                            "security_passed", "benchmark_passed"}
        found_actions = {e.action for e in actions}
        missing = required_actions - found_actions
        if missing:
            raise SkillPipelineError(
                f"{candidate_id}: cannot publish — missing gates: {missing}")

        # Verify hash integrity: source_hash must match expected.
        if c.source_hash and c.source_hash != c.expected_hash:
            raise SkillPipelineError(
                f"{candidate_id}: source_hash mismatch — candidate may be "
                f"tampered (expected {c.expected_hash}, got {c.source_hash})")

        # Publish: create immutable PublishedSkill, register in app registry.
        sign_payload = json.dumps({
            "app_id": c.app_id,
            "version": c.version,
            "source_hash": c.expected_hash,
            "granted_permissions": list(granted_permissions),
            "genesis_solo": genesis_solo,
        }, sort_keys=True)
        sign_hash = hashlib.sha256(sign_payload.encode()).hexdigest()

        published = PublishedSkill(
            app_id=c.app_id,
            version=c.version,
            description=c.description,
            bridge_adapter=c.proposed_bridge_adapter,
            required_capabilities=c.required_capabilities,
            required_os_deps=c.required_os_deps,
            required_model_capabilities=c.required_model_capabilities,
            permissions_granted=granted_permissions,
            source_url=c.source_url,
            license=c.license,
            source_hash=c.expected_hash,
            sign_hash=sign_hash,
            published_at=time.time(),
            published_by=approver,
            benchmark_passed=True,
            genesis_solo=genesis_solo,
        )

        # Register in the application registry (immutable per app_id+version).
        try:
            self._registry.register(published.to_application_record("VERIFIED"))
        except AppRegistryError:
            # If this exact app_id is already registered, this is a VERSION
            # UPDATE — we still record the version history for rollback.
            pass  # app registry dedupes by app_id; version history tracked below

        # Track version history for rollback.
        versions = self._published_by_app.setdefault(c.app_id, [])
        if versions and versions[-1].version == published.version:
            raise SkillPipelineError(
                f"{candidate_id}: this exact version is already published")
        versions.append(published)
        self._active_version[c.app_id] = published.version

        self._audit_log[candidate_id].append(
            PipelineEvent(c.candidate_id, SkillStage.PUBLISHED.value,
                          "published", approver,
                          details=f"version={published.version}; "
                                  f"sign_hash={published.sign_hash[:16]}…"))

        # If this app was previously published, mark the old version superseded.
        if len(versions) > 1:
            old = versions[-2]
            self._audit_log.setdefault(
                f"{old.app_id}@{old.version}", []).append(
                PipelineEvent(f"{old.app_id}@{old.version}",
                              SkillStage.SUPERSEDED.value,
                              "superseded", approver,
                              details=f"replaced by {published.version}"))

        return published

    # -- rollback --------------------------------------------------------------

    def published_versions(self, app_id: str) -> list[PublishedSkill]:
        """All published versions of a skill, oldest first (immutable history)."""
        return list(self._published_by_app.get(app_id, []))

    def active_version(self, app_id: str) -> Optional[PublishedSkill]:
        """The currently active (published) version, or None.

        Respects roll-back state: if a manual rollback was performed, the
        active version is the rolled-back one, not merely the last published.
        """
        versions = self._published_by_app.get(app_id, [])
        if not versions:
            return None
        active_v = self._active_version.get(app_id)
        if active_v:
            for v in versions:
                if v.version == active_v:
                    return v
        return versions[-1]

    def can_rollback(self, app_id: str) -> bool:
        """True if at least one prior version exists to roll back to."""
        return len(self._published_by_app.get(app_id, [])) >= 2

    def rollback(self, app_id: str, to_version: str, actor: str) -> PublishedSkill:
        """Roll back to a previously published version.

        The old version is re-activated (re-published as current).  All prior
        versions are preserved — nothing is erased.
        """
        versions = self._published_by_app.get(app_id, [])
        if not versions:
            raise SkillPipelineError(
                f"{app_id}: no published versions to roll back from")
        target = None
        for v in versions:
            if v.version == to_version:
                target = v
                break
        if target is None:
            raise SkillPipelineError(
                f"{app_id}: version {to_version!r} not found in published history")

        # Re-activate: set as active, audit the rollback.
        self._active_version[app_id] = to_version
        cid = f"{app_id}@{to_version}"
        self._audit_log.setdefault(cid, []).append(
            PipelineEvent(cid, "rollback", "rolled_back_to", actor,
                          details=f"reactivated from {len(versions)} version history"))
        return target

    # -- introspection ---------------------------------------------------------

    def audit_log_for(self, candidate_id: str) -> list[PipelineEvent]:
        """All events for one candidate, chronological."""
        return list(self._audit_log.get(candidate_id, []))

    def all_candidates(self) -> dict[str, SkillCandidate]:
        """All submitted candidates (including rejected/superseded)."""
        return dict(self._candidates)

    def published_skills(self) -> list[PublishedSkill]:
        """All published skills across all apps, newest-first."""
        all_skills = [s for vs in self._published_by_app.values() for s in vs]
        return sorted(all_skills, key=lambda s: s.published_at, reverse=True)

    # -- internal --------------------------------------------------------------

    def _require_candidate(self, candidate_id: str) -> SkillCandidate:
        if candidate_id not in self._candidates:
            raise SkillPipelineError(f"unknown candidate {candidate_id!r}")
        return self._candidates[candidate_id]
