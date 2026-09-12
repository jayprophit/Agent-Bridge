# v0.8 Tool Capability Matrix (regenerated live, convergence)

Source: `python -c "from tools.tool_audit import audit"` on this PC.
Methodology: enumerated live from `tools/cat_* *_records()`; AVAILABLE +
backend + exact tool_id reference in `tests/*.py` => IMPLEMENTED_VERIFIED;
AVAILABLE + backend without direct reference => IMPLEMENTED_UNVERIFIED;
declared PROVIDER_REQUIRED / NOT_INSTALLED / DISABLED pass through.

## Counts (370 tools, 43 families)

| State | Count |
|---|---|
| IMPLEMENTED_VERIFIED | 16 |
| IMPLEMENTED_UNVERIFIED | 260 |
| PROVIDER_REQUIRED | 73 |
| NOT_INSTALLED | 16 |
| DISABLED | 5 |
| INTERFACE_ONLY / MODEL_REQUIRED / DEVICE_REQUIRED / ADMIN_REQUIRED / DEGRADED / UNSUPPORTED_PLATFORM | 0 |
| **Total** | **370** |

Previous report said 364 / 7 / 266 / 13: stale (catalog grew; audit now
live). No duplicates: every tool_id namespaced, registry rejects dupes.

## Notable families

- email: 3 VERIFIED (draft/compose local) + 3 PROVIDER_REQUIRED (send).
- browser/filesystem: VERIFIED via real local backends.
- github (9), http-remote (6), image-generative (5), stt-audio (3):
  PROVIDER_REQUIRED / NOT_INSTALLED, never faked AVAILABLE.
- Full per-tool entries: V08_TOOL_CAPABILITY_MATRIX.json (`tools` array).
