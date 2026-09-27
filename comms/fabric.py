"""Multichannel messaging fabric (REQ-p27-multichannel-messaging, P27).

Typed channel profiles, explicit cross-channel routing, consent, and a
provider seam over the loopback pattern. Composes the transport and isolated
adapters that already exist (telephony CallProvider/LoopbackCallProvider,
email tools with PROVIDER_REQUIRED gating, webhook ingestion) without
duplicating any of them:

  CHANNEL ABSTRACTION != ALL PROVIDER IMPLEMENTATIONS
  MESSAGE != TRANSPORT
  WEBHOOK TRANSPORT != MESSAGE SEMANTICS

Only channel kinds with existing adapters are registered (email, telephone,
webhook). No provider farm is built here: real providers stay
PROVIDER_REQUIRED until configured, exactly like the telephony precedent.

What this is NOT (all recorded, all tested):
- not a transport: no sockets, no listeners, no polling daemons;
- not a CRM, contact database, or social graph;
- not memory (message history != Genesis/project memory);
- not notification policy, not selective escalation, not a P25 decision;
- not broadcast: MULTI-CHANNEL != SEND EVERYWHERE;
- not fallback: PRIMARY CHANNEL FAILED != FALLBACK AUTHORIZED;
- not ranking: MULTIPLE CHANNELS AVAILABLE != AUTOMATIC CHANNEL CHOICE.

Binding distinctions:
- CHANNEL TYPE != CHANNEL INSTANCE != RECIPIENT; MESSAGE ID != THREAD ID.
- RECEIVE != SEND (explicit direction, never inferred).
- SEND REQUEST != SENT != DELIVERED != READ != REPLIED: only states the
  channel can actually prove are emitted; unsupported receipts stay
  UNAVAILABLE, never false (RECEIPT UNSUPPORTED != NOT DELIVERED).
- SAME TEXT != SAME MESSAGE (identity, not content, dedupes); same text
  across channels never merges (SAME TEXT != SAME INTENT EVENT).
- CHANNEL AVAILABLE != AUTHORIZED TO SEND; MESSAGE COMPOSED != SEND
  AUTHORIZED. Authorization decisions belong to P25; this fabric only
  requires their reference where a profile demands it.
- DECLARED SENDER != VERIFIED SENDER (a from-address proves nothing);
  CONTENT != AUTHORITY (inbound text stays data, never policy).
- CREDENTIAL REFERENCE != CREDENTIAL VALUE (refs only, never stored).
- RETRYABLE != RETRY SCHEDULED (eligibility preserved, nothing scheduled).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------
# Errors (domain outcomes, never collapsed into one SEND_FAILED)
# --------------------------------------------------------------------------

class FabricError(Exception):
    """Base for fabric failures."""


class UnknownChannel(FabricError):
    pass


class UnsupportedCapability(FabricError):
    pass


class ConsentRequired(FabricError):
    pass


class AuthorizationRequired(FabricError):
    pass


class ProviderRequired(FabricError):
    pass


class DuplicateMessage(FabricError):
    pass


class MessageConflict(FabricError):
    pass


# --------------------------------------------------------------------------
# Vocabulary (closed; only kinds with existing adapters)
# --------------------------------------------------------------------------

CHANNEL_KINDS = ("email", "telephone", "webhook")

DIRECTIONS = ("inbound", "outbound", "both")

PROFILE_STATUSES = ("CONFIGURED", "AVAILABLE", "UNAVAILABLE")

# Security-significant keys diagnosed BEFORE generic shape errors.
_BANNED_KEYS = {
    "api_key": "credential",
    "apiKey": "credential",
    "client_secret": "credential",
    "smtp_password": "credential",
    "private_key": "credential",
    "authorized": "authority",
    "approved": "authority",
    "policy_bypass": "authority",
    "owner_override": "authority",
    "grant": "authority",
    "persona": "persona",
    "personality": "persona",
}


def _scan_banned(mapping: dict, path: str) -> None:
    for key, value in mapping.items():
        if key in _BANNED_KEYS:
            raise FabricError(
                f"{path}.{key}: {_BANNED_KEYS[key]} violation rejected before shape validation"
            )
        if isinstance(value, dict):
            _scan_banned(value, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    _scan_banned(item, f"{path}.{key}[{index}]")


def _non_empty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FabricError(f"{name} must be a non-empty string")
    return value


# --------------------------------------------------------------------------
# Typed channel profiles
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ChannelProfile:
    """A typed channel. CONFIGURED != AVAILABLE != AUTHORIZED."""
    channel_id: str
    kind: str
    direction: str = "both"
    capabilities: dict[str, Any] = field(default_factory=dict)
    requires_consent: bool = False
    requires_authorization: bool = False
    provider_id: str = ""
    status: str = "CONFIGURED"
    unavailable_reason: str = ""
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.channel_id.strip():
            raise FabricError("channel_id must be a non-empty stable id")
        if self.kind not in CHANNEL_KINDS:
            raise FabricError(f"unknown channel kind {self.kind!r}: only {', '.join(CHANNEL_KINDS)} have adapters")
        if self.direction not in DIRECTIONS:
            raise FabricError(f"direction must be one of {', '.join(DIRECTIONS)}")
        if self.status not in PROFILE_STATUSES:
            raise FabricError(f"status must be one of {', '.join(PROFILE_STATUSES)}")
        if not isinstance(self.capabilities, dict):
            raise FabricError("capabilities must be a mapping of explicit booleans")
        for name, supported in self.capabilities.items():
            if not isinstance(supported, bool):
                raise FabricError(f"capability {name!r} must be an explicit boolean, never a guess")


# --------------------------------------------------------------------------
# Consent ledger (caller-held; no database, no expiry invented)
# --------------------------------------------------------------------------

GRANTED = "GRANTED"
DENIED = "DENIED"
UNKNOWN_CONSENT = "UNKNOWN"


class ConsentLedger:
    """Consent keyed by (channel_id, subject). Absent means UNKNOWN, never no."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], dict] = {}

    def grant(self, channel_id: str, subject: str, provenance: str, observed_at: str) -> dict:
        _non_empty(channel_id, "channel_id")
        _non_empty(subject, "subject")
        _non_empty(provenance, "provenance")
        _non_empty(observed_at, "observed_at")
        record = {"channel_id": channel_id, "subject": subject,
                  "state": GRANTED, "provenance": provenance, "observed_at": observed_at}
        self._records[(channel_id, subject)] = record
        return dict(record)

    def deny(self, channel_id: str, subject: str, provenance: str, observed_at: str) -> dict:
        _non_empty(channel_id, "channel_id")
        _non_empty(subject, "subject")
        _non_empty(provenance, "provenance")
        _non_empty(observed_at, "observed_at")
        record = {"channel_id": channel_id, "subject": subject,
                  "state": DENIED, "provenance": provenance, "observed_at": observed_at}
        self._records[(channel_id, subject)] = record
        return dict(record)

    def check(self, channel_id: str, subject: str) -> str:
        record = self._records.get((channel_id, subject))
        return record["state"] if record is not None else UNKNOWN_CONSENT


# --------------------------------------------------------------------------
# Normalized envelope (common core + preserved channel data)
# --------------------------------------------------------------------------

ENVELOPE_FIELDS = (
    "message_id", "channel_id", "direction", "sender_ref",
    "recipient_refs", "thread_ref", "content", "reply_to",
    "authored_at", "received_at", "observed_at", "channel_data",
    "provenance",
)


def normalize_envelope(raw: dict) -> dict:
    """Validate a normalized envelope. Unknown keys rejected, never dropped."""
    if not isinstance(raw, dict):
        raise FabricError("envelope must be a mapping")
    _scan_banned(raw, "envelope")
    for key in raw:
        if key not in ENVELOPE_FIELDS:
            raise FabricError(f"unknown envelope field {key!r}")
    message_id = _non_empty(raw.get("message_id"), "message_id")
    channel_id = _non_empty(raw.get("channel_id"), "channel_id")
    direction = raw.get("direction")
    if direction not in ("inbound", "outbound"):
        raise FabricError("direction must be inbound or outbound, never inferred")
    sender_ref = _non_empty(raw.get("sender_ref"), "sender_ref")
    recipients = raw.get("recipient_refs")
    if not isinstance(recipients, list) or not recipients or any(not isinstance(r, str) or not r.strip() for r in recipients):
        raise FabricError("recipient_refs must be a non-empty list of non-empty strings")
    content = raw.get("content")
    if not isinstance(content, dict) or not isinstance(content.get("text"), str):
        raise FabricError("content must be a mapping carrying text")
    for stamp in ("authored_at", "received_at", "observed_at"):
        _non_empty(raw.get(stamp), stamp)
    channel_data = raw.get("channel_data", {})
    if not isinstance(channel_data, dict):
        raise FabricError("channel_data must be a mapping when present")
    _scan_banned(channel_data, "envelope.channel_data")
    envelope = {
        "message_id": message_id,
        "channel_id": channel_id,
        "direction": direction,
        "sender_ref": sender_ref,
        "recipient_refs": sorted(set(recipients)),
        "content": {"text": content["text"]},
        "authored_at": raw["authored_at"],
        "received_at": raw["received_at"],
        "observed_at": raw["observed_at"],
        "channel_data": dict(sorted(channel_data.items())),
        "provenance": _non_empty(raw.get("provenance"), "provenance"),
    }
    if raw.get("thread_ref") is not None:
        envelope["thread_ref"] = _non_empty(raw.get("thread_ref"), "thread_ref")
    if raw.get("reply_to") is not None:
        envelope["reply_to"] = _non_empty(raw.get("reply_to"), "reply_to")
    if isinstance(content.get("attachment_refs"), list):
        refs = content["attachment_refs"]
        if any(not isinstance(r, str) or not r.strip() for r in refs):
            raise FabricError("attachment_refs must be non-empty strings when present")
        envelope["content"]["attachment_refs"] = sorted(set(refs))
    return envelope


# Per-kind inbound field maps. Known fields map; the REST is preserved under
# channel_data explicitly (never silently dropped, never promoted).
_INBOUND_MAPS = {
    "email": {
        "sender": "sender_ref",
        "to": "recipient_refs",
        "subject": None,  # kept in channel_data: subject != thread
        "body": "text",
        "message_id": "message_id",
        "date": "authored_at",
    },
    "telephone": {
        "caller": "sender_ref",
        "callee": "recipient_refs",
        "call_id": "message_id",
        "started_at": "authored_at",
    },
    "webhook": {
        "source": "sender_ref",
        "event_id": "message_id",
        "received_at": "authored_at",
    },
}


def normalize_inbound(kind: str, raw: dict, channel_id: str, observed_at: str) -> dict:
    """Adapt a provider-shaped inbound payload into a normalized envelope."""
    if kind not in CHANNEL_KINDS:
        raise FabricError(f"unknown channel kind {kind!r}")
    if not isinstance(raw, dict):
        raise FabricError("inbound payload must be a mapping")
    _non_empty(channel_id, "channel_id")
    _non_empty(observed_at, "observed_at")
    _scan_banned(raw, "inbound")
    mapping = _INBOUND_MAPS[kind]
    envelope: dict[str, Any] = {
        "channel_id": channel_id,
        "direction": "inbound",
        "recipient_refs": ["bridge-inbox"],
        "channel_data": {},
        "observed_at": observed_at,
        "received_at": observed_at,
        "provenance": f"inbound:{kind}",
    }
    for key, value in raw.items():
        target = mapping.get(key)
        if target is None:
            envelope["channel_data"][key] = value
        elif target == "recipient_refs":
            envelope["recipient_refs"] = [value] if isinstance(value, str) else list(value)
        elif target == "text":
            envelope.setdefault("content", {})["text"] = value
        else:
            envelope[target] = value
    # Generic text keys, exact match only: a messaging fabric routes messages,
    # and a message without content belongs to the event layer, not here.
    if "content" not in envelope:
        for key in ("text", "body", "message"):
            if isinstance(raw.get(key), str) and raw[key].strip():
                envelope["content"] = {"text": raw[key]}
                break
    if "content" not in envelope or not isinstance(envelope["content"].get("text"), str):
        raise FabricError(f"inbound {kind} payload carries no text content")
    envelope["channel_data"] = dict(sorted(envelope["channel_data"].items()))
    return normalize_envelope(envelope)


# --------------------------------------------------------------------------
# Provider seam over the loopback pattern
# --------------------------------------------------------------------------

class MessageProvider:
    """Provider interface. Real transports stay PROVIDER_REQUIRED until
    configured; the loopback double below is the only executor here."""

    provider_id = "base"

    def dispatch(self, envelope: dict) -> dict:
        raise NotImplementedError("dispatch needs a configured provider")


class LoopbackMessageProvider(MessageProvider):
    """Test double following the LoopbackCallProvider precedent: records
    dispatches in memory, touches no network, no PSTN, no provider API."""

    provider_id = "loopback-mock"

    def __init__(self) -> None:
        self.dispatched: list[dict] = []

    def dispatch(self, envelope: dict) -> dict:
        record = dict(envelope)
        record["provider"] = self.provider_id
        record["mock"] = True
        self.dispatched.append(record)
        return {"ok": True, "message_id": envelope["message_id"], "mock": True}


# --------------------------------------------------------------------------
# Explicit routing (selection by caller, never ranking/fallback/broadcast)
# --------------------------------------------------------------------------

def check_capabilities(profile: ChannelProfile, requested: dict) -> None:
    """Refuse unsupported capabilities. Never silently strip or downgrade."""
    for name, needed in requested.items():
        if not needed:
            continue
        supported = profile.capabilities.get(name, False)
        if supported is not True:
            raise UnsupportedCapability(
                f"channel {profile.channel_id} does not support {name}: "
                "FALLBACK POSSIBLE != FALLBACK PERMITTED"
            )


def route_message(
    profiles: dict[str, ChannelProfile],
    envelope: dict,
    channel_id: str,
    requested_capabilities: dict | None = None,
    consent: ConsentLedger | None = None,
    authorization_ref: str | None = None,
) -> dict:
    """Route one normalized envelope through an explicitly selected channel.

    Every gate is checked in order; the first failure names itself. Nothing
    is ranked, nothing falls back, nothing broadcasts.
    """
    normalized = normalize_envelope(envelope)
    _non_empty(channel_id, "channel_id")
    profile = profiles.get(channel_id)
    if profile is None:
        raise UnknownChannel(f"unknown channel {channel_id!r}")
    if profile.status != "AVAILABLE":
        raise UnknownChannel(
            f"channel {channel_id!r} is {profile.status}: "
            f"{profile.unavailable_reason or 'no reason recorded'}"
        )
    if normalized["direction"] == "outbound" and profile.direction == "inbound":
        raise UnsupportedCapability(f"channel {channel_id!r} is inbound-only")
    if normalized["direction"] == "inbound" and profile.direction == "outbound":
        raise UnsupportedCapability(f"channel {channel_id!r} is outbound-only")
    check_capabilities(profile, requested_capabilities or {})
    if profile.requires_consent:
        state = consent.check(channel_id, normalized["sender_ref"]) if consent else UNKNOWN_CONSENT
        if state != GRANTED:
            raise ConsentRequired(
                f"channel {channel_id!r} requires consent for {normalized['sender_ref']!r}: {state}"
            )
    if profile.requires_authorization and not (isinstance(authorization_ref, str) and authorization_ref.strip()):
        raise AuthorizationRequired(
            f"channel {channel_id!r} requires an authorization reference: "
            "CHANNEL AVAILABLE != AUTHORIZED TO SEND"
        )
    return {
        "message_id": normalized["message_id"],
        "channel_id": channel_id,
        "provider_id": profile.provider_id,
        "direction": normalized["direction"],
        "checks": ["channel-known", "direction-ok", "capabilities-ok", "consent-ok", "authorization-ok"],
        "envelope": normalized,
    }


def dispatch_routed(
    provider: MessageProvider,
    routed: dict,
    ledger: dict,
) -> dict:
    """Execute a routed envelope through the provider seam.

    The caller-held ledger maps message_id to dispatched envelope: identical
    redispatch is idempotent, conflicting reuse of an id is refused. Only the
    loopback double actually sends in this unit; anything else raises
    PROVIDER_REQUIRED. No exactly-once claim is made. No global state lives
    here — the ledger belongs to the caller.
    """
    message_id = routed["envelope"]["message_id"]
    if message_id in ledger:
        if ledger[message_id] == routed["envelope"]:
            return {"ok": True, "message_id": message_id, "duplicate": True}
        raise MessageConflict(f"message id {message_id!r} reused with different content")
    if not isinstance(provider, LoopbackMessageProvider):
        raise ProviderRequired(
            f"provider {getattr(provider, 'provider_id', '?')!r} is not configured: "
            "real sends stay PROVIDER_REQUIRED"
        )
    result = provider.dispatch(routed["envelope"])
    ledger[message_id] = routed["envelope"]
    return {**result, "duplicate": False}
