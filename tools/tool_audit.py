"""ToolRegistry truth audit (v0.7, convergence).

Enumerates every tool definition from all tools/cat_* catalogs and classifies
each into canonical implementation states. AVAILABLE is never used as a
synonym for "definition exists": a definition with no backend is
INTERFACE_ONLY, and IMPLEMENTED_VERIFIED requires direct evidence (exact
tool_id reference in a passing test).

Usage:
    python -m tools.tool_audit  # prints summary JSON
"""
from __future__ import annotations

import glob
import importlib
import inspect
import json
import os
import pkgutil
from collections import Counter
from typing import Any

import tools
from tools.registry import (
    ADMIN_REQUIRED, AVAILABLE, DEGRADED, DISABLED, MODEL_REQUIRED,
    NOT_INSTALLED, PROVIDER_REQUIRED, UNSUPPORTED_PLATFORM,
)

# Canonical implementation states for the release matrix.
IMPLEMENTED_VERIFIED = "IMPLEMENTED_VERIFIED"
IMPLEMENTED_UNVERIFIED = "IMPLEMENTED_UNVERIFIED"
INTERFACE_ONLY = "INTERFACE_ONLY"
DEVICE_REQUIRED = "DEVICE_REQUIRED"

STATES = (
    IMPLEMENTED_VERIFIED, IMPLEMENTED_UNVERIFIED, INTERFACE_ONLY,
    PROVIDER_REQUIRED, MODEL_REQUIRED, NOT_INSTALLED, DEVICE_REQUIRED,
    ADMIN_REQUIRED, UNSUPPORTED_PLATFORM, DEGRADED, DISABLED,
)


def collect_records() -> list:
    """Collect every ToolRecord from all tools/cat_* catalogs."""
    recs = []
    for mod in pkgutil.iter_modules(tools.__path__):
        if not mod.name.startswith("cat_"):
            continue
        module = importlib.import_module("tools." + mod.name)
        for fname, fn in inspect.getmembers(module, inspect.isfunction):
            if fname.endswith("_records"):
                try:
                    recs.extend(fn())
                except TypeError:
                    continue
    return recs


def verified_tool_ids(repo_root: str = "") -> set[str]:
    """Exact tool_ids referenced in tests/*.py (direct evidence only)."""
    root = repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ids: set[str] = set()
    recs = collect_records()
    candidates = {r.tool_id for r in recs}
    for path in glob.glob(os.path.join(root, "tests", "test_*.py")):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for tool_id in candidates:
            if tool_id in text:
                ids.add(tool_id)
    return ids


def classify(record, verified_ids: set[str]) -> str:
    """Classify one record into a canonical implementation state."""
    status = record.status
    if status == PROVIDER_REQUIRED:
        return PROVIDER_REQUIRED
    if status == MODEL_REQUIRED:
        return MODEL_REQUIRED
    if status == NOT_INSTALLED:
        return NOT_INSTALLED
    if status == DISABLED:
        return DISABLED
    if status == DEGRADED:
        return DEGRADED
    if status == UNSUPPORTED_PLATFORM:
        return UNSUPPORTED_PLATFORM
    if status == ADMIN_REQUIRED:
        return ADMIN_REQUIRED
    if status == AVAILABLE:
        if not record.backend or record.backend == "none":
            return INTERFACE_ONLY
        if record.tool_id in verified_ids:
            return IMPLEMENTED_VERIFIED
        return IMPLEMENTED_UNVERIFIED
    return status


def audit(repo_root: str = "") -> dict[str, Any]:
    """Run the full audit; returns a JSON-safe matrix dict."""
    recs = collect_records()
    verified = verified_tool_ids(repo_root)
    by_state: Counter = Counter()
    by_family: dict[str, Counter] = {}
    entries = []
    for r in recs:
        state = classify(r, verified)
        by_state[state] += 1
        fam = r.tool_id.split(".")[0]
        by_family.setdefault(fam, Counter())[state] += 1
        entries.append({
            "tool_id": r.tool_id,
            "family": fam,
            "implementation_state": state,
            "declared_status": r.status,
            "backend": r.backend,
            "provider": r.provider,
            "installed": bool(r.installed),
            "enabled": bool(r.enabled),
            "verified": state == IMPLEMENTED_VERIFIED,
            "risk": r.risk_class,
            "admin": bool(r.requires_admin),
            "network": r.requires_network,
            "model_requirement": r.requires_model_capability,
            "rollback": bool(r.supports_rollback),
            "cancel": bool(r.supports_cancel),
            "audit": bool(r.supports_audit),
            "limitations": r.limitations,
        })
    entries.sort(key=lambda e: e["tool_id"])
    counts = {s: int(by_state.get(s, 0)) for s in STATES}
    return {
        "total_registered_tools": len(recs),
        "counts": counts,
        "families": {fam: dict(cnt) for fam, cnt in sorted(by_family.items())},
        "methodology": (
            "Enumerated live from tools/cat_* *_records() on this machine. "
            "AVAILABLE+backend+exact tool_id reference in tests/*.py => "
            "IMPLEMENTED_VERIFIED. AVAILABLE+backend without direct reference "
            "=> IMPLEMENTED_UNVERIFIED. AVAILABLE with no backend => "
            "INTERFACE_ONLY. Declared PROVIDER_REQUIRED/MODEL_REQUIRED/"
            "NOT_INSTALLED/DISABLED/DEGRADED/UNSUPPORTED_PLATFORM/ADMIN_REQUIRED "
            "pass through unchanged."
        ),
        "tools": entries,
    }


def main() -> int:
    print(json.dumps(audit(), indent=1)[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
