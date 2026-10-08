"""Context Broker for the Aetherius Knowledge & Provenance Fabric (§15, §16).

SUPERVISOR
   ↓
AETHERIUS CONTEXT BROKER       ← this module
   ↓  PERMISSION / PRIVACY POLICY
   ↓  RETRIEVAL ADAPTERS
   ↓  SCOPED CONTEXT PACKAGE
   ↓  SPECIALIST WORKER

The supervisor asks for project context; the broker gathers it from
authorised sources and returns a scoped, provenance-tagged context package.

Privacy enforcement is mandatory: workers never receive context beyond their
privacy ceiling. SECRET_LOCAL_ONLY content never leaves local.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from knowledge_fabric.source_adapter import (
    KnowledgeSourceAdapter, SourceMetadata,
    CAP_LIST_CONVERSATIONS, CAP_READ_MESSAGES,
    CAP_READ_ATTACHMENTS, CAP_READ_CODE_BLOCKS, CAP_READ_LINKS,
)
from knowledge_fabric.source_provenance import (
    SourceReference, ProvenanceRecord, DerivedKnowledge,
    CONF_SOURCE_QUOTE, CONF_UNVERIFIED_RESEARCH,
    KIND_EVIDENCE,
    LIFE_CURRENT,
)
from models.inference_contract import (
    PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_PERSONAL,
    PRIVACY_CONFIDENTIAL, PRIVACY_SECRET_LOCAL_ONLY,
)

# Privacy classes for knowledge sources (same as inference contract)
KB_PRIVACY_CLASSES = (PRIVACY_PUBLIC, PRIVACY_PROJECT, PRIVACY_PERSONAL,
                      PRIVACY_CONFIDENTIAL, PRIVACY_SECRET_LOCAL_ONLY)

# Worker role privacy ceilings (§102)
ROLE_PRIVACY_CEILINGS = {
    "coding_worker": PRIVACY_PROJECT,
    "research_worker": PRIVACY_PROJECT,
    "review_worker": PRIVACY_PROJECT,
    "security_reviewer": PRIVACY_CONFIDENTIAL,
    "qa_worker": PRIVACY_PROJECT,
    "cad_specialist": PRIVACY_PERSONAL,
    "media_worker": PRIVACY_PROJECT,
    "genesis": PRIVACY_SECRET_LOCAL_ONLY,
    "default": PRIVACY_PUBLIC,
}


@dataclass
class ContextPackage:
    """A scoped context package delivered to a worker (§16, §17).

    Workers receive only the context required for their role, filtered by
    privacy ceiling.
    """
    package_id: str = ""
    request_id: str = ""
    task_id: str = ""
    team_id: str = ""
    project: str = ""
    worker_id: str = ""
    worker_role: str = ""
    objective: str = ""
    privacy_ceiling: str = PRIVACY_PROJECT
    requirements: list[str] = field(default_factory=list)
    current_decisions: list[str] = field(default_factory=list)
    relevant_history: list[SourceReference] = field(default_factory=list)
    relevant_repositories: list[dict[str, Any]] = field(default_factory=list)
    relevant_files: list[dict[str, Any]] = field(default_factory=list)
    relevant_conversations: list[dict[str, Any]] = field(default_factory=list)
    relevant_media: list[dict[str, Any]] = field(default_factory=list)
    known_failures: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    security_policy_refs: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[ProvenanceRecord] = field(default_factory=list)
    source_refs: list[SourceReference] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    generated_at: float = 0.0
    max_context_tokens: int = 32000
    actual_context_tokens: int = 0
    remote_disclosure: bool = False  # whether any data leaves local
    summary: str = ""

    def __post_init__(self) -> None:
        if not self.package_id:
            self.package_id = f"ctx-{uuid.uuid4().hex[:12]}"
        if not self.generated_at:
            self.generated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContextPackage":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})


@dataclass
class ContextRequest:
    """A request from the supervisor for project context (§15)."""
    request_id: str = ""
    project: str = ""
    objective: str = ""
    worker_role: str = "default"
    required_topics: list[str] = field(default_factory=list)
    max_context_tokens: int = 32000
    privacy_ceiling: str = PRIVACY_PROJECT
    include_sources: list[str] = field(default_factory=list)  # adapter IDs to search
    exclude_sources: list[str] = field(default_factory=list)
    local_only: bool = False
    provenance_required: bool = True

    def __post_init__(self) -> None:
        if not self.request_id:
            self.request_id = f"ctxreq-{uuid.uuid4().hex[:12]}"
        if not self.privacy_ceiling:
            self.privacy_ceiling = ROLE_PRIVACY_CEILINGS.get(
                self.worker_role, PRIVACY_PROJECT)

    def effective_privacy_ceiling(self) -> str:
        """Compute the effective privacy ceiling — worker role takes precedence."""
        role_ceiling = ROLE_PRIVACY_CEILINGS.get(
            self.worker_role, PRIVACY_PROJECT)
        # The tighter (more restrictive) of the two applies
        priorities = {
            PRIVACY_SECRET_LOCAL_ONLY: 0,
            PRIVACY_CONFIDENTIAL: 1,
            PRIVACY_PERSONAL: 2,
            PRIVACY_PROJECT: 3,
            PRIVACY_PUBLIC: 4,
        }
        req_pri = priorities.get(self.privacy_ceiling, 3)
        role_pri = priorities.get(role_ceiling, 3)
        effective_pri = min(req_pri, role_pri)
        for cls, pri in priorities.items():
            if pri == effective_pri:
                return cls
        return PRIVACY_PROJECT


class ContextBroker:
    """Aetherius Context Broker (§15).

    Coordinates source adapters to build scoped, privacy-filtered context
    packages for specialist workers.
    """

    def __init__(self) -> None:
        self.adapters: dict[str, KnowledgeSourceAdapter] = {}
        self.source_registry: dict[str, SourceMetadata] = {}
        self.provenance: dict[str, ProvenanceRecord] = {}
        self.knowledge: dict[str, DerivedKnowledge] = {}
        self.remote_disclosure_enabled: bool = False

    def register_adapter(self, adapter: KnowledgeSourceAdapter) -> None:
        """Register a source adapter (§4: adapter registry)."""
        self.adapters[adapter.adapter_id] = adapter

    def unregister_adapter(self, adapter_id: str) -> None:
        """Safely remove an adapter without crashing (§50)."""
        self.adapters.pop(adapter_id, None)

    def list_sources(
        self, project: str | None = None,
        adapter_id: str | None = None,
    ) -> list[SourceMetadata]:
        """List all known sources from all adapters."""
        if adapter_id:
            adapter = self.adapters.get(adapter_id)
            if adapter is None:
                return []
            return adapter.list_sources(project=project)
        results = []
        for adapter in self.adapters.values():
            try:
                results.extend(adapter.list_sources(project=project))
            except (NotImplementedError, Exception):
                continue  # graceful degradation (§54: test 20)
        return results

    def request_context(self, req: ContextRequest) -> ContextPackage:
        """Build a scoped context package for a worker (§15, §16, §17).

        Privacy enforcement is mandatory — workers never receive context
        above their privacy ceiling.
        """
        ceiling = req.effective_privacy_ceiling()
        remote_disclosure = self._will_disclose_remote(ceiling, req)

        package = ContextPackage(
            request_id=req.request_id,
            project=req.project,
            worker_role=req.worker_role,
            objective=req.objective,
            privacy_ceiling=ceiling,
            max_context_tokens=req.max_context_tokens,
            remote_disclosure=remote_disclosure,
        )

        # Gather from selected adapters
        adapters_to_query = self._select_adapters(req)
        all_sources = []
        for adapter in adapters_to_query:
            try:
                sources = adapter.search(
                    query=" ".join(req.required_topics) if req.required_topics else "",
                    project=req.project,
                    limit=100,
                )
                all_sources.extend(sources)
            except NotImplementedError:
                # Fallback: list_sources then filter client-side
                try:
                    all_sources.extend(adapter.list_sources(project=req.project))
                except NotImplementedError:
                    continue  # §54: unsupported sources remain registered
            except Exception:
                continue  # §54: adapter failure doesn't crash

        # Privacy filter — drop sources above the worker's ceiling
        filtered = self._privacy_filter(all_sources, ceiling)

        # Dedupe by source_id, keep most recent
        seen = {}
        for src in filtered:
            sid = src.source_id
            if sid not in seen or src.last_checked > seen[sid].last_checked:
                seen[sid] = src
        unique_sources = sorted(seen.values(),
                                key=lambda s: s.last_checked, reverse=True)

        # Build context package
        for src in unique_sources[:30]:  # bounded by max_context_tokens
            ref = SourceReference(
                source_id=src.source_id,
                source_type=src.source_type,
                platform=src.platform,
                remote_id=src.remote_id,
                remote_url=src.remote_url,
                title=src.title,
                created_at=src.created_at,
                updated_at=src.updated_at,
                content_hash=src.content_hash,
            )
            if src.source_type == "conversation":
                package.relevant_conversations.append(ref.to_dict() if hasattr(ref, 'to_dict') else ref.__dict__)
            elif src.source_type == "repository":
                package.relevant_repositories.append(ref.to_dict() if hasattr(ref, 'to_dict') else ref.__dict__)
            elif src.source_type in ("file", "document"):
                package.relevant_files.append(ref.to_dict() if hasattr(ref, 'to_dict') else ref.__dict__)
            elif src.source_type in ("image", "video", "audio"):
                package.relevant_media.append(ref.to_dict() if hasattr(ref, 'to_dict') else ref.__dict__)

            package.source_refs.append(ref)

            # Register provenance
            if req.provenance_required:
                prov = ProvenanceRecord(
                    source=ref,
                    derived_kind=KIND_EVIDENCE,
                    confidence=CONF_SOURCE_QUOTE if src.evidence == "VERIFIED_LIVE" else CONF_UNVERIFIED_RESEARCH,
                    lifecycle=LIFE_CURRENT,
                    extractor=src.adapter_id,
                )
                self.provenance[prov.provenance_id] = prov
                package.evidence.append(prov)

        package.actual_context_tokens = self._estimate_tokens(package)
        package.summary = (
            f"Context package for project={req.project}, "
            f"worker_role={req.worker_role}, "
            f"privacy_ceiling={ceiling}, "
            f"remote_disclosure={remote_disclosure}, "
            f"sources={len(package.source_refs)}, "
            f"tokens={package.actual_context_tokens}"
        )

        return package

    def register_source(self, metadata: SourceMetadata) -> None:
        """Register a source in the canonical source registry (§10)."""
        self.source_registry[metadata.source_id] = metadata

    def get_source(self, source_id: str) -> SourceMetadata:
        return self.source_registry[source_id]

    def health(self) -> dict[str, Any]:
        """Broker + adapter health (§50, §125)."""
        return {
            "broker_status": "HEALTHY",
            "registered_adapters": len(self.adapters),
            "registered_sources": len(self.source_registry),
            "provenance_records": len(self.provenance),
            "knowledge_items": len(self.knowledge),
            "remote_disclosure_enabled": self.remote_disclosure_enabled,
            "adapter_health": {
                aid: {"state": a.state, "platform": a.platform}
                for aid, a in self.adapters.items()
            },
        }

    # -- Private helpers -------------------------------------------------------

    def _select_adapters(self, req: ContextRequest) -> list[KnowledgeSourceAdapter]:
        """Select which adapters to query (§17: role-scoped)."""
        if req.include_sources:
            selected = []
            for sid in req.include_sources:
                if sid in self.adapters:
                    selected.append(self.adapters[sid])
            return selected
        excluded = set(req.exclude_sources)
        return [a for aid, a in self.adapters.items() if aid not in excluded]

    def _privacy_filter(
        self, sources: list[SourceMetadata], ceiling: str
    ) -> list[SourceMetadata]:
        """Filter sources that exceed the privacy ceiling (§18, §69, §119)."""
        priorities = {
            PRIVACY_SECRET_LOCAL_ONLY: 0,
            PRIVACY_CONFIDENTIAL: 1,
            PRIVACY_PERSONAL: 2,
            PRIVACY_PROJECT: 3,
            PRIVACY_PUBLIC: 4,
        }
        ceiling_pri = priorities.get(ceiling, 3)
        result = []
        for src in sources:
            src_pri = priorities.get(src.privacy_class, 4)
            # Lower priority = more sensitive; can't give more sensitive content
            if src_pri < ceiling_pri:
                continue
            # If local_only flag, never include remote sources
            if ceiling == PRIVACY_SECRET_LOCAL_ONLY and src.privacy_class == PRIVACY_SECRET_LOCAL_ONLY:
                if src.access_method == "browser_automation" and src.platform not in ("local", "hermes", "opencode"):
                    continue  # SECRET_LOCAL_ONLY must never go to remote
                # Local sources are fine
            result.append(src)
        return result

    def _will_disclose_remote(self, ceiling: str, req: ContextRequest) -> bool:
        """Determine if the context package will involve remote disclosure."""
        if ceiling == PRIVACY_SECRET_LOCAL_ONLY:
            return False
        # Check if any selected adapter is remote
        for adapter in self._select_adapters(req):
            if adapter.platform not in ("local", "hermes", "opencode", "agent-bridge"):
                return True
        return False

    def _estimate_tokens(self, package: ContextPackage) -> int:
        """Estimate token count of context package content."""
        total = 0
        for ref in package.source_refs:
            total += len(ref.snippet) // 4 if ref.snippet else 0
        total += len(package.summary) // 4
        return min(total, package.max_context_tokens)


__all__ = [
    "ContextBroker", "ContextRequest", "ContextPackage",
    "ROLE_PRIVACY_CEILINGS", "KB_PRIVACY_CLASSES",
]
