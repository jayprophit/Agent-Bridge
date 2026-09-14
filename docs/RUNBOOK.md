# Agent Bridge Runbook (Phase 2)

## Start the runtime service

```powershell
python cli.py --root <workspace-root> --approval AUTO_SAFE serve --host 127.0.0.1 --port 8471
```

Verify: `GET http://127.0.0.1:8471/health` → 200. Aggregate IDE view:
`GET /v1/runtime`. Full route list: `GET /v1/schema`
(also snapshotted in `docs/api_schema.json`).

## Start the IDE app (prototype shell)

```powershell
cd <IDE-Workspace>\workspace\app
npm.cmd install
npm.cmd run build   # tsc + vite; must pass before serving
```

The app polls the bridge at `http://127.0.0.1:8471` every 5s
(override for tests: `window.__BRIDGE_BASE__`). With no backend it
shows honest `backend: disconnected` labels — never fake live data.

## Health checks / diagnostics

- Service: `/health`, `/v1/selfcheck`, `/v1/diagnostics`.
- Machine: `python -c "from capability_api import machine_capabilities"`.
- Models: `ollama list` + `local/model-audit/records.json` for the
  audited default set (granite3.3:2b, qwen2.5-coder:3b, nomic-embed-text).
- Tests: `python -m unittest discover -s tests -p "test_*.py"`
  (slow, ~12 min; use halves `test_[a-m]*` / `test_[n-z]*` during work).

## Configuration

- OpenCode unattended policy lives outside this repo:
  `%USERPROFILE%\.config\opencode\opencode.jsonc` (ordinary tools
  allow-listed; destructive commands denied; restart + `--auto` to apply).
- Agent Bridge owner profiles: `--profile` on `cli.py`
  (default SAFE_EXPLORATION; OWNER_FULL_ACCESS requires explicit flag).
- Never commit `.bridge/`, `local/`, `.env`, credentials, or model blobs.

## Known limitations

- F:\ external disk = hardware failure; use `E:\F-Drive-Backup`.
- IDE terminal surface is planned, not implemented (no remote exec
  endpoint by design; see final report).
- `qwen3:latest` (8B) is too slow locally (~1.4 tok/s); retirement
  candidate awaiting owner approval (nothing auto-deleted).
