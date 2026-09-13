"""Toolchain Registry (v0.9.0 Phase 1).

Extensible registry for development toolchains.
A toolchain is NOT synonymous with a language - it represents a category
of tools: compiler, interpreter, runtime, build system, package manager,
test framework, debugger, formatter, linter, language server, SDK,
container runtime, firmware toolchain.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from machine_capability import MachineCapabilityRegistry, MachineCapability, ToolInfo, discover_machine_capability
from execution_environment import ExecutionEnvironmentRegistry, discover_execution_environments


class ToolchainCategory(Enum):
    """Categories of toolchains."""
    COMPILER = "compiler"
    INTERPRETER = "interpreter"
    RUNTIME = "runtime"
    BUILD_SYSTEM = "build_system"
    PACKAGE_MANAGER = "package_manager"
    TEST_FRAMEWORK = "test_framework"
    DEBUGGER = "debugger"
    FORMATTER = "formatter"
    LINTER = "linter"
    LANGUAGE_SERVER = "language_server"
    SDK = "sdk"
    CONTAINER_RUNTIME = "container_runtime"
    FIRMWARE_TOOLCHAIN = "firmware_toolchain"
    SHADER_COMPILER = "shader_compiler"
    DATABASE_CLI = "database_cli"
    VCS = "vcs"
    OTHER = "other"


class ToolchainStatus(Enum):
    """Toolchain availability status."""
    AVAILABLE = "AVAILABLE"
    AVAILABLE_BUT_BROKEN = "AVAILABLE_BUT_BROKEN"
    NOT_FOUND = "NOT_FOUND"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class ToolchainComponent:
    """A single tool within a toolchain."""
    name: str = ""
    executable_path: str = ""
    version: str = ""
    category: ToolchainCategory = ToolchainCategory.OTHER
    languages: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    environment: str = ""  # Execution environment identifier
    architecture: str = ""
    status: ToolchainStatus = ToolchainStatus.UNVERIFIED
    probe_command: str = ""
    probe_output: str = ""
    probe_duration_ms: float = 0.0
    source: str = ""  # package manager, manual, bundled, etc.
    requires_admin: bool = False
    last_verified: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Toolchain:
    """A complete toolchain for a language/domain."""
    id: str = ""  # e.g., "cpp-clang-clang++-cmake-ninja"
    name: str = ""
    primary_language: str = ""
    supported_languages: list[str] = field(default_factory=list)
    components: list[ToolchainComponent] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)  # Environment identifiers
    status: ToolchainStatus = ToolchainStatus.UNVERIFIED
    rank: int = 0  # Lower is better (for selection)
    metadata: dict[str, Any] = field(default_factory=dict)


class ToolchainRegistry:
    """Registry for discovering and managing toolchains."""

    def __init__(self):
        self._toolchains: dict[str, Toolchain] = {}
        self._machine_registry = MachineCapabilityRegistry()
        self._env_registry = ExecutionEnvironmentRegistry()
        self._machine: MachineCapability | None = None
        self._environments: dict[str, Any] = {}

    # Default toolchain definitions - these map to the probes in machine_capability.py
    TOOLCHAIN_DEFINITIONS: dict[str, dict[str, Any]] = {
        # C/C++ Toolchains
        "cpp-msvc": {
            "name": "MSVC (Visual Studio)",
            "primary_language": "cpp",
            "supported_languages": ["c", "cpp"],
            "components": [
                {"name": "cl.exe", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "clang-cl", "category": ToolchainCategory.COMPILER, "required": False},
                {"name": "cmake", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "ninja", "category": ToolchainCategory.BUILD_SYSTEM, "required": False},
                {"name": "msbuild", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "lldb", "category": ToolchainCategory.DEBUGGER, "required": False},
            ],
        },
        "cpp-clang": {
            "name": "Clang/LLVM",
            "primary_language": "cpp",
            "supported_languages": ["c", "cpp", "objective-c", "cuda"],
            "components": [
                {"name": "clang", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "clang++", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "cmake", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "ninja", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "lld", "category": ToolchainCategory.COMPILER, "required": False},
                {"name": "lldb", "category": ToolchainCategory.DEBUGGER, "required": False},
            ],
        },
        "cpp-gcc": {
            "name": "GCC/MinGW",
            "primary_language": "cpp",
            "supported_languages": ["c", "cpp", "fortran"],
            "components": [
                {"name": "gcc", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "g++", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "cmake", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "make", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
                {"name": "gdb", "category": ToolchainCategory.DEBUGGER, "required": False},
            ],
        },
        # Rust
        "rust": {
            "name": "Rust Toolchain",
            "primary_language": "rust",
            "supported_languages": ["rust"],
            "components": [
                {"name": "rustc", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "cargo", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
            ],
        },
        # Python
        "python": {
            "name": "Python Toolchain",
            "primary_language": "python",
            "supported_languages": ["python"],
            "components": [
                {"name": "python", "category": ToolchainCategory.INTERPRETER, "required": True},
                {"name": "pip", "category": ToolchainCategory.PACKAGE_MANAGER, "required": True},
                {"name": "uv", "category": ToolchainCategory.PACKAGE_MANAGER, "required": False},
                {"name": "pytest", "category": ToolchainCategory.TEST_FRAMEWORK, "required": False},
                {"name": "ruff", "category": ToolchainCategory.LINTER, "required": False},
                {"name": "mypy", "category": ToolchainCategory.LINTER, "required": False},
                {"name": "black", "category": ToolchainCategory.FORMATTER, "required": False},
            ],
        },
        # Node.js/JavaScript/TypeScript
        "nodejs": {
            "name": "Node.js Toolchain",
            "primary_language": "javascript",
            "supported_languages": ["javascript", "typescript"],
            "components": [
                {"name": "node", "category": ToolchainCategory.RUNTIME, "required": True},
                {"name": "npm", "category": ToolchainCategory.PACKAGE_MANAGER, "required": True},
                {"name": "npx", "category": ToolchainCategory.PACKAGE_MANAGER, "required": False},
                {"name": "pnpm", "category": ToolchainCategory.PACKAGE_MANAGER, "required": False},
                {"name": "yarn", "category": ToolchainCategory.PACKAGE_MANAGER, "required": False},
                {"name": "tsc", "category": ToolchainCategory.COMPILER, "required": False},
                {"name": "eslint", "category": ToolchainCategory.LINTER, "required": False},
                {"name": "prettier", "category": ToolchainCategory.FORMATTER, "required": False},
                {"name": "jest", "category": ToolchainCategory.TEST_FRAMEWORK, "required": False},
                {"name": "vite", "category": ToolchainCategory.BUILD_SYSTEM, "required": False},
            ],
        },
        # Bun
        "bun": {
            "name": "Bun Toolchain",
            "primary_language": "javascript",
            "supported_languages": ["javascript", "typescript"],
            "components": [
                {"name": "bun", "category": ToolchainCategory.RUNTIME, "required": True},
            ],
        },
        # Deno
        "deno": {
            "name": "Deno Toolchain",
            "primary_language": "javascript",
            "supported_languages": ["javascript", "typescript"],
            "components": [
                {"name": "deno", "category": ToolchainCategory.RUNTIME, "required": True},
            ],
        },
        # .NET
        "dotnet": {
            "name": ".NET SDK",
            "primary_language": "csharp",
            "supported_languages": ["csharp", "fsharp", "vb"],
            "components": [
                {"name": "dotnet", "category": ToolchainCategory.SDK, "required": True},
            ],
        },
        # Java
        "java-maven": {
            "name": "Java (Maven)",
            "primary_language": "java",
            "supported_languages": ["java", "kotlin", "scala"],
            "components": [
                {"name": "java", "category": ToolchainCategory.RUNTIME, "required": True},
                {"name": "javac", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "mvn", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
            ],
        },
        "java-gradle": {
            "name": "Java (Gradle)",
            "primary_language": "java",
            "supported_languages": ["java", "kotlin", "scala"],
            "components": [
                {"name": "java", "category": ToolchainCategory.RUNTIME, "required": True},
                {"name": "javac", "category": ToolchainCategory.COMPILER, "required": True},
                {"name": "gradle", "category": ToolchainCategory.BUILD_SYSTEM, "required": True},
            ],
        },
        # Go
        "go": {
            "name": "Go Toolchain",
            "primary_language": "go",
            "supported_languages": ["go"],
            "components": [
                {"name": "go", "category": ToolchainCategory.COMPILER, "required": True},
            ],
        },
        # Dart/Flutter
        "dart": {
            "name": "Dart SDK",
            "primary_language": "dart",
            "supported_languages": ["dart"],
            "components": [
                {"name": "dart", "category": ToolchainCategory.SDK, "required": True},
            ],
        },
        "flutter": {
            "name": "Flutter SDK",
            "primary_language": "dart",
            "supported_languages": ["dart"],
            "components": [
                {"name": "flutter", "category": ToolchainCategory.SDK, "required": True},
                {"name": "dart", "category": ToolchainCategory.SDK, "required": True},
            ],
        },
        # Embedded
        "embedded-arduino": {
            "name": "Arduino CLI",
            "primary_language": "cpp",
            "supported_languages": ["c", "cpp"],
            "components": [
                {"name": "arduino-cli", "category": ToolchainCategory.FIRMWARE_TOOLCHAIN, "required": True},
            ],
        },
        "embedded-platformio": {
            "name": "PlatformIO",
            "primary_language": "cpp",
            "supported_languages": ["c", "cpp"],
            "components": [
                {"name": "pio", "category": ToolchainCategory.FIRMWARE_TOOLCHAIN, "required": True},
            ],
        },
        # Shader
        "shader-glslang": {
            "name": "glslangValidator",
            "primary_language": "glsl",
            "supported_languages": ["glsl", "hlsl", "spirv"],
            "components": [
                {"name": "glslangValidator", "category": ToolchainCategory.SHADER_COMPILER, "required": True},
                {"name": "spirv-val", "category": ToolchainCategory.SHADER_COMPILER, "required": False},
            ],
        },
        # Database
        "database": {
            "name": "Database CLIs",
            "primary_language": "sql",
            "supported_languages": ["sql"],
            "components": [
                {"name": "psql", "category": ToolchainCategory.DATABASE_CLI, "required": False},
                {"name": "mysql", "category": ToolchainCategory.DATABASE_CLI, "required": False},
                {"name": "sqlite3", "category": ToolchainCategory.DATABASE_CLI, "required": False},
            ],
        },
        # Container
        "docker": {
            "name": "Docker",
            "primary_language": "",
            "supported_languages": [],
            "components": [
                {"name": "docker", "category": ToolchainCategory.CONTAINER_RUNTIME, "required": True},
                {"name": "docker-compose", "category": ToolchainCategory.CONTAINER_RUNTIME, "required": False},
            ],
        },
        "podman": {
            "name": "Podman",
            "primary_language": "",
            "supported_languages": [],
            "components": [
                {"name": "podman", "category": ToolchainCategory.CONTAINER_RUNTIME, "required": True},
            ],
        },
    }

    def _get_tool_info(self, tool_name: str) -> ToolInfo | None:
        """Get tool info from machine capability."""
        if self._machine is None:
            self._machine = self._machine_registry.scan()
        
        for tool in self._machine.tools:
            if tool.name == tool_name:
                return tool
        return None

    def _probe_component(self, tool_name: str, category: ToolchainCategory) -> ToolchainComponent:
        """Probe a single toolchain component."""
        comp = ToolchainComponent()
        comp.name = tool_name
        comp.category = category
        
        tool_info = self._get_tool_info(tool_name)
        
        if tool_info:
            comp.executable_path = tool_info.executable
            comp.version = tool_info.version
            comp.languages = tool_info.languages
            comp.environment = tool_info.category
            comp.probe_command = tool_info.probe_command
            comp.probe_output = tool_info.probe_output
            comp.source = tool_info.source or "unknown"
            comp.requires_admin = tool_info.requires_admin
            comp.last_verified = time.time()
            
            if tool_info.working:
                comp.status = ToolchainStatus.AVAILABLE
            else:
                comp.status = ToolchainStatus.AVAILABLE_BUT_BROKEN
        else:
            # Tool not found in machine capability - check PATH
            exe = shutil.which(tool_name)
            if exe:
                comp.executable_path = exe
                comp.status = ToolchainStatus.UNVERIFIED
            else:
                comp.status = ToolchainStatus.NOT_FOUND
        
        return comp

    def discover_toolchain(self, toolchain_id: str, 
                           machine: MachineCapability | None = None,
                           environments: dict[str, Any] | None = None) -> Toolchain | None:
        """Discover a specific toolchain by ID."""
        if toolchain_id not in self.TOOLCHAIN_DEFINITIONS:
            return None
        
        if machine is None:
            machine = self._machine_registry.scan()
        self._machine = machine
        
        if environments is None:
            self._environments = self._env_registry.discover(machine)
        else:
            self._environments = environments
        
        definition = self.TOOLCHAIN_DEFINITIONS[toolchain_id]
        tc = Toolchain()
        tc.id = toolchain_id
        tc.name = definition["name"]
        tc.primary_language = definition["primary_language"]
        tc.supported_languages = definition["supported_languages"]
        
        required_count = 0
        required_available = 0
        any_available = 0

        for comp_def in definition["components"]:
            comp_name = comp_def["name"]
            comp_category = comp_def["category"]
            required = comp_def.get("required", False)

            # Category is a single ToolchainCategory; tolerate list/tuple for forward-compat.
            if isinstance(comp_category, (list, tuple)) and comp_category:
                cat = comp_category[0]
            else:
                cat = comp_category

            comp = self._probe_component(comp_name, cat)
            comp.metadata["required"] = required
            tc.components.append(comp)

            if comp.status == ToolchainStatus.AVAILABLE:
                any_available += 1
                if required:
                    required_available += 1
            if required:
                required_count += 1

        # Determine overall status: all REQUIRED components available -> AVAILABLE.
        # Optional components never break an otherwise complete toolchain.
        if required_count > 0 and required_available == required_count:
            tc.status = ToolchainStatus.AVAILABLE
        elif any_available > 0:
            tc.status = ToolchainStatus.AVAILABLE_BUT_BROKEN
        else:
            tc.status = ToolchainStatus.NOT_FOUND
        
        # Find compatible environments
        tc.environments = [e.identifier for e in self._environments.values() if e.health == "HEALTHY"]
        
        # Calculate rank (lower is better)
        tc.rank = self._calculate_rank(tc)
        
        self._toolchains[toolchain_id] = tc
        return tc

    def _calculate_rank(self, tc: Toolchain) -> int:
        """Calculate toolchain rank for selection (lower is better)."""
        rank = 0
        
        # Prefer native toolchains
        if "WINDOWS_NATIVE" in tc.environments and sys.platform == "win32":
            rank -= 10
        
        # Prefer complete toolchains
        required = sum(1 for c in tc.components if c.metadata.get("required", True))
        available = sum(1 for c in tc.components if c.status == ToolchainStatus.AVAILABLE)
        if required > 0:
            rank += (required - available) * 100
        
        # Prefer newer versions (simplified)
        for comp in tc.components:
            if comp.version:
                # Extract major version
                try:
                    major = int(comp.version.split(".")[0].lstrip("vV"))
                    if major >= 20:  # Modern versions
                        rank -= 1
                except Exception:
                    pass
        
        return rank

    def discover_all(self, machine: MachineCapability | None = None,
                     environments: dict[str, Any] | None = None) -> dict[str, Toolchain]:
        """Discover all defined toolchains."""
        results = {}
        for tc_id in self.TOOLCHAIN_DEFINITIONS:
            tc = self.discover_toolchain(tc_id, machine, environments)
            if tc:
                results[tc_id] = tc
        return results

    def get(self, toolchain_id: str) -> Toolchain | None:
        """Get a discovered toolchain by ID."""
        return self._toolchains.get(toolchain_id)

    def list(self, language: str = "", status: ToolchainStatus | None = None,
             category: ToolchainCategory | None = None) -> list[Toolchain]:
        """List toolchains with optional filters."""
        results = []
        for tc in self._toolchains.values():
            if language and language not in tc.supported_languages:
                continue
            if status and tc.status != status:
                continue
            if category:
                # Check if any component matches category
                if not any(c.category == category for c in tc.components):
                    continue
            results.append(tc)
        return sorted(results, key=lambda t: (t.rank, t.id))

    def list_available(self, language: str = "") -> list[Toolchain]:
        """List only available toolchains."""
        return self.list(language=language, status=ToolchainStatus.AVAILABLE)

    def find_best_for_language(self, language: str) -> Toolchain | None:
        """Find the best available toolchain for a language."""
        candidates = self.list_available(language=language)
        if not candidates:
            return None
        return min(candidates, key=lambda t: t.rank)

    def find_all_for_language(self, language: str) -> list[Toolchain]:
        """Find all available toolchains for a language, ranked."""
        return self.list_available(language=language)

    def to_dict(self) -> dict[str, Any]:
        """Convert all toolchains to dictionary."""
        return {k: asdict(v) for k, v in self._toolchains.items()}


def discover_toolchains(machine: MachineCapability | None = None,
                        environments: dict[str, Any] | None = None) -> dict[str, Toolchain]:
    """Convenience function for one-shot discovery."""
    registry = ToolchainRegistry()
    return registry.discover_all(machine, environments)


if __name__ == "__main__":
    import json
    from machine_capability import discover_machine_capability
    from execution_environment import discover_execution_environments
    
    machine = discover_machine_capability(force=True)
    environments = discover_execution_environments(machine)
    registry = ToolchainRegistry()
    toolchains = registry.discover_all(machine, environments)
    print(json.dumps(registry.to_dict(), indent=2, default=str))