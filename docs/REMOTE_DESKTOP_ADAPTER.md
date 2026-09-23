# Governed Remote-Desktop Adapter (REQ-p21-remote-desktop, P21)

VNC-class remote desktop reach with authenticated transport, scoped
clipboard/file transfer and a saved-endpoint registry using vault
references. Reference: CrabFleet remote-desktop v0.3.1 (MIT, STUDY_ONLY).
CrabFleet is a remote-desktop tool, not a fleet controller — no fleet
semantics exist here.

## Rules (`remote_desktop.py`)

- **Vault references only**: endpoints carry `{ref: <pointer>}`; raw
  password/secret/token/private-key fields are rejected at registration.
  The registry never sees raw credentials.
- **Authenticated transport**: `auth_method` is allowlisted
  (`password-vault-ref`, `key-vault-ref`, `loopback-sim`); anything else —
  including unauthenticated — is rejected.
- **Scoped transfer**: per-session `TransferScope` (clipboard in/out, file
  upload/download, byte budget). Out-of-scope direction or budget breach
  fails closed.
- **Session lifecycle**: DEFINED→AUTH→CONNECTED→CLOSED, declared
  transitions only.
- **No live backend here**: `LoopbackBackend` (labeled simulated) replays
  declared frame descriptors for tests — metadata only, never pixels, no
  network, no capture, no input. `VncBackend` is declared-unavailable with
  a reason. Real VNC reach is owner-authorized runtime work.

## Tests

`tests/test_remote_desktop.py` — 10 tests: vault-ref discipline, raw
credential rejection, endpoint shape/auth validation, registry dedup,
lifecycle, declared-frame replay, foreign-auth rejection, scope + budget
enforcement, no-authority surface, VNC unavailability.
