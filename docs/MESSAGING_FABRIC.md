# Messaging Fabric

Multichannel messaging fabric (REQ-p27-multichannel-messaging, P27):
typed channel profiles, explicit cross-channel routing, consent, and a
provider seam over the loopback pattern.

Implementation: `comms/fabric.py`. Tests:
`tests/test_messaging_fabric.py` (28 tests, `python -m unittest`).

## What it is

The fabric join over existing transport and isolated adapters (telephony
`CallProvider`/`LoopbackCallProvider`, email tools with `PROVIDER_REQUIRED`
gating, webhook ingestion). It adds what was missing:

- **Typed channel profiles** (`ChannelProfile`) — closed kinds with existing
  adapters only (`email`, `telephone`, `webhook`); explicit capability
  booleans; consent/authorization requirements; CONFIGURED / AVAILABLE /
  UNAVAILABLE states. CONFIGURED != AVAILABLE != AUTHORIZED.
- **Explicit routing** (`route_message`) — caller-selected channel only.
  No ranking, no fallback, no broadcast. Gates checked in order: channel
  known+available, direction fit, capabilities (refused never stripped),
  consent, authorization reference.
- **Consent** (`ConsentLedger`, caller-held) — GRANTED / DENIED / UNKNOWN
  (absent). No expiry invented. Channels that require it refuse without it.
- **Provider seam** (`MessageProvider` + `LoopbackMessageProvider`) —
  loopback records dispatches in memory for tests; anything else stays
  PROVIDER_REQUIRED. No real sends exist in this unit.

## Envelope and inbound

`normalize_envelope` validates the common core (message_id, channel,
direction, sender/recipient refs, thread/reply refs, content with
attachment refs, three distinguished timestamps, provenance) and preserves
channel-specific fields under `channel_data` explicitly. `normalize_inbound`
adapts email/telephone/webhook payloads; subject stays a channel field, never
promoted to a thread; sequential messages never share a thread; content-less
events belong to the event layer and are rejected.

Identity dedupes, never content: same message_id twice is idempotent when
identical and a conflict when changed; same text across channels never
merges. Delivery states record only what the channel proves; unsupported
receipts stay UNAVAILABLE, never false.

## Boundaries

- MESSAGE != TRANSPORT; CHANNEL != TRANSPORT.
- SEND REQUEST != DELIVERY; no read/replied claims beyond provider proof.
- CHANNEL AVAILABLE != AUTHORIZED TO SEND; MESSAGE COMPOSED != SEND
  AUTHORIZED (P25 decides elsewhere; the fabric only requires the reference).
- RECIPIENT ADDRESS != VERIFIED IDENTITY; DECLARED SENDER != VERIFIED SENDER.
- CONTENT != AUTHORITY (inbound text stays data).
- CREDENTIAL REFERENCE != CREDENTIAL VALUE (refs only, never stored).
- RETRYABLE != RETRY SCHEDULED; no timers, daemons, or polling.
- No CRM, memory, notification policy, escalation, ranking, fallback,
  broadcast, vector search, or model calls.
