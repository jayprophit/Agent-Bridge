# v0.8 Root Layout Audit (final correction pass)

## Principle

Root holds only what is genuinely useful at root: README, .gitignore,
live critical config (bridge_config.json), and the flat top-level Python
runtime modules the architecture imports (bridge, runtime, executor, …).
Everything else lives in docs/, reports/, config/, scripts/, schemas.

## Before / after

- Root files before: 149 (58 md, 37 json, 52 py, 2 dotfiles).
- Root files after: 45 (README.md, .gitignore, .gitattributes,
  bridge_config.json, 41 source .py).
- Files moved: 104 (hash-verified, before == after for all).
- Duplicates removed: 0 (no true duplicates existed; v07 vs v08 matrices
  are distinct versions, both kept).
- Loose text documents: none at root (no .txt present; nothing to move).

## Destinations

- docs/architecture/ — 29 topical design docs.
- docs/releases/v0.8/ — 28 release md (V08_/V07_/matrices/benchmarks) + INDEX.md.
- reports/v0.8/ — 33 machine-readable json evidence files.
- config/ — historical bridge_config_v05/v06 (live config stays root).
- docs/ — api_schema_v05.json (beside existing schemas).
- scripts/ — 11 run_*.py acceptance/evidence drivers.

## References updated

- All scripts: sys.path now resolves the repo root from scripts/;
  outputs write to reports/v0.8 + docs/releases/v0.8.
- run_v07_full imports run_windows sibling (same dir, intact).
- tests/test_versions_cleanup.py reads config/bridge_config_v05.json.
- docs/REPRODUCIBLE_SETUP.md commands use scripts/ paths.
- Machine move log (old/new/hash/refs): reports/v0.8/V08_ROOT_LAYOUT_MOVES.json.

## Verification

- py_compile over scripts/ (see audit json).
- Targeted: test_versions_cleanup, test_repo_portability,
  test_secret_hygiene — all PASS post-move.
- No source module moved, so all package imports are unchanged.
