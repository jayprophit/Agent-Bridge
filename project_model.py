"""Mixed-Language Project Model (v0.9.0 Phase 1).

A project may contain MANY languages simultaneously.
Do NOT choose one project language and discard the others.

Models full-stack contracts: frontend, backend/API, database, workers,
native services, containers, firmware, tests, assets, docs, deployment.
This phase creates the intelligence/contracts the orchestrator will use later.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from project_detector import ProjectProfile, inspect_project


@dataclass
class ProjectComponent:
    """One component of a (possibly mixed-language) project."""
    name: str = ""  # e.g., frontend, backend, native-engine, ml-worker, service, database, shaders, firmware
    role: str = ""  # frontend, backend, native, ml, service, database, firmware, shaders, containers, docs, assets, tests
    languages: list[str] = field(default_factory=list)
    runtime: str = ""  # e.g., node, python, dotnet, jvm
    toolchain_id: str = ""  # recommended toolchain id (from ToolchainRegistry)
    build_command: str = ""
    test_command: str = ""
    dependencies: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    source_dirs: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # indicator paths that caused this component


@dataclass
class FullStackProject:
    """Full-stack project contract."""
    workspace: str = ""
    name: str = ""
    components: list[ProjectComponent] = field(default_factory=list)
    primary_languages: list[str] = field(default_factory=list)
    all_languages: list[str] = field(default_factory=list)
    has_frontend: bool = False
    has_backend: bool = False
    has_database: bool = False
    has_native: bool = False
    has_firmware: bool = False
    has_shaders: bool = False
    has_containers: bool = False
    has_tests: bool = False
    has_docs: bool = False
    has_assets: bool = False
    build_targets: list[str] = field(default_factory=list)
    deployment_targets: list[str] = field(default_factory=list)
    confidence: str = "unknown"
    notes: list[str] = field(default_factory=list)


# Heuristic mapping: detector kind -> component role + defaults
KIND_TO_COMPONENT: dict[str, dict[str, Any]] = {
    "node": {"role": "frontend", "name": "frontend", "languages": ["javascript"], "runtime": "node"},
    "typescript": {"role": "frontend", "name": "frontend", "languages": ["typescript"], "runtime": "node"},
    "vite": {"role": "frontend", "name": "frontend", "languages": ["typescript", "javascript"], "runtime": "node"},
    "webpack": {"role": "frontend", "name": "frontend", "languages": ["javascript"], "runtime": "node"},
    "nextjs": {"role": "frontend", "name": "frontend", "languages": ["typescript", "javascript"], "runtime": "node"},
    "python": {"role": "backend", "name": "backend", "languages": ["python"], "runtime": "python"},
    "rust": {"role": "service", "name": "service", "languages": ["rust"], "runtime": ""},
    "cmake": {"role": "native", "name": "native-engine", "languages": ["cpp", "c"], "runtime": ""},
    "make": {"role": "native", "name": "native-engine", "languages": ["c", "cpp"], "runtime": ""},
    "meson": {"role": "native", "name": "native-engine", "languages": ["c", "cpp"], "runtime": ""},
    "go": {"role": "service", "name": "service", "languages": ["go"], "runtime": ""},
    "maven": {"role": "backend", "name": "backend", "languages": ["java"], "runtime": "jvm"},
    "gradle": {"role": "backend", "name": "backend", "languages": ["java", "kotlin"], "runtime": "jvm"},
    "dotnet": {"role": "backend", "name": "backend", "languages": ["csharp"], "runtime": "dotnet"},
    "flutter": {"role": "frontend", "name": "frontend", "languages": ["dart"], "runtime": "flutter"},
    "docker": {"role": "containers", "name": "containers", "languages": [], "runtime": "docker"},
    "docker-compose": {"role": "containers", "name": "containers", "languages": [], "runtime": "docker"},
    "platformio": {"role": "firmware", "name": "firmware", "languages": ["cpp", "c"], "runtime": ""},
    "arduino": {"role": "firmware", "name": "firmware", "languages": ["cpp", "c"], "runtime": ""},
    "shader": {"role": "shaders", "name": "shaders", "languages": ["glsl"], "runtime": "gpu"},
}

DEFAULT_BUILD_COMMANDS: dict[str, str] = {
    "frontend": "npm run build",
    "backend": "",
    "native-engine": "cmake -S . -B build && cmake --build build",
    "service": "cargo build",
    "firmware": "pio run",
    "shaders": "glslangValidator",
    "containers": "docker compose build",
}

DEFAULT_TEST_COMMANDS: dict[str, str] = {
    "frontend": "npm test",
    "backend": "python -m pytest",
    "native-engine": "ctest --test-dir build",
    "service": "cargo test",
    "firmware": "pio test",
    "shaders": "",
    "containers": "",
}


def build_project_model(profile: ProjectProfile) -> FullStackProject:
    """Build a mixed-language project model from a detector profile."""
    proj = FullStackProject()
    proj.workspace = profile.workspace
    try:
        proj.name = Path(profile.workspace).name
    except Exception:
        proj.name = ""
    proj.confidence = profile.confidence

    by_role: dict[str, ProjectComponent] = {}

    def _get_or_create(role: str, name: str) -> ProjectComponent:
        key = f"{role}:{name}"
        if key not in by_role:
            by_role[key] = ProjectComponent(name=name, role=role)
        return by_role[key]

    # 1) Components from explicit indicators (kinds)
    for ind in profile.indicators:
        mapping = KIND_TO_COMPONENT.get(ind.kind)
        if mapping:
            comp = _get_or_create(mapping["role"], mapping["name"])
            for lang in mapping.get("languages", []):
                if lang and lang not in comp.languages:
                    comp.languages.append(lang)
            if mapping.get("runtime") and not comp.runtime:
                comp.runtime = mapping["runtime"]
            if ind.path and ind.path not in comp.evidence:
                comp.evidence.append(ind.path)
        # dotnet globs etc. already mapped via kind

    # 2) Components from detected component hints (detector components dict)
    for comp_name, langs in (profile.components or {}).items():
        # Map detector component names to model roles
        role_map = {
            "frontend": "frontend", "backend": "backend",
            "native-engine": "native", "service": "service",
            "containers": "containers", "firmware": "firmware",
            "shaders": "shaders",
        }
        role = role_map.get(comp_name, comp_name)
        comp = _get_or_create(role, comp_name)
        for lang in langs:
            if lang and lang not in comp.languages:
                comp.languages.append(lang)

    # 3) Language-only fallback: if sources exist but no indicator, create a generic component
    if not by_role and profile.languages:
        # Single-language project without build files (e.g., script collection)
        top_lang = next(iter(profile.languages))
        role = "backend" if top_lang in ("python", "java", "csharp", "go") else \
               "frontend" if top_lang in ("javascript", "typescript", "html", "css", "dart") else \
               "native" if top_lang in ("c", "cpp", "rust") else \
               "firmware" if top_lang in ("arduino",) else \
               "shaders" if top_lang in ("glsl",) else "service"
        comp = _get_or_create(role, "main")
        if top_lang not in comp.languages:
            comp.languages.append(top_lang)
        comp.evidence.append(f"{sum(profile.languages.values())} source files")

    # 4) Fill defaults per component
    for comp in by_role.values():
        if not comp.build_command:
            comp.build_command = DEFAULT_BUILD_COMMANDS.get(comp.name, "")
        if not comp.test_command:
            comp.test_command = DEFAULT_TEST_COMMANDS.get(comp.name, "")

    # 5) Synthetic cross-cutting components: database, tests, docs, assets
    if profile.database_hints:
        comp = _get_or_create("database", "database")
        if "sql" not in comp.languages:
            comp.languages.append("sql")
        comp.evidence.extend(profile.database_hints[:10])
    if profile.test_dirs:
        comp = _get_or_create("tests", "tests")
        comp.evidence.extend(profile.test_dirs[:10])
        if not comp.test_command:
            # Infer from primary component
            comp.test_command = ""
    if profile.doc_files:
        comp = _get_or_create("docs", "documentation")
        comp.evidence.extend(profile.doc_files[:10])
    if profile.asset_dirs or profile.shader_files:
        if profile.shader_files:
            comp = _get_or_create("shaders", "shaders")
            if "glsl" not in comp.languages:
                comp.languages.append("glsl")
            comp.evidence.extend(profile.shader_files[:10])
        if profile.asset_dirs:
            comp = _get_or_create("assets", "assets")
            comp.evidence.extend(profile.asset_dirs[:10])
    if profile.container_files:
        comp = _get_or_create("containers", "containers")
        comp.evidence.extend(profile.container_files[:10])

    proj.components = sorted(by_role.values(), key=lambda c: (c.role, c.name))

    # Aggregate flags + languages
    all_langs: dict[str, int] = dict(profile.languages)
    for comp in proj.components:
        for lang in comp.languages:
            all_langs[lang] = all_langs.get(lang, 0) + 1
    proj.all_languages = sorted(all_langs, key=lambda l: (-all_langs[l], l))
    proj.primary_languages = proj.all_languages[:3]

    roles = {c.role for c in proj.components}
    proj.has_frontend = "frontend" in roles
    proj.has_backend = "backend" in roles
    proj.has_database = "database" in roles
    proj.has_native = "native" in roles
    proj.has_firmware = "firmware" in roles
    proj.has_shaders = "shaders" in roles
    proj.has_containers = "containers" in roles
    proj.has_tests = "tests" in roles or bool(profile.test_dirs)
    proj.has_docs = "docs" in roles
    proj.has_assets = "assets" in roles

    # Build / deployment targets (descriptive, not executed)
    if proj.has_frontend:
        proj.build_targets.append("web")
    if proj.has_native:
        proj.build_targets.append("native")
    if proj.has_firmware:
        proj.build_targets.append("firmware")
    if proj.has_containers:
        proj.deployment_targets.append("containers")
    if proj.has_backend:
        proj.deployment_targets.append("service")

    if not proj.components:
        proj.notes.append("unknown project: no components inferred")
    return proj


def model_to_dict(proj: FullStackProject) -> dict[str, Any]:
    return asdict(proj)


if __name__ == "__main__":
    import json
    import sys as _sys
    target = _sys.argv[1] if len(_sys.argv) > 1 else "."
    print(json.dumps(model_to_dict(build_project_model(inspect_project(target))), indent=2))
