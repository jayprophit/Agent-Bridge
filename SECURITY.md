# Agent Bridge — Security Model (v0.8.1)

## Defaults

- Localhost bind (127.0.0.1); non-loopback plaintext refused; TLS 1.2+ where used.
- Optional bearer token; per-IP rate limiting; request size caps; no CORS by default.
- Sandboxed workspace roots; path traversal refused; `.bridge` audit files model-protected.
- Approval levels: AUTO_SAFE, ASK_RISKY, ASK_ALL_WRITES, READ_ONLY (+ explicit OWNER_FULL_ACCESS with dual authorization).
- Unknown/invented tools rejected; adapters without registration never execute.
- Audit log redacts secrets; emergency stop honored across delegation.
- Pairing: single-use expiring tokens, HMAC challenge, replay window; remote owner scope disabled by default.

## Data

- Local-first: artifacts stay in the workspace; no central warehouse.
- Ephemeral captures (camera/mic) deleted after derivation by default.
- No credentials in tree (enforced by tests/test_secret_hygiene.py).

## Reporting issues

No public contact is published in this repository. Report through the
owner's private channel. Do not file public issues containing private data.
