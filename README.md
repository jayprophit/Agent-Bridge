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
