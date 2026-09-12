# Privacy Routing (v0.7)

Modes: `LOCAL_ONLY`, `LOCAL_FIRST`, `BALANCED`, `REMOTE_ALLOWED`,
`SPECIFIC_PROVIDER`, plus `CURRENT_DEVICE_ONLY` and `TRUSTED_NODES` scopes.
`LOCAL_ONLY` means the current device/runtime only. `LOCAL_FIRST` prefers
local/trusted execution and falls back only where allowed. Remote candidates
must still pass trust, provider, data, capability, and authorization checks.
`SPECIFIC_PROVIDER` honors the owner's choice or fails explicitly — never a
silent substitution. Privacy is checked before private content is
serialized for the network.
