"""Source Adapter interface for the Aetherius Knowledge & Provenance Fabric.

Defines the canonical interface that all conversation, repository, file,
media, and desktop source adapters implement (§4, §54).

Do not implement adapters directly against this interface — inherit from
KnowledgeSourceAdapter and implement the supported capabilities.

Access methods (§5 priority):
  1. OFFICIAL API / CONNECTOR
  2. USER-AUTHORISED EXPORT / IMPORT
  3. LOCAL APPLICATION API / MCP / CLI
  4. AUTHORISED BROWSER AUTOMATION
  5. AUTHORISED DESKTOP UI AUTOMATION
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator, Optional


# -- Source adapter capability flags ------------------------------------------
CAP_LIST_CONVERSATIONS = "list_conversations"
CAP_GET_METADATA = "get_metadata"
CAP_READ_MESSAGES = "read_messages"
CAP_SEARCH = "search"
CAP_READ_ATTACHMENTS = "read_attachments"
CAP_READ_CODE_BLOCKS = "read_code_blocks"
CAP_READ_IMAGES = "read_images"
CAP_READ_LINKS = "read_links"

CAP_ALL = (
    CAP_LIST_CONVERSATIONS,
    CAP_GET_METADATA,
    CAP_READ_MESSAGES,
    CAP_SEARCH,
    CAP_READ_ATTACHMENTS,
    CAP_READ_CODE_BLOCKS,
    CAP_READ_IMAGES,
    CAP_READ_LINKS,
)

# Source types
SOURCE_TYPE_CONVERSATION = "conversation"
SOURCE_TYPE_REPOSITORY = "repository"
SOURCE_TYPE_FILE = "file"
SOURCE_TYPE_IMAGE = "image"
SOURCE_TYPE_AUDIO = "audio"
SOURCE_TYPE_VIDEO = "video"
SOURCE_TYPE_DOCUMENT = "document"

SOURCE_TYPES = (
    SOURCE_TYPE_CONVERSATION,
    SOURCE_TYPE_REPOSITORY,
    SOURCE_TYPE_FILE,
    SOURCE_TYPE_IMAGE,
    SOURCE_TYPE_AUDIO,
    SOURCE_TYPE_VIDEO,
    SOURCE_TYPE_DOCUMENT,
)

# Access methods (§5)
ACCESS_OFFICIAL_API = "official_api"
ACCESS_EXPORT = "export"
ACCESS_LOCAL_APP_API = "local_app_api"
ACCESS_BROWSER_AUTOMATION = "browser_automation"
ACCESS_DESKTOP_UI = "desktop_ui"

ACCESS_METHODS = (
    ACCESS_OFFICIAL_API,
    ACCESS_EXPORT,
    ACCESS_LOCAL_APP_API,
    ACCESS_BROWSER_AUTOMATION,
    ACCESS_DESKTOP_UI,
)

# Adapter states (§61)
STATE_SPECIFIED = "SPECIFIED"
STATE_ADAPTER_AVAILABLE = "ADAPTER_AVAILABLE"
STATE_AUTH_REQUIRED = "AUTH_REQUIRED"
STATE_PARTIAL = "PARTIAL"
STATE_INDEXING = "INDEXING"
STATE_INDEXED = "INDEXED"
STATE_VERIFIED = "VERIFIED"
STATE_DEGRADED = "DEGRADED"
STATE_BLOCKED = "BLOCKED"
STATE_STALE = "STALE"
STATE_SUPERSEDED = "SUPERSEDED"
STATE_FAILED = "FAILED"

STATES = (
    STATE_SPECIFIED,
    STATE_ADAPTER_AVAILABLE,
    STATE_AUTH_REQUIRED,
    STATE_PARTIAL,
    STATE_INDEXING,
    STATE_INDEXED,
    STATE_VERIFIED,
    STATE_DEGRADED,
    STATE_BLOCKED,
    STATE_STALE,
    STATE_SUPERSEDED,
    STATE_FAILED,
)


@dataclass
class SourceMetadata:
    """Metadata for a single source item (§10).

    Every ingested source receives a stable record.
    """
    source_id: str = ""           # stable internal ID, e.g. SRC-CHATGPT-000184
    source_type: str = SOURCE_TYPE_CONVERSATION
    platform: str = ""            # chatgpt, claude, github, local, etc.
    remote_id: str = ""           # platform-native ID
    remote_url: str = ""          # canonical URL if available
    title: str = ""
    created_at: float = 0.0       # epoch
    updated_at: float = 0.0       # epoch
    access_method: str = ACCESS_OFFICIAL_API
    owner: str = "Jonathan"
    authorisation: str = ""       # AUTH_REQUIRED | owner-authorised | etc.
    privacy_class: str = "PROJECT"
    projects: list[str] = field(default_factory=list)
    content_hash: str = ""        # SHA-256 of content
    attachments: list[dict[str, Any]] = field(default_factory=list)
    state: str = STATE_SPECIFIED
    last_checked: float = 0.0
    evidence: str = ""            # VERIFIED_LIVE | VERIFIED_CONFIGURED | etc.
    adapter_id: str = ""          # which adapter can read this
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content_hash:
            self.content_hash = hashlib.sha256(
                f"{self.source_id}:{self.title}".encode()
            ).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceMetadata":
        return cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})


class KnowledgeSourceAdapter:
    """Base class for source adapters (§4).

    Subclasses implement the capabilities they support. Unsupported
    capabilities raise NotImplementedError or return empty/default results.
    """

    adapter_id: str = "base"       # stable adapter ID
    platform: str = "base"        # platform name
    source_type: str = SOURCE_TYPE_CONVERSATION
    access_method: str = ACCESS_OFFICIAL_API
    state: str = STATE_SPECIFIED
    supported_capabilities: tuple[str, ...] = ()
    privacy_class: str = "PROJECT"
    owner: str = "Jonathan"
    authorisation_required: bool = True
    notes: str = ""

    # -- Core interface --------------------------------------------------------

    def list_sources(self, project: str | None = None,
                     limit: int = 100) -> list[SourceMetadata]:
        """List sources from this adapter. (§4: list_conversations)"""
        raise NotImplementedError(
            f"{self.adapter_id}: list_sources not supported")

    def get_metadata(self, source_id: str) -> Optional[SourceMetadata]:
        """Get metadata for a specific source. (§4: get_metadata)"""
        raise NotImplementedError(
            f"{self.adapter_id}: get_metadata not supported")

    def read_content(self, source_id: str) -> str:
        """Read the main content of a source. (§4: read_messages)"""
        raise NotImplementedError(
            f"{self.adapter_id}: read_content not supported")

    def read_content_stream(
        self, source_id: str
    ) -> Iterator[SourceMetadata]:
        """Stream content in chunks. (§4: read for large sources)"""
        raise NotImplementedError(
            f"{self.adapter_id}: read_content_stream not supported")

    def search(
        self, query: str, project: str | None = None,
        limit: int = 20,
    ) -> list[SourceMetadata]:
        """Search sources by content/keywords. (§4: search_conversations)"""
        raise NotImplementedError(
            f"{self.adapter_id}: search not supported")

    def read_attachments(self, source_id: str) -> list[dict[str, Any]]:
        """Read attachments for a source. (§4: read_attachments)"""
        raise NotImplementedError(
            f"{self.adapter_id}: read_attachments not supported")

    def read_code_blocks(self, source_id: str) -> list[str]:
        """Extract code blocks from a source. (§4: read_code_blocks)"""
        raise NotImplementedError(
            f"{self.adapter_id}: read_code_blocks not supported")

    def read_links(self, source_id: str) -> list[str]:
        """Extract links from a source. (§4: read_links)"""
        raise NotImplementedError(
            f"{self.adapter_id}: read_links not supported")

    def hash_source(self, source_id: str) -> str:
        """Compute content hash for incremental sync. (§9)"""
        raise NotImplementedError(
            f"{self.adapter_id}: hash_source not supported")

    def is_changed(self, source_id: str) -> bool:
        """Check if a source has changed since last indexing. (§9)"""
        try:
            current_hash = self.hash_source(source_id)
            # In a full implementation, compare against stored hash
            return True  # conservative: always check
        except NotImplementedError:
            return False  # unknown — skip

    # -- Adapter metadata ------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Return adapter metadata for the registry (§60)."""
        return {
            "adapter_id": self.adapter_id,
            "platform": self.platform,
            "source_type": self.source_type,
            "access_method": self.access_method,
            "state": self.state,
            "supported_capabilities": list(self.supported_capabilities),
            "privacy_class": self.privacy_class,
            "owner": self.owner,
            "authorisation_required": self.authorisation_required,
            "notes": self.notes,
        }


def compute_content_hash(content: str, salt: str = "") -> str:
    """Compute SHA-256 hash of content for incremental sync (§9, §10)."""
    h = hashlib.sha256()
    h.update(salt.encode() if salt else b"aetherius")
    h.update(content.encode("utf-8", errors="replace"))
    return h.hexdigest()


def stable_source_id(platform: str, remote_id: str) -> str:
    """Generate a stable source ID (§10)."""
    return f"SRC-{platform.upper()}-{remote_id.replace('/', '-')[:32]}"


__all__ = [
    # adapter base + interface
    "KnowledgeSourceAdapter",
    "SourceMetadata",
    # source types
    "SOURCE_TYPE_CONVERSATION", "SOURCE_TYPE_REPOSITORY",
    "SOURCE_TYPE_FILE", "SOURCE_TYPE_IMAGE",
    "SOURCE_TYPE_AUDIO", "SOURCE_TYPE_VIDEO",
    "SOURCE_TYPE_DOCUMENT", "SOURCE_TYPES",
    # capabilities
    "CAP_LIST_CONVERSATIONS", "CAP_GET_METADATA", "CAP_READ_MESSAGES",
    "CAP_SEARCH", "CAP_READ_ATTACHMENTS", "CAP_READ_CODE_BLOCKS",
    "CAP_READ_IMAGES", "CAP_READ_LINKS", "CAP_ALL",
    # access methods
    "ACCESS_OFFICIAL_API", "ACCESS_EXPORT", "ACCESS_LOCAL_APP_API",
    "ACCESS_BROWSER_AUTOMATION", "ACCESS_DESKTOP_UI", "ACCESS_METHODS",
    # states
    "STATE_SPECIFIED", "STATE_ADAPTER_AVAILABLE", "STATE_AUTH_REQUIRED",
    "STATE_PARTIAL", "STATE_INDEXING", "STATE_INDEXED", "STATE_VERIFIED",
    "STATE_DEGRADED", "STATE_BLOCKED", "STATE_STALE", "STATE_SUPERSEDED",
    "STATE_FAILED", "STATES",
    # helpers
    "compute_content_hash", "stable_source_id",
]
