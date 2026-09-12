# v0.8 Security / Privacy Summary (convergence, verified)

## Scans: PASS

- Secret scan (`tests.test_secret_hygiene`): zero hardcoded API keys,
  passwords, tokens, cookies, private keys or pairing secrets in tracked
  source; zero committed raw captures; zero `.bridge` runtime state.
- Personal paths: zero absolute personal paths in shipped `.py`
  (configs/CLI default to `AGENT_BRIDGE_ROOT` env or `.`).
- Portability (`tests.test_repo_portability`): old-tree references
  fixed (bridge configs, cli.py, run_gate/owner_e2e); remaining
  occurrences are HISTORICAL_DOC release evidence only.

## .gitignore: PASS

Covers `__pycache__/`, venvs, `.env`, `.bridge/`, logs, temp TLS
(`*.pem/*.key`), temp test workspaces (`sandbox_*/`, `ab_*`),
raw captures (`*.wav/*.mp4/...`), mic/audio capture, `secrets/`.

## License: PASS

No MIT/Apache/GPL/BSD/Unlicense file added; README grants no
open-source rights (owner decision pending).

## Privacy gates: PASS (tested)

- Microphone/camera/screen: explicit permission required; voice
  recording consent-gated; guided capture requires camera permission.
- Raw capture lifecycle: EPHEMERAL_RAW_CAPTURE default,
  DELETE_AFTER_DERIVATION proven by test (files gone); explicit retain
  is audited, never silent; nothing uploaded by default; avatar data
  local unless the user selects a destination.
- Email send: provider + authorization required, owner-only, no
  credentials in tree. Telephony: default MANUAL_ANSWER, recording
  needs consent, Do-Not-Disturb rejects. PSTN never auto-dialed.
- Unknown tools rejected, never invented; pairing HMAC + replay
  protection (v0.7 transports); audit redaction; emergency stop honors
  delegation; 127.0.0.1 bind default.

**Status: PASS**
