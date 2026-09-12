# Remote Security (v0.7)

## Defense in depth

Source policy → delegation → target receives → target policy → target tool
authorization → execution. Source authorization alone is never sufficient.

## Rules

- No arbitrary remote shell; no insecure plaintext LAN control surface.
- Plain HTTP remote control is denied by default (`REMOTE_PLAINTEXT_DENIED`).
- HTTPS requires real certs (`CONFIGURATION_REQUIRED` otherwise, TLS 1.2+).
- Pairing tokens: `secrets`, 300 s TTL, single use, revocable, hashed at rest.
- Replay: nonce + timestamp + request ID with 300 s window.
- Cancellation propagates source → transport → target execution.
- Emergency stop on the target rejects new delegations and cancels running ones;
  a remote source can never disable the target's emergency stop.
- Heartbeats track liveness/latency; repeated failures mark nodes OFFLINE while
  retaining metadata, trust, and benchmark history.
- Audit records source/target, transport, security mode, protocol version,
  pairing/trust state, IDs, privacy mode, timing, verification, and errors —
  never secrets.
- Artifacts travel as references with origin and verification state; artifacts
  from LIMITED/UNTRUSTED nodes are never implicitly trusted.
