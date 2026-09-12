# Integrations

External applications connect through stable surfaces only:

- HTTP `/v1` API on 127.0.0.1 (see `service.py`, `docs/api_schema.json`).
- Python SDK/client (`client.py`), same routes.
- IDE embedding contract (`ides/embedding.py`).
- Provider adapters (`models/providers/`) and tool catalogs
  (`tools/cat_*.py` + `ToolRegistry`).

Never import `executor`, `policy` or `protocol` internals from outside;
a static test (`tests/test_rerun_gui_genesis.py`) enforces this boundary.
