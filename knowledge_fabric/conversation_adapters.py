"""Conversation source adapter foundation (§15–§20).

THE POINT OF THIS MODULE

Every AI platform stores conversations differently. Rather than write eight
ingestors, this defines ONE canonical interface that every source implements,
plus a generic export adapter that can ingest owner-authorized archives TODAY,
before any vendor-specific live adapter exists (§19).

THE HONESTY RULE (§18)

A class existing is NOT access. Each source declares an explicit state, and
the states that mean "we actually read data" — LIVE_VERIFIED — are only
assigned when a real authorized retrieval succeeded. An interface that has
never touched a source stays INTERFACE_READY.

This distinction is the whole value of the module. Marking Claude LIVE because
a Python class exists would be exactly the kind of false evidence the
programme is meant to prevent.

NO AUTHENTICATION BYPASS (§17)

Access modes are declared and ranked: official API → export/local →
browser → desktop automation. There is deliberately no code path that reads a
browser cookie store or extracts a session token. Session material stays
outside this project.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

# --------------------------------------------------------------------------
# Adapter states (§18)
# --------------------------------------------------------------------------
INTERFACE_READY = "INTERFACE_READY"
IMPLEMENTED = "IMPLEMENTED"
AUTH_REQUIRED = "AUTH_REQUIRED"
OWNER_ACTION_REQUIRED = "OWNER_ACTION_REQUIRED"
LIVE_VERIFIED = "LIVE_VERIFIED"
PARTIAL = "PARTIAL"
DEGRADED = "DEGRADED"
UNSUPPORTED = "UNSUPPORTED"
FAILED = "FAILED"

ALL_STATES = (INTERFACE_READY, IMPLEMENTED, AUTH_REQUIRED, OWNER_ACTION_REQUIRED,
              LIVE_VERIFIED, PARTIAL, DEGRADED, UNSUPPORTED, FAILED)


class AccessMode(str, Enum):
    """How a source may legitimately be reached (§17)."""

    OFFICIAL_API = "OFFICIAL_API"
    OFFICIAL_CONNECTOR = "OFFICIAL_CONNECTOR"
    USER_EXPORT = "USER_EXPORT"
    LOCAL_DATABASE = "LOCAL_DATABASE"
    LOCAL_FILE = "LOCAL_FILE"
    MCP = "MCP"
    CLI = "CLI"
    AUTHORIZED_BROWSER = "AUTHORIZED_BROWSER"
    DESKTOP_AUTOMATION = "DESKTOP_AUTOMATION"
    UNSUPPORTED = "UNSUPPORTED"


# §17 priority order — earlier is preferred.
ACCESS_PRIORITY = [
    AccessMode.OFFICIAL_API,
    AccessMode.OFFICIAL_CONNECTOR,
    AccessMode.USER_EXPORT,
    AccessMode.LOCAL_DATABASE,
    AccessMode.LOCAL_FILE,
    AccessMode.MCP,
    AccessMode.CLI,
    AccessMode.AUTHORIZED_BROWSER,
    AccessMode.DESKTOP_AUTOMATION,
]

# Canonical capability names (§16)
CAP_LIST_CONVERSATIONS = "list_conversations"
CAP_PAGINATE = "paginate_conversations"
CAP_SEARCH = "search_conversations"
CAP_GET_CONVERSATION = "get_conversation"
CAP_READ_MESSAGES = "read_messages"
CAP_READ_ATTACHMENTS = "read_attachments"
CAP_READ_CODE_BLOCKS = "read_code_blocks"
CAP_READ_LINKS = "read_links"
CAP_GET_METADATA = "get_metadata"
CAP_GET_CREATED_AT = "get_created_at"
CAP_GET_UPDATED_AT = "get_updated_at"
CAP_GET_PROJECT = "get_project"
CAP_GET_SOURCE_URL = "get_source_url"
CAP_GET_REMOTE_ID = "get_remote_id"
CAP_CONTENT_HASH = "get_content_hash"

ALL_CONVERSATION_CAPABILITIES = (
    CAP_LIST_CONVERSATIONS, CAP_PAGINATE, CAP_SEARCH, CAP_GET_CONVERSATION,
    CAP_READ_MESSAGES, CAP_READ_ATTACHMENTS, CAP_READ_CODE_BLOCKS,
    CAP_READ_LINKS, CAP_GET_METADATA, CAP_GET_CREATED_AT, CAP_GET_UPDATED_AT,
    CAP_GET_PROJECT, CAP_GET_SOURCE_URL, CAP_GET_REMOTE_ID, CAP_CONTENT_HASH,
)


class UnsupportedCapabilityError(NotImplementedError):
    """Raised when a caller uses a capability a source does not advertise (§16)."""

    def __init__(self, source_id: str, capability: str) -> None:
        super().__init__(
            f"source '{source_id}' does not support '{capability}'")
        self.source_id = source_id
        self.capability = capability


@dataclass
class ConversationMessage:
    """One message in a conversation."""

    message_id: str
    role: str                      # user / assistant / system / tool
    content: str
    created_at: str = ""
    author: str = ""
    attachments: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    code_blocks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            ("message_id", self.message_id),
            ("role", self.role),
            ("created_at", self.created_at),
            ("author", self.author),
            ("content_hash", hash_text(self.content)),
            ("attachments", list(self.attachments)),
            ("links", list(self.links)),
            ("code_blocks", list(self.code_blocks)),
            # Content itself is NOT stored in the normalized record: the
            # fabric keeps a hash plus a pointer, so raw conversation text is
            # not duplicated into a public repository.
            ("content_length", len(self.content)),
        ])


@dataclass
class ConversationRecord:
    """A normalized conversation (§19)."""

    conversation_id: str
    source_id: str
    platform: str
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    project: str = ""
    source_url: str = ""
    message_count: int = 0
    content_hash: str = ""
    messages: list[ConversationMessage] = field(default_factory=list)

    def to_dict(self, include_messages: bool = True) -> dict[str, Any]:
        out = OrderedDict([
            ("conversation_id", self.conversation_id),
            ("source_id", self.source_id),
            ("platform", self.platform),
            ("title", self.title),
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
            ("project", self.project),
            ("source_url", self.source_url),
            ("message_count", self.message_count),
            ("content_hash", self.content_hash),
        ])
        if include_messages:
            out["messages"] = [m.to_dict() for m in self.messages]
        return out


def hash_text(text: str) -> str:
    """Stable content hash for incremental sync (§20)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ConversationSourceAdapter:
    """Canonical interface every conversation source implements (§15, §16).

    Subclasses DECLARE capabilities honestly. A capability not in
    ``supported_capabilities`` raises ``UnsupportedCapabilityError`` rather
    than returning an empty result that looks like real data.
    """

    platform: str = "unknown"
    source_id: str = ""
    access_mode: AccessMode = AccessMode.UNSUPPORTED
    supported_capabilities: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.state = INTERFACE_READY
        self._sync_cursor: dict[str, str] = {}   # conversation_id -> content_hash

    # -- capability gate ----------------------------------------------------
    def supports(self, capability: str) -> bool:
        return capability in self.supported_capabilities

    def require(self, capability: str) -> None:
        if not self.supports(capability):
            raise UnsupportedCapabilityError(self.source_id or self.platform,
                                             capability)

    def capabilities(self) -> dict[str, Any]:
        """Honest advertisement: what works, what does not, and current state."""
        return OrderedDict([
            ("platform", self.platform),
            ("source_id", self.source_id),
            ("access_mode", self.access_mode.value),
            ("state", self.state),
            ("supported", sorted(self.supported_capabilities)),
            ("unsupported", sorted(
                c for c in ALL_CONVERSATION_CAPABILITIES
                if c not in self.supported_capabilities)),
        ])

    # -- interface (subclasses override) -----------------------------------
    def list_conversations(self, limit: int = 50) -> list[ConversationRecord]:
        self.require(CAP_LIST_CONVERSATIONS)
        return []

    def paginate_conversations(self, cursor: str = "",
                               page_size: int = 50) -> tuple[list[ConversationRecord], str]:
        """Return (records, next_cursor). Empty next_cursor means exhausted."""
        self.require(CAP_PAGINATE)
        return [], ""

    def search_conversations(self, query: str) -> list[ConversationRecord]:
        self.require(CAP_SEARCH)
        return []

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        self.require(CAP_GET_CONVERSATION)
        return None

    def read_messages(self, conversation_id: str) -> list[ConversationMessage]:
        self.require(CAP_READ_MESSAGES)
        return []

    def get_content_hash(self, conversation_id: str) -> str:
        self.require(CAP_CONTENT_HASH)
        return ""

    # -- incremental sync (§20) --------------------------------------------
    def sync(self, limit: int = 50) -> dict[str, Any]:
        """Ingest, skipping conversations whose hash has not changed (§20).

        Returns a summary of SKIPPED vs INGESTED so a full history is not
        re-parsed on every startup.
        """
        ingested, skipped = [], []
        for conv in self.list_conversations(limit=limit):
            try:
                new_hash = self.get_content_hash(conv.conversation_id)
            except UnsupportedCapabilityError:
                new_hash = conv.content_hash
            old_hash = self._sync_cursor.get(conv.conversation_id)
            if new_hash and new_hash == old_hash:
                skipped.append(conv.conversation_id)
                continue
            self._sync_cursor[conv.conversation_id] = new_hash
            ingested.append(conv.conversation_id)
        return OrderedDict([
            ("source_id", self.source_id or self.platform),
            ("state", self.state),
            ("ingested", ingested),
            ("skipped", skipped),
            ("ingested_count", len(ingested)),
            ("skipped_count", len(skipped)),
        ])


class GenericConversationExportAdapter(ConversationSourceAdapter):
    """Ingests owner-authorized conversation archives (§19).

    Supports JSON, Markdown, TXT and ZIP export bundles. This is the
    deliberately unglamorous adapter that makes historical knowledge usable
    NOW, while the vendor-specific live adapters remain blocked on
    authorization.

    Raw message text is hashed and counted, not copied into the fabric, so a
    private conversation is not duplicated into a public repository.
    """

    def __init__(self, platform: str = "generic",
                 archive_path: str | Path | None = None) -> None:
        super().__init__()
        self.platform = platform
        self.source_id = f"conversation_export:{platform}"
        self.access_mode = AccessMode.USER_EXPORT
        self.supported_capabilities = (
            CAP_LIST_CONVERSATIONS, CAP_PAGINATE, CAP_GET_CONVERSATION,
            CAP_READ_MESSAGES, CAP_GET_METADATA, CAP_GET_CREATED_AT,
            CAP_GET_UPDATED_AT, CAP_GET_PROJECT, CAP_GET_SOURCE_URL,
            CAP_GET_REMOTE_ID, CAP_CONTENT_HASH, CAP_READ_CODE_BLOCKS,
            CAP_READ_LINKS,
        )
        self.archive_path = Path(archive_path) if archive_path else None
        self._records: dict[str, ConversationRecord] = {}
        if self.archive_path and self.archive_path.exists():
            self._load(self.archive_path)
            self.state = IMPLEMENTED

    # -- parsing ------------------------------------------------------------
    def _load(self, path: Path) -> None:
        if path.suffix.lower() == ".zip":
            self._load_zip(path)
        elif path.suffix.lower() == ".json":
            self._load_json(path)
        else:
            self._load_text(path)

    def _load_zip(self, path: Path) -> None:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith((".json", ".md", ".txt")):
                    try:
                        text = zf.read(name).decode("utf-8", "replace")
                    except Exception:
                        continue
                    if name.endswith(".json"):
                        self._ingest_json_text(text, source=name)
                    else:
                        self._ingest_text(text, source=name)

    def _load_json(self, path: Path) -> None:
        self._ingest_json_text(path.read_text(encoding="utf-8", errors="replace"),
                               source=path.name)

    def _load_text(self, path: Path) -> None:
        self._ingest_text(path.read_text(encoding="utf-8", errors="replace"),
                          source=path.name)

    def _ingest_json_text(self, text: str, source: str) -> None:
        """Parse an exported conversation JSON into normalized records.

        Tolerant by design: vendor export schemas differ, and a field that is
        absent should degrade the record, not abort the whole import.
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            self._ingest_text(text, source=source)
            return

        conversations = data if isinstance(data, list) else [data]
        for conv in conversations:
            if not isinstance(conv, dict):
                continue
            conv_id = str(conv.get("id") or conv.get("conversation_id")
                          or conv.get("uuid") or source)
            messages = self._parse_messages(conv.get("messages")
                                            or conv.get("mapping")
                                            or [])
            body = "".join(m.content for m in messages)
            self._records[conv_id] = ConversationRecord(
                conversation_id=conv_id,
                source_id=self.source_id,
                platform=self.platform,
                title=str(conv.get("title") or conv.get("name") or ""),
                created_at=str(conv.get("created_at") or conv.get("create_time")
                               or ""),
                updated_at=str(conv.get("updated_at") or conv.get("update_time")
                               or ""),
                project=str(conv.get("project") or conv.get("folder") or ""),
                source_url=str(conv.get("url") or conv.get("source_url") or ""),
                message_count=len(messages),
                content_hash=hash_text(body),
                messages=messages,
            )

    def _parse_messages(self, raw: Any) -> list[ConversationMessage]:
        """Normalize the several shapes vendor exports use for messages."""
        out: list[ConversationMessage] = []
        if isinstance(raw, dict):
            # ChatGPT's nested mapping form: {node_id: {message: {...}}}
            for node_id, node in raw.items():
                if not isinstance(node, dict):
                    continue
                msg = node.get("message") if isinstance(node.get("message"),
                                                        dict) else node
                content = self._extract_content(msg.get("content"))
                role = (msg.get("author") or {}).get("role") if isinstance(
                    msg.get("author"), dict) else msg.get("role", "unknown")
                out.append(ConversationMessage(
                    message_id=str(msg.get("id") or node_id),
                    role=str(role or "unknown"),
                    content=content,
                    created_at=str(msg.get("create_time") or ""),
                ))
        elif isinstance(raw, list):
            for i, msg in enumerate(raw):
                if isinstance(msg, dict):
                    out.append(ConversationMessage(
                        message_id=str(msg.get("id") or f"msg-{i}"),
                        role=str(msg.get("role") or msg.get("author") or "unknown"),
                        content=self._extract_content(msg.get("content")),
                        created_at=str(msg.get("created_at")
                                       or msg.get("timestamp") or ""),
                    ))
                else:
                    out.append(ConversationMessage(
                        message_id=f"msg-{i}", role="unknown", content=str(msg)))
        return out

    def _extract_content(self, content: Any) -> str:
        """Pull text from the shapes vendors use for a message body."""
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                return "".join(str(p) for p in parts)
            return str(content.get("text") or "")
        if isinstance(content, list):
            return "".join(self._extract_content(c) for c in content)
        return str(content)

    def _ingest_text(self, text: str, source: str) -> None:
        """Treat a plain text/markdown export as one conversation."""
        self._records[source] = ConversationRecord(
            conversation_id=source,
            source_id=self.source_id,
            platform=self.platform,
            title=source,
            message_count=1,
            content_hash=hash_text(text),
            messages=[ConversationMessage(message_id="msg-0", role="unknown",
                                          content=text)],
        )

    # -- interface ----------------------------------------------------------
    def list_conversations(self, limit: int = 50) -> list[ConversationRecord]:
        self.require(CAP_LIST_CONVERSATIONS)
        return list(self._records.values())[:limit]

    def paginate_conversations(self, cursor: str = "",
                               page_size: int = 50) -> tuple[list[ConversationRecord], str]:
        self.require(CAP_PAGINATE)
        start = int(cursor) if cursor.isdigit() else 0
        records = list(self._records.values())
        page = records[start:start + page_size]
        nxt = str(start + page_size) if start + page_size < len(records) else ""
        return page, nxt

    def get_conversation(self, conversation_id: str) -> ConversationRecord | None:
        self.require(CAP_GET_CONVERSATION)
        return self._records.get(conversation_id)

    def read_messages(self, conversation_id: str) -> list[ConversationMessage]:
        self.require(CAP_READ_MESSAGES)
        conv = self._records.get(conversation_id)
        return conv.messages if conv else []

    def get_content_hash(self, conversation_id: str) -> str:
        self.require(CAP_CONTENT_HASH)
        conv = self._records.get(conversation_id)
        return conv.content_hash if conv else ""


# --------------------------------------------------------------------------
# Live adapters — interface ready, access NOT verified (§18)
# --------------------------------------------------------------------------
class _LivePlatformAdapter(ConversationSourceAdapter):
    """Base for vendor adapters whose interface is defined but access is not.

    These deliberately advertise NO data capabilities. A live adapter that
    claimed list_conversations without a verified retrieval path would be
    exactly the false claim §18 forbids.
    """

    requires_auth: bool = True
    access_note: str = ""

    def __init__(self) -> None:
        super().__init__()
        # No data capabilities until a real authorized retrieval succeeds.
        self.supported_capabilities = (CAP_GET_METADATA,)
        self.state = AUTH_REQUIRED if self.requires_auth else INTERFACE_READY


class ChatGPTAdapter(_LivePlatformAdapter):
    platform = "chatgpt"
    source_id = "conversation:chatgpt"
    access_mode = AccessMode.OFFICIAL_API
    access_note = "Official API exposes models, not conversation history."


class ClaudeAdapter(_LivePlatformAdapter):
    platform = "claude"
    source_id = "conversation:claude"
    access_mode = AccessMode.USER_EXPORT
    access_note = "Owner-authorized export required."


class ManusAdapter(_LivePlatformAdapter):
    platform = "manus"
    source_id = "conversation:manus"
    access_mode = AccessMode.UNSUPPORTED
    access_note = "No known structured access mechanism."


class KimiAdapter(_LivePlatformAdapter):
    platform = "kimi"
    source_id = "conversation:kimi"
    access_mode = AccessMode.UNSUPPORTED
    access_note = "No known structured access mechanism."


class DeepSeekAdapter(_LivePlatformAdapter):
    platform = "deepseek"
    source_id = "conversation:deepseek"
    access_mode = AccessMode.UNSUPPORTED
    access_note = "No known structured access mechanism."


class HermesAdapter(_LivePlatformAdapter):
    platform = "hermes"
    source_id = "conversation:hermes"
    # Hermes session history IS locally reachable, which makes this the one
    # platform where a real retrieval path plausibly exists without export.
    access_mode = AccessMode.LOCAL_DATABASE
    access_note = "Local session store; requires owner-authorized read path."


class OpenCodeAdapter(_LivePlatformAdapter):
    platform = "opencode"
    source_id = "conversation:opencode"
    access_mode = AccessMode.LOCAL_FILE
    access_note = "Local session files."


class OpenClawAdapter(_LivePlatformAdapter):
    platform = "openclaw"
    source_id = "conversation:openclaw"
    access_mode = AccessMode.UNSUPPORTED
    access_note = "Unconfirmed platform."


def build_conversation_registry() -> dict[str, ConversationSourceAdapter]:
    """One registry, one framework (§15) — no per-provider ingestors."""
    return OrderedDict([
        ("chatgpt", ChatGPTAdapter()),
        ("claude", ClaudeAdapter()),
        ("manus", ManusAdapter()),
        ("kimi", KimiAdapter()),
        ("deepseek", DeepSeekAdapter()),
        ("hermes", HermesAdapter()),
        ("opencode", OpenCodeAdapter()),
        ("openclaw", OpenClawAdapter()),
    ])


def registry_summary(registry: dict[str, ConversationSourceAdapter]) -> dict[str, Any]:
    """Summary showing every adapter's HONEST state (§18)."""
    return OrderedDict([
        ("adapters", {name: a.capabilities() for name, a in registry.items()}),
        ("live_verified", sorted(
            name for name, a in registry.items() if a.state == LIVE_VERIFIED)),
        ("owner_action_required", sorted(
            name for name, a in registry.items()
            if a.state in (AUTH_REQUIRED, OWNER_ACTION_REQUIRED))),
        ("interface_ready", sorted(
            name for name, a in registry.items()
            if a.state == INTERFACE_READY)),
    ])
