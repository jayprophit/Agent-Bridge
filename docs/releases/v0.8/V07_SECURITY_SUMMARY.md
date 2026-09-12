# v0.7 Security Summary (freeze)

## Verified by regression tests (all PASS)

- Path traversal refused (read/write/stat outside workspace; absolute-path
  containment) — `test_security_regression.py::PathTraversalTests`.
- Invented tools rejected (`UNKNOWN_TOOL`); records without adapters never
  execute (`NO_ADAPTER`); owner-only tools denied without owner profile
  (`PROFILE_DENIED`); unknown plugin adapters raise `KeyError`.
- Audit log has no exfiltration route (404) and all secret fields redacted.
- Pairing: single-use expiring tokens, HMAC challenge via `compare_digest`,
  bad/expired token rejection, revocation.
- Replay: nonce + timestamp + request-ID window enforced.
- Trust: untrusted and revoked nodes excluded over real HTTP.
- Privacy checked before serialization (`PRIVACY_DENIED`).
- Plaintext to non-loopback refused pre-send (`REMOTE_PLAINTEXT_DENIED`).
- Protocol mismatch rejected (`PROTOCOL_VERSION_UNSUPPORTED`).
- Unknown tools rejected (`CAPABILITY_UNAVAILABLE`); executor-deny path
  returns `TOOL_DENIED` (target-side authorization).
- Remote owner scope denied by default (`REMOTE_OWNER_POLICY_DENIED`);
  explicit grants allow only configured scopes.
- Emergency stop rejects new delegations remotely; cancellation propagates
  source → transport → target; large results truncated (2000 chars).

## Architecture guarantees

- No remote shell; no plaintext LAN control surface; 127.0.0.1 default bind.
- TLS 1.2+ with real certs; self-signed dev CAs only via explicit cafile
  (no verify-skipping flag exists).
- Pairing ≠ trust ≠ authorization; pairing never grants OWNER_FULL_ACCESS.
- mTLS: SUPPORTED_CONFIGURATION / INTERFACE_ONLY (server does not request
  client certs by default — asserted by test).

## Bugs found and fixed by this audit

- `tools/cat_sys.py`: missing `INSTALL` import (crashed `package_records()`).
- `tools/router.py`: missing `ADMIN` import (crashed any routed call touching
  the admin gate, e.g. adapter-less records).
