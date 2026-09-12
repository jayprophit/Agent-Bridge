"""Independent versioning (v0.5). API v1 unbroken; protocol 0.4 wire."""
from __future__ import annotations

RUNTIME_VERSION = "0.6"
API_VERSION = "v1"
PROTOCOL_VERSION = "0.4"
PROTOCOL_ACCEPTED = ("0.1", "0.2", "0.3", "0.4", "")
CONFIG_SCHEMA_VERSION = 2
PROMPT_PROFILE_VERSION = 1
CLIENT_SDK_VERSION = "0.6"

COMPATIBILITY = {
    "runtime": RUNTIME_VERSION,
    "api": API_VERSION,
    "protocol": PROTOCOL_VERSION,
    "protocol_accepts": list(PROTOCOL_ACCEPTED),
    "config_schema": CONFIG_SCHEMA_VERSION,
    "prompts": PROMPT_PROFILE_VERSION,
    "client_sdk": CLIENT_SDK_VERSION,
    "notes": ("API v1 stable since 0.4; protocol 0.4 wire-compatible; "
              "0.1-0.3 action formats still accepted; "
              "config schema 2 migrates v0.3/v0.4/v0.5 files with warnings; "
              "v0.4/v0.5 client operations unchanged"),
}

# Stale labels that must never be produced by new code (regression guard).
STALE_LABEL_FRAGMENTS = ("bridge-v01", "bridge-v02", "bridge-v03", "bridge-v04",
                           "bridge-v05")
CHECKPOINT_LABEL_PREFIX = "bridge-v06"
