"""Project Detector (v0.9.0 Phase 1).

Reusable, READ-ONLY workspace inspection.
Never executes project code, never runs package scripts, never installs.
"""
from __future__ import annotations

import fnmatch
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


MAX_READ_BYTES = 8000
MAX_SCAN_FILES = 5000
MAX_DEPTH = 4

# Indicator filename -> (project_kind, language_hint, component_hint)
INDICATOR_FILES: dict[str, tuple[str, str, str]] = {
    "package.json": ("node", "javascript", "frontend"),
    "tsconfig.json": ("typescript", "typescript", "frontend"),
    "vite.config.js": ("vite", "javascript", "frontend"),
    "vite.config.ts": ("vite", "typescript", "frontend"),
    "webpack.config.js": ("webpack", "javascript", "frontend"),
    "next.config.js": ("nextjs", "javascript", "frontend"),
    "pyproject.toml": ("python", "python", "backend"),
    "requirements.txt": ("python", "python", "backend"),
    "setup.py": ("python", "python", "backend"),
    "setup.cfg": ("python", "python", "backend"),
    "Pipfile": ("python", "python", "backend"),
    "poetry.lock": ("python", "python", "backend"),
    "Cargo.toml": ("rust", "rust", "service"),
    "Cargo.lock": ("rust", "rust", "service"),
    "CMakeLists.txt": ("cmake", "cpp", "native-engine"),
    "Makefile": ("make", "c", "native-engine"),
    "makefile": ("make", "c", "native-engine"),
    "meson.build": ("meson", "c", "native-engine"),
    "go.mod": ("go", "go", "service"),
    "go.sum": ("go", "go", "service"),
    "pom.xml": ("maven", "java", "backend"),
    "build.gradle": ("gradle", "java", "backend"),
    "build.gradle.kts": ("gradle", "kotlin", "backend"),
    "pubspec.yaml": ("flutter", "dart", "frontend"),
    "Dockerfile": ("docker", "", "containers"),
    "docker-compose.yml": ("docker-compose", "", "containers"),
    "docker-compose.yaml": ("docker-compose", "", "containers"),
    "compose.yaml": ("docker-compose", "", "containers"),
    "platformio.ini": ("platformio", "cpp", "firmware"),
    ".platformio": ("platformio", "cpp", "firmware"),
    "sketch.json": ("arduino", "cpp", "firmware"),
    ".ino": ("arduino", "cpp", "firmware"),
}

INDICATOR_GLOBS: list[tuple[str, str, str, str]] = [
    ("*.sln", "dotnet", "csharp", "backend"),
    ("*.csproj", "dotnet", "csharp", "backend"),
    ("*.fsproj", "dotnet", "fsharp", "backend"),
    ("*.vbproj", "dotnet", "vb", "backend"),
    ("*.ino", "arduino", "cpp", "firmware"),
    ("*.vert", "shader", "glsl", "shaders"),
    ("*.frag", "shader", "glsl", "shaders"),
    ("*.glsl", "shader", "glsl", "shaders"),
    ("*.hlsl", "shader", "glsl", "shaders"),
    ("*.wgsl", "shader", "glsl", "shaders"),
    ("*.comp", "shader", "glsl", "shaders"),
    ("vite.config.*", "vite", "typescript", "frontend"),
    ("webpack.*.js", "webpack", "javascript", "frontend"),
]

SOURCE_EXTENSIONS: dict[str, str] = {
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp",
    ".rs": "rust",
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript",
    ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".cs": "csharp", ".fs": "fsharp", ".vb": "vb",
    ".go": "go", ".swift": "swift", ".dart": "dart",
    ".sql": "sql",
    ".html": "html", ".htm": "html",
    ".css": "css", ".scss": "css", ".sass": "css", ".less": "css",
    ".sh": "shell", ".bash": "shell",
    ".ps1": "powershell", ".psm1": "powershell",
    ".s": "assembly", ".asm": "assembly",
    ".vert": "glsl", ".frag": "glsl", ".glsl": "glsl", ".hlsl": "glsl", ".wgsl": "glsl",
    ".ino": "arduino",
}

TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "e2e", "integration"}
DOC_NAMES = {"README.md", "README", "CHANGELOG.md", "docs", "doc", "DOCUMENTATION.md"}
ASSET_DIRS = {"assets", "static", "public", "images", "img", "audio", "video", "models", "textures", "shaders"}


@dataclass
class ProjectIndicator:
    kind: str = ""
    path: str = ""
    language: str = ""
    component: str = ""


@dataclass
class ProjectProfile:
    workspace: str = ""
    exists: bool = False
    indicators: list[ProjectIndicator] = field(default_factory=list)
    languages: dict[str, int] = field(default_factory=dict)  # language -> file count
    components: dict[str, list[str]] = field(default_factory=dict)  # component -> languages
    build_files: list[str] = field(default_factory=list)
    test_dirs: list[str] = field(default_factory=list)
    doc_files: list[str] = field(default_factory=list)
    asset_dirs: list[str] = field(default_factory=list)
    container_files: list[str] = field(default_factory=list)
    firmware_hints: list[str] = field(default_factory=list)
    shader_files: list[str] = field(default_factory=list)
    database_hints: list[str] = field(default_factory=list)
    project_kinds: list[str] = field(default_factory=list)
    confidence: str = "unknown"  # unknown, low, medium, high
    notes: list[str] = field(default_factory=list)


def _safe_read_text(path: Path, limit: int = MAX_READ_BYTES) -> str:
    try:
        if path.stat().st_size > 4 * 1024 * 1024:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _iter_files(root: Path, max_depth: int = MAX_DEPTH, max_files: int = MAX_SCAN_FILES):
    """Yield (path, depth) without following symlinked dirs outside root."""
    count = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    seen: set[str] = set()
    while stack and count < max_files:
        cur, depth = stack.pop()
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            if count >= max_files:
                break
            try:
                p = Path(e.path)
                # Skip heavy/irrelevant dirs
                if e.is_dir(follow_symlinks=False):
                    name = e.name
                    if name in {".git", "node_modules", "__pycache__", ".venv", "venv",
                                "target", "build", "dist", ".bridge", ".pytest_cache",
                                ".mypy_cache", ".ruff_cache", "out", "bin", "obj"}:
                        continue
                    if depth + 1 <= max_depth:
                        real = str(p.resolve()) if p.exists() else str(p)
                        if real not in seen:
                            seen.add(real)
                            stack.append((p, depth + 1))
                elif e.is_file(follow_symlinks=False):
                    count += 1
                    yield p, depth
            except OSError:
                continue


def inspect_project(workspace: str | Path) -> ProjectProfile:
    """Inspect a workspace read-only and return a structured profile."""
    root = Path(str(workspace or "."))
    profile = ProjectProfile(workspace=str(root))
    if not root.exists() or not root.is_dir():
        profile.notes.append("workspace does not exist or is not a directory")
        return profile
    profile.exists = True

    indicators: list[ProjectIndicator] = []
    languages: dict[str, int] = {}
    components: dict[str, set[str]] = {}
    build_files: list[str] = []
    test_dirs: set[str] = set()
    doc_files: list[str] = []
    asset_dirs: set[str] = set()
    container_files: list[str] = []
    firmware_hints: list[str] = []
    shader_files: list[str] = []
    database_hints: list[str] = []
    kinds: set[str] = set()

    def _add_component(comp: str, lang: str) -> None:
        if not comp:
            return
        components.setdefault(comp, set())
        if lang:
            components[comp].add(lang)

    # Top-level indicator files (depth 0-1, cheap)
    try:
        top_entries = [p for p in root.iterdir()]
    except OSError:
        top_entries = []
    for p in top_entries:
        name = p.name
        if p.is_file() and name in INDICATOR_FILES:
            kind, lang, comp = INDICATOR_FILES[name]
            indicators.append(ProjectIndicator(kind=kind, path=name, language=lang, component=comp))
            kinds.add(kind)
            build_files.append(name)
            _add_component(comp, lang)
            if kind in ("docker", "docker-compose"):
                container_files.append(name)
            if kind in ("platformio", "arduino"):
                firmware_hints.append(name)
        elif p.is_dir():
            if p.name in TEST_DIR_NAMES:
                test_dirs.add(p.name)
            if p.name in DOC_NAMES:
                doc_files.append(p.name)
            if p.name in ASSET_DIRS:
                asset_dirs.add(p.name)

    # Deeper scan for globs, sources, tests, docs, assets
    for f, _depth in _iter_files(root):
        fname = f.name
        try:
            rel = str(f.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = fname

        # Glob indicators
        for pattern, kind, lang, comp in INDICATOR_GLOBS:
            if fnmatch.fnmatch(fname, pattern):
                indicators.append(ProjectIndicator(kind=kind, path=rel, language=lang, component=comp))
                kinds.add(kind)
                if kind == "shader":
                    shader_files.append(rel)
                elif kind in ("dotnet",):
                    build_files.append(rel)
                else:
                    build_files.append(rel)
                _add_component(comp, lang)
                break

        # Exact indicator files at any depth (limit to known names)
        if fname in INDICATOR_FILES and rel not in [i.path for i in indicators]:
            kind, lang, comp = INDICATOR_FILES[fname]
            # Only record nested ones if meaningful (e.g., nested package.json = monorepo component)
            if "/" in rel:
                indicators.append(ProjectIndicator(kind=kind, path=rel, language=lang, component=comp))
                kinds.add(kind)
                _add_component(comp, lang)

        # Source languages
        ext = f.suffix.lower()
        if ext in SOURCE_EXTENSIONS:
            lang = SOURCE_EXTENSIONS[ext]
            languages[lang] = languages.get(lang, 0) + 1
            if ext in (".vert", ".frag", ".glsl", ".hlsl", ".wgsl") and rel not in shader_files:
                shader_files.append(rel)
            if ext == ".sql" and rel not in database_hints:
                database_hints.append(rel)

        # Test dirs (any depth, record relative)
        parts = rel.split("/")
        for part in parts[:-1]:
            if part in TEST_DIR_NAMES:
                test_dirs.add(rel.rsplit("/", 1)[0] if "/" in rel else part)
                break

        # Docs
        if fname in ("README.md", "README", "CHANGELOG.md", "DOCUMENTATION.md"):
            if rel not in doc_files:
                doc_files.append(rel)

        # Asset dirs
        for part in parts[:-1]:
            if part in ASSET_DIRS:
                asset_dirs.add(part)
                break

        # Schema / migration hints
        if fname in ("schema.sql", "schema.prisma", "migration.sql") or \
                ("migrations" in parts and ext == ".sql"):
            if rel not in database_hints:
                database_hints.append(rel)

    profile.indicators = indicators
    profile.languages = dict(sorted(languages.items(), key=lambda kv: (-kv[1], kv[0])))
    profile.components = {k: sorted(v) for k, v in components.items()}
    profile.build_files = sorted(set(build_files))[:100]
    profile.test_dirs = sorted(test_dirs)[:50]
    profile.doc_files = sorted(set(doc_files))[:50]
    profile.asset_dirs = sorted(asset_dirs)[:50]
    profile.container_files = sorted(set(container_files))[:20]
    profile.firmware_hints = sorted(set(firmware_hints))[:20]
    profile.shader_files = shader_files[:100]
    profile.database_hints = database_hints[:50]
    profile.project_kinds = sorted(kinds)

    # Confidence heuristic
    score = len(indicators) * 2 + len(profile.languages) + len(profile.test_dirs)
    if score >= 8:
        profile.confidence = "high"
    elif score >= 4:
        profile.confidence = "medium"
    elif score >= 1:
        profile.confidence = "low"

    if not indicators and not profile.languages:
        profile.notes.append("unknown project: no indicators or recognized sources")
    return profile


def profile_to_dict(profile: ProjectProfile) -> dict[str, Any]:
    return asdict(profile)


if __name__ == "__main__":
    import json
    import sys as _sys
    target = _sys.argv[1] if len(_sys.argv) > 1 else "."
    print(json.dumps(profile_to_dict(inspect_project(target)), indent=2))
