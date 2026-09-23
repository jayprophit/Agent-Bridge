# Webhook Trigger Ingestion (REQ-webhook-triggers, P21)

External webhook/event ingestion as future P19 trigger sources with
trust/signature policy. The P19 core trigger contract already handles
trusted internal events; this module is the ingestion boundary that turns
an untrusted inbound webhook into a trusted internal event — or rejects
it. No HTTP server lives here (opening a listener is owner-authorized
runtime work); the caller transports bytes, this module verifies.

## Rules (`webhook_triggers.py`)

- **Known sources only**: unknown `source_id` rejected, no open ingestion.
- **HMAC-SHA256 signatures** over the raw body (`X-Signature-Sha256`,
  case-insensitive header). Secrets arrive via a caller-provided resolver
  keyed by vault ref; the module never stores, logs, or echoes secrets
  (tested — failure messages and module source contain no secret).
- **Freshness + dedup**: timestamps outside the per-source window (past or
  future) rejected; seen event ids rejected (bounded LRU set).
- **Size + shape**: per-source byte cap; JSON object bodies only.
- **Allowlisted payloads**: only `allowed_payload_fields` pass into the
  normalized event — internal/extra fields dropped, never wholesale blobs.
- **P19-shaped output**: `NormalizedEvent` mirrors `AetheriusEvent`
  (event_id/type, source `webhook:<id>`, occurred/received ms, payload,
  `webhook:<id>:verified` provenance) so verified webhooks feed
  `dispatchEvent` directly.

## Tests

`tests/test_webhook_triggers.py` — 8 tests: valid normalization, header
case-insensitivity, unknown source, bad/missing/tampered signatures,
stale/future/duplicate, size/type/shape guards, unsigned-allowed policy,
secret non-echo.
