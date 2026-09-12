# ADR-001: Keep the flat top-level package (no src/ move in v0.8.x)

Status: accepted.

Context: v0.8.0 ships 41 runtime modules as flat top-level imports
(`import runtime`, `from bridge import run_bridge`, …) used by 58 test
files, 11 scripts, the HTTP service, CLI and SDK.

Decision: do NOT migrate to `src/agent_bridge/` in the v0.8.x line.
A move would rewrite every import site with zero behavioral gain and
real regression risk on a frozen, verified tree.

Consequences: packaging (if ever needed) can use a shim or a later
major with a compat alias package. Revisit only with owner approval.
