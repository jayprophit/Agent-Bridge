# Legacy Model Compatibility (v0.8, Part B)

Modes (evidence-selected, never name-based): NATIVE_TOOL_CALLING,
BRIDGE_STRUCTURED_ACTION, STRICT_JSON_ACTION, TEXT_ACTION_TRANSLATION,
LEGACY_MODEL_MODE, plus orthogonal SMALL_CONTEXT_MODE (budgets).
`compat/negotiation.py` reuses `tools/toolkit.py` shortlisting with
mode budgets; `tools.search` expands. `LegacyActionTranslator` parses
fenced/bare JSON and `tool:` lines, validates tool_id against the registry
(unknown tools rejected, never invented), repairs bounded times, fails safe.
Measured: qwen2.5-coder-tools:3b STRICT_JSON end-to-end live; qwen3:0.6b
TEXT_ACTION / qwen3:1.7b LEGACY selected, single repair did not recover
(fails safe). See SMALL_MODEL_RUNTIME.md.
