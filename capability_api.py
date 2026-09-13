"""Capability public API (v0.9.0 Phase 1).

Additive facade over the new intelligence modules. No existing core modified.
Exposes, through existing Agent Bridge patterns (plain functions returning dicts):

  machine_capabilities()
  execution_environments()
  toolchains()
  languages()
  inspect_project(workspace)
  recommend_toolchain(component)
"""
from __future__ import annotations

from typing import Any

from machine_capability import MachineCapabilityRegistry
from execution_environment import ExecutionEnvironmentRegistry
from toolchain_registry import ToolchainRegistry, ToolchainStatus
from language_registry import LanguageRegistry
from project_detector import inspect_project as _inspect, profile_to_dict
from project_model import build_project_model, model_to_dict
from tool_selector import ProjectRequirement, ToolSelectionEngine
from capability_cache import CapabilityCache

_cache = CapabilityCache(ttl_seconds=3600.0)
_machine_registry = MachineCapabilityRegistry()
_env_registry = ExecutionEnvironmentRegistry()
_toolchain_registry = ToolchainRegistry()
_language_registry = LanguageRegistry()
_selector = ToolSelectionEngine(_toolchain_registry)


def machine_capabilities(force: bool = False) -> dict[str, Any]:
    if not force:
        hit = _cache.get("machine")
        if hit is not None:
            return hit.payload
    cap = _machine_registry.scan(force=force)
    payload = _machine_registry.to_dict(cap)
    tools = {t.name: t.version for t in cap.tools}
    _cache.put("machine", payload, tools)
    return payload


def execution_environments(force: bool = False) -> dict[str, Any]:
    if not force:
        hit = _cache.get("environments")
        if hit is not None:
            return hit.payload
    machine = _machine_registry.scan(force=force)
    envs = _env_registry.discover(machine)
    payload = {k: {
        "identifier": v.identifier, "platform": v.platform,
        "architecture": v.architecture, "shell": v.shell,
        "available_tools": v.available_tools,
        "path_semantics": v.path_semantics,
        "working_directory_behavior": v.working_directory_behavior,
        "health": v.health, "limitations": v.limitations,
        "metadata": v.metadata,
    } for k, v in envs.items()}
    _cache.put("environments", payload, {})
    return payload


def toolchains(language: str = "", force: bool = False) -> dict[str, Any]:
    if not force:
        hit = _cache.get("toolchains")
        if hit is not None:
            payload = hit.payload
            if language:
                return {k: v for k, v in payload.items()
                        if language in v.get("supported_languages", [])}
            return payload
    machine = _machine_registry.scan(force=force)
    envs = _env_registry.discover(machine)
    found = _toolchain_registry.discover_all(machine, envs)
    payload: dict[str, Any] = {}
    for tid, tc in found.items():
        payload[tid] = {
            "id": tc.id, "name": tc.name,
            "primary_language": tc.primary_language,
            "supported_languages": tc.supported_languages,
            "status": tc.status.value if hasattr(tc.status, "value") else str(tc.status),
            "rank": tc.rank, "environments": tc.environments,
            "components": [{
                "name": c.name, "executable_path": c.executable_path,
                "version": c.version,
                "category": c.category.value if hasattr(c.category, "value") else str(c.category),
                "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                "languages": c.languages,
            } for c in tc.components],
        }
    versions = {}
    for tid, tc in found.items():
        for c in tc.components:
            if c.version:
                versions[f"{tid}:{c.name}"] = c.version
    _cache.put("toolchains", payload, versions)
    if language:
        return {k: v for k, v in payload.items()
                if language in v.get("supported_languages", [])}
    return payload


def languages(force: bool = False) -> dict[str, Any]:
    if not force:
        hit = _cache.get("languages")
        if hit is not None:
            return hit.payload
    machine = _machine_registry.scan(force=force)
    envs = _env_registry.discover(machine)
    _toolchain_registry.discover_all(machine, envs)
    _language_registry._machine = machine  # reuse scan (same-process additive use)
    _language_registry._environments = envs
    _language_registry._toolchains = dict(_toolchain_registry._toolchains)
    caps = _language_registry.get_all_capabilities()
    payload: dict[str, Any] = {}
    for lang, cap in caps.items():
        payload[lang] = {
            "language": cap.language,
            "recommended_toolchain": cap.recommended_toolchain,
            "available_toolchains": [t.id for t in cap.available_toolchains
                                     if t.status == ToolchainStatus.AVAILABLE],
            "build_support": cap.build_support.name,
            "test_support": cap.test_support.name,
            "debug_support": cap.debug_support.name,
            "format_support": cap.format_support.name,
            "lint_support": cap.lint_support.name,
            "typical_runtimes": cap.typical_runtimes,
        }
    _cache.put("languages", payload, {})
    return payload


def inspect_project(workspace: str) -> dict[str, Any]:
    """Read-only project inspection returning profile + model."""
    profile = _inspect(workspace)
    model = build_project_model(profile)
    return {"profile": profile_to_dict(profile), "model": model_to_dict(model)}


def recommend_toolchain(component: dict[str, Any]) -> dict[str, Any]:
    """Recommend toolchains for a project component dict.

    Expected keys: language, min_version, build_system, environment, standards.
    """
    req = ProjectRequirement(
        language=str(component.get("language", "")),
        min_version=str(component.get("min_version", "")),
        build_system=str(component.get("build_system", "")),
        test_framework=str(component.get("test_framework", "")),
        environment=str(component.get("environment", "")),
        standards=list(component.get("standards", [])),
        user_override_toolchain=str(component.get("user_override_toolchain", "")),
    )
    machine = _machine_registry.scan()
    envs = _env_registry.discover(machine)
    tcs = list(_toolchain_registry.discover_all(machine, envs).values())
    options = _selector.recommend(req, tcs)
    return {"requirement": {
        "language": req.language, "min_version": req.min_version,
        "build_system": req.build_system, "environment": req.environment,
        "standards": req.standards,
    }, "options": [{
        "toolchain_id": o.toolchain_id, "name": o.name, "score": o.score,
        "reasons": o.reasons, "warnings": o.warnings, "compatible": o.compatible,
    } for o in options]}


def cache_status() -> dict[str, Any]:
    return _cache.status()


def invalidate_cache(key: str | None = None) -> dict[str, Any]:
    return {"removed": _cache.invalidate(key)}
