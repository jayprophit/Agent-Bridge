"""Webhook and external event trigger sources (P21, REQ-webhook-triggers).

External webhook/event ingestion as future P19 trigger sources with
trust/signature policy. The P19 core trigger contract already supports
trusted internal events; this module is the ingestion boundary that turns
an untrusted inbound webhook into a trusted internal event — or rejects
it. No HTTP server lives here (opening a listener is owner-authorized
runtime work); the caller transports bytes, this module verifies.

Boundaries:
- Unknown sources are rejected. No open ingestion.
- Signatures are HMAC-SHA256 over the raw body. Secrets arrive via a
  caller-provided resolver keyed by vault ref; this module never stores,
  logs, or echoes secrets (tested).
- Freshness (max age) + seen event-id dedup (bounded) block replays.
- Size limits bound memory. Payloads are allowlisted per source: only
  matched fields pass into the normalized event, never wholesale blobs.
- Output mirrors the P19 AetheriusEvent shape so a verified webhook can
  feed dispatchEvent directly.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------

class WebhookError(Exception):
    """Base for ingestion failures. Messages never contain secrets."""


class UnknownSource(WebhookError):
    pass


class BadSignature(WebhookError):
    pass


class StaleEvent(WebhookError):
    pass


class DuplicateEvent(WebhookError):
    pass


class OversizeEvent(WebhookError):
    pass


class DisallowedEventType(WebhookError):
    pass


class MalformedEvent(WebhookError):
    pass


# --------------------------------------------------------------------------
# Trust policy
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class SourcePolicy:
    source_id: str
    allowed_event_types: tuple[str, ...]
    require_signature: bool = True
    secret_ref: str = ""
    max_age_s: int = 300
    max_bytes: int = 65536
    allowed_payload_fields: tuple[str, ...] = ()


SecretResolver = Callable[[str], bytes]


@dataclass(frozen=True)
class NormalizedEvent:
    event_id: str
    event_type: str
    source: str
    occurred_at: int
    received_at: int
    payload: dict[str, Any]
    provenance: str


class WebhookIngestor:
    """Verifies inbound webhooks against per-source trust policy."""

    def __init__(
        self,
        policies: list[SourcePolicy],
        resolve_secret: SecretResolver | None = None,
        now_ms: Callable[[], int] | None = None,
        max_seen: int = 10000,
    ):
        self._policies = {p.source_id: p for p in policies}
        self._resolve_secret = resolve_secret or (lambda ref: (_ for _ in ()).throw(
            WebhookError(f"no secret resolver for vault ref {ref}")))
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._max_seen = max_seen

    def sources(self) -> list[str]:
        return sorted(self._policies)

    def ingest(
        self,
        source_id: str,
        body: bytes,
        headers: dict[str, str],
        event_id: str,
        event_type: str,
        occurred_at_ms: int,
    ) -> NormalizedEvent:
        policy = self._policies.get(source_id)
        if policy is None:
            raise UnknownSource(f"unknown webhook source {source_id}")
        if len(body) > policy.max_bytes:
            raise OversizeEvent(f"webhook body {len(body)} exceeds {policy.max_bytes}")
        if event_type not in policy.allowed_event_types:
            raise DisallowedEventType(f"{source_id} may not emit {event_type}")
        now = self._now_ms()
        if occurred_at_ms > now + 60_000:
            raise StaleEvent("webhook timestamp is in the future")
        if now - occurred_at_ms > policy.max_age_s * 1000:
            raise StaleEvent("webhook is older than the source freshness window")
        if event_id in self._seen:
            raise DuplicateEvent(f"webhook {event_id} already ingested")
        if policy.require_signature:
            self._verify_signature(policy, body, headers)
        try:
            parsed = json.loads(body.decode("utf-8")) if body.strip() else {}
        except (UnicodeDecodeError, ValueError) as exc:
            raise MalformedEvent(f"webhook body is not JSON: {exc}") from None
        if not isinstance(parsed, dict):
            raise MalformedEvent("webhook JSON body must be an object")
        payload = {k: parsed[k] for k in policy.allowed_payload_fields if k in parsed}
        self._seen[event_id] = None
        while len(self._seen) > self._max_seen:
            self._seen.popitem(last=False)
        return NormalizedEvent(
            event_id=event_id,
            event_type=event_type,
            source=f"webhook:{source_id}",
            occurred_at=occurred_at_ms,
            received_at=now,
            payload=payload,
            provenance=f"webhook:{source_id}:verified",
        )

    def _verify_signature(self, policy: SourcePolicy, body: bytes, headers: dict[str, str]) -> None:
        lowered = {k.lower(): v for k, v in headers.items()}
        presented = lowered.get("x-signature-sha256", "")
        if not presented:
            raise BadSignature("missing X-Signature-Sha256")
        if not policy.secret_ref:
            raise BadSignature("source requires a signature but has no secret ref")
        secret = self._resolve_secret(policy.secret_ref)
        if not secret:
            raise BadSignature("secret resolver returned empty secret")
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, presented.strip().lower()):
            raise BadSignature("signature mismatch")


def sign_body(secret: bytes, body: bytes) -> str:
    """Test/sender helper: compute the expected header value."""
    return hmac.new(secret, body, hashlib.sha256).hexdigest()
