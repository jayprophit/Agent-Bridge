# Pairing and Trust (v0.7)

## Core rules

- Discovery does NOT imply trust. Unknown nodes default to `UNTRUSTED_NODE`.
- Pairing does NOT automatically grant `TRUSTED_NODE`. After owner approval
  the default is the conservative `LIMITED_NODE` unless the owner selects otherwise.
- Authentication, pairing, and trust are separate:
  a node can be authenticated-but-LIMITED, or paired-but-denied private data.
- Pairing never grants `OWNER_FULL_ACCESS`. Remote owner operations need an
  explicit remote-owner policy (conservative in v0.7).

## Trust levels

`OWNER_NODE` (self) > `TRUSTED_NODE` > `LIMITED_NODE` > `UNTRUSTED_NODE`.

## Pairing state machine

`UNPAIRED → PAIRING_REQUESTED → AWAITING_OWNER_APPROVAL → CHALLENGE_SENT →
CHALLENGE_VERIFIED → PAIRED`, with `REJECTED`, `REVOKED`, `EXPIRED` exits.
A node is never marked paired merely for answering HTTP.

## Challenge/response

- One-time token from `secrets.token_urlsafe(32)` (never `random`), 300 s TTL,
  single use, bound to the attempt; only its SHA-256 hash is stored.
- Challenge `secrets.token_hex(16)`; response is
  `HMAC-SHA256(token, attempt_id:challenge)` verified with `compare_digest`.
- HMAC is message authentication only, not transport confidentiality (that is TLS).

## Replay protection

Envelopes carry `nonce` + `timestamp` + `delegation_id`. Duplicates, skew
beyond 300 s, or reused IDs are rejected with `REPLAY_REJECTED`.

## Credential storage

- `CredentialStore` abstraction; `DevFileCredentialStore` is development-only
  (requires explicit flag, 0600 permissions).
- `WindowsCredentialManagerStore` is INTERFACE_ONLY in v0.7.
- Secrets never appear in logs, benchmark reports, prompts, or progress files
  (`audit_event` redacts token/challenge/response/secret/key fields).
