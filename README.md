# Agent-Bridge
A framework for connecting AI agents, models, tools and local resources through a unified runtime.

## Layout

- Top-level `.py` modules + packages (`agent/`, `tools/`, `resources/`, …) are the runtime.
- `scripts/` — acceptance/evidence drivers (`python scripts/run_v08_acceptance.py`).
- `docs/releases/v0.8/` — human release reports (start with `V08_FINAL_VERIFICATION_REPORT.md`).
- `reports/v0.8/` — machine-readable evidence (`.json`).
- `docs/requirements/` — problem/solution registry + 450-item traceability.
- `docs/architecture/` — topical design docs. `config/` — example configs.

## Quick start

```powershell
python -m unittest discover -s tests -p "test_*.py"
python scripts/run_v08_acceptance.py --skip-regression
```

See `docs/REPRODUCIBLE_SETUP.md` for the full clean-machine path.

## What it is / is not

Agent Bridge is a local-first runtime that lets small AI models act as
tool-using agents: bridge loop (`bridge.py`) → policy/approvals →
workspace-scoped executor → verification. It is NOT a model, NOT an IDE,
NOT a cloud service, and NOT a robot controller.

## Architecture

Flat top-level runtime modules (`bridge`, `runtime`, `executor`,
`policy`, providers under `models/providers/`, tools under
`tools/cat_*.py`, resources, voice, avatar, nodes, ides) — see
`docs/adr/ADR-001-flat-package-layout.md`. Tests live in `tests/`
(ADR-002). Release evidence: `docs/releases/`, `reports/`.
Schemas: `docs/*.json`. Configs: `bridge_config.json`, `config/`.

## Local data policy

Everything local/runtime/removable defaults under `local/` (acceptance,
sessions, logs, cache, workspaces, …), resolved from explicit path >
`AGENT_BRIDGE_LOCAL`/`AGENT_BRIDGE_ROOT` env > repository root
(`localdirs.py`). `local/` is git-ignored; release evidence stays in
`docs/`/`reports/`.

## Extension points

Providers (`models/providers/`), tool catalogs (`tools/cat_*.py` +
`ToolRegistry`), IDE embedding (`ides/embedding.py`), HTTP `/v1`
(`service.py`) and SDK (`client.py`). Examples: `examples/`.

## Security / versions

Model in `SECURITY.md`. Product line in `CHANGELOG.md` (runtime 0.6 /
API v1 independent of product releases). No open-source license granted.
