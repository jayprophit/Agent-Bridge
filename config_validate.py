"""Strict config validation + v0.3/v0.4 migration (v0.5, schema 2)."""
from __future__ import annotations

from typing import Any

from config import VALID_APPROVALS, VALID_COLLISIONS, VALID_MODES, VALID_PROMPT_PROFILES

KNOWN_TOP_KEYS = {
    "config_schema", "ollama_url", "ollama_host", "model", "roles", "models",
    "preset", "fallback", "workspace", "mode", "approval", "collision",
    "prompt_profile", "max_steps", "max_revision_cycles", "request_timeout_s",
    "shell_timeout_s", "shell_profile", "non_interactive", "dry_run",
    "repeat_threshold", "large_write_bytes", "enable_reviewer", "git",
    "cache", "logging", "test_profile", "context", "runtime", "_comment",
}

# Security-sensitive keys that must never appear with unexpected shapes.
SENSITIVE_KEYS = ("token", "password", "secret", "api_key", "host")


def validate_dict(d: dict[str, Any]) -> tuple[bool, list[str]]:
    """Strict validation. Returns (ok, [problems]). Unknown security-sensitive
    fields, wrong types, bad enums, public bind, bad quotas all fail."""
    problems: list[str] = []
    if not isinstance(d, dict):
        return False, ["config must be a JSON object"]
    for k in d:
        if k not in KNOWN_TOP_KEYS and k.lower() in SENSITIVE_KEYS:
            problems.append(f"unknown security-sensitive field rejected: {k!r}")
    mode = d.get("mode", "build")
    if mode not in VALID_MODES:
        problems.append(f"invalid mode {mode!r}")
    if d.get("approval", "AUTO_SAFE") not in VALID_APPROVALS:
        problems.append(f"invalid approval {d.get('approval')!r}")
    if d.get("collision", "REQUIRE_APPROVAL") not in VALID_COLLISIONS:
        problems.append(f"invalid collision {d.get('collision')!r}")
    if d.get("prompt_profile", "standard") not in VALID_PROMPT_PROFILES:
        problems.append(f"invalid prompt_profile {d.get('prompt_profile')!r}")
    for numkey in ("max_steps", "max_revision_cycles", "request_timeout_s",
                   "shell_timeout_s", "repeat_threshold", "large_write_bytes"):
        if numkey in d and (not isinstance(d[numkey], int) or d[numkey] < 0):
            problems.append(f"{numkey} must be a non-negative integer")
    rt = d.get("runtime", {})
    if rt:
        if not isinstance(rt, dict):
            problems.append("runtime must be an object")
        else:
            host = rt.get("host", "127.0.0.1")
            if host not in ("127.0.0.1", "localhost", "::1"):
                problems.append(
                    f"public bind {host!r} refused without explicit override")
            roots = rt.get("allowed_workspace_roots", [])
            if roots is not None and (not isinstance(roots, list) or
                                      not all(isinstance(r, str) for r in roots)):
                problems.append("allowed_workspace_roots must be a string list")
            q = rt.get("quotas", {})
            if q:
                for qk, qv in q.items():
                    if not isinstance(qv, int) or qv <= 0:
                        problems.append(f"quota {qk!r} must be a positive integer")
            for rk, rv in (rt.get("roots", {}) or {}).items():
                if not isinstance(rv, dict):
                    problems.append(f"root rule {rk!r} must be an object")
    if "non_interactive" in d and not isinstance(d["non_interactive"], bool):
        problems.append("non_interactive must be a boolean")
    return (not problems), problems


def migrate_dict(d: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize v0.3/v0.4-shaped config to schema 2. Returns (new, warnings).
    Ambiguous security settings warn loudly; unknown approval refuses."""
    import copy
    nd = copy.deepcopy(d)
    warnings: list[str] = []
    if "ollama_host" in nd and "ollama_url" not in nd:
        nd["ollama_url"] = nd.pop("ollama_host")
        warnings.append("renamed ollama_host -> ollama_url")
    if isinstance(nd.get("models"), dict) and "roles" not in nd:
        nd["roles"] = nd.pop("models")
        warnings.append("renamed models -> roles")
    if "non_interactive" not in nd:
        nd["non_interactive"] = True
        warnings.append("non_interactive was ambiguous: defaulting to true "
                        "(safe); set explicitly to override")
    if "approval" not in nd:
        nd["approval"] = "AUTO_SAFE"
        warnings.append("approval ambiguous: defaulting to AUTO_SAFE")
    if "collision" not in nd:
        nd["collision"] = "REQUIRE_APPROVAL"
        warnings.append("collision ambiguous: defaulting to REQUIRE_APPROVAL")
    git = nd.setdefault("git", {})
    if git.get("checkpoint_label_prefix", "").startswith("bridge-v0"):
        if git["checkpoint_label_prefix"] != "bridge-v06":
            warnings.append(
                f"checkpoint prefix {git['checkpoint_label_prefix']!r} is stale; "
                "new checkpoints use bridge-v06 (old manifests stay readable)")
            git["checkpoint_label_prefix"] = "bridge-v06"
    nd["config_schema"] = 2
    ok, problems = validate_dict(nd)
    if not ok:
        raise ValueError(f"migrated config invalid: {problems}")
    return nd, warnings
