# Small Model Runtime (v0.8, Part B)

Small models get bounded shortlists (12/6/4 tools), compact schemas
(3000/1200/800 chars), one action per turn, and the UnknownLegacyModel9000
synthetic proves a text-only small-context model can complete bounded tasks.
Live: V08_COMPAT_ACCEPTANCE.json. AgentCore/loop untouched; `compat/` is the
wiring layer (prepare prompt -> model -> translate -> ToolRouter -> policy).
