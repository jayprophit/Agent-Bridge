"""Language Registry (v0.9.0 Phase 1).

Language capability contracts - maps languages to their toolchains,
build/test/debug support, and runtime requirements.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

from toolchain_registry import ToolchainRegistry, Toolchain, ToolchainCategory, ToolchainStatus
from machine_capability import MachineCapability, discover_machine_capability
from execution_environment import ExecutionEnvironment, discover_execution_environments


class LanguageFamily(Enum):
    """Recognized language families."""
    C = "c"
    CPP = "cpp"
    RUST = "rust"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    SWIFT = "swift"
    KOTLIN = "kotlin"
    DART = "dart"
    SQL = "sql"
    HTML = "html"
    CSS = "css"
    SHELL = "shell"
    POWERSHELL = "powershell"
    ASSEMBLY = "assembly"
    GLSL = "glsl"
    ARDUINO = "arduino"
    OTHER = "other"


class SupportLevel(IntEnum):
    """Level of support for a capability (ordered: higher is better)."""
    NONE = 0                # No support
    MINIMAL = 1             # Basic support only
    PARTIAL = 2             # Some capabilities available
    FULL = 3                # All capabilities available


@dataclass
class LanguageCapability:
    """Capabilities for a specific language."""
    language: str = ""
    family: LanguageFamily = LanguageFamily.OTHER
    aliases: list[str] = field(default_factory=list)
    file_extensions: list[str] = field(default_factory=list)
    
    # Toolchain support
    available_toolchains: list[Toolchain] = field(default_factory=list)
    recommended_toolchain: str = ""
    
    # Capability support levels
    build_support: SupportLevel = SupportLevel.NONE
    test_support: SupportLevel = SupportLevel.NONE
    debug_support: SupportLevel = SupportLevel.NONE
    format_support: SupportLevel = SupportLevel.NONE
    lint_support: SupportLevel = SupportLevel.NONE
    language_server_support: SupportLevel = SupportLevel.NONE
    package_management_support: SupportLevel = SupportLevel.NONE
    
    # Runtime requirements
    runtime_requirements: list[str] = field(default_factory=list)
    typical_runtimes: list[str] = field(default_factory=list)
    
    # Metadata
    maturity: str = "stable"  # stable, beta, experimental
    notes: str = ""


# Language definitions with their characteristics
LANGUAGE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "c": {
        "family": LanguageFamily.C,
        "aliases": ["c"],
        "extensions": [".c", ".h"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.DEBUGGER],
        "runtimes": [],
        "maturity": "stable",
    },
    "cpp": {
        "family": LanguageFamily.CPP,
        "aliases": ["c++", "cxx"],
        "extensions": [".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hxx", ".h++", ".hh"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.DEBUGGER],
        "runtimes": [],
        "maturity": "stable",
    },
    "rust": {
        "family": LanguageFamily.RUST,
        "aliases": ["rs"],
        "extensions": [".rs"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": [],
        "maturity": "stable",
    },
    "python": {
        "family": LanguageFamily.PYTHON,
        "aliases": ["py"],
        "extensions": [".py", ".pyw", ".pyi"],
        "toolchain_categories": [ToolchainCategory.INTERPRETER, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER, ToolchainCategory.RUNTIME],
        "runtimes": ["python", "pypy", "conda"],
        "maturity": "stable",
    },
    "javascript": {
        "family": LanguageFamily.JAVASCRIPT,
        "aliases": ["js", "ecmascript"],
        "extensions": [".js", ".mjs", ".cjs", ".jsx"],
        "toolchain_categories": [ToolchainCategory.RUNTIME, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["node", "bun", "deno"],
        "maturity": "stable",
    },
    "typescript": {
        "family": LanguageFamily.TYPESCRIPT,
        "aliases": ["ts"],
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.RUNTIME, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["node", "bun", "deno"],
        "maturity": "stable",
    },
    "java": {
        "family": LanguageFamily.JAVA,
        "aliases": [],
        "extensions": [".java"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.RUNTIME, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["jre", "jdk", "graalvm"],
        "maturity": "stable",
    },
    "csharp": {
        "family": LanguageFamily.CSHARP,
        "aliases": ["cs", "c#"],
        "extensions": [".cs"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.RUNTIME, ToolchainCategory.SDK, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": [".net", ".net framework", "mono"],
        "maturity": "stable",
    },
    "go": {
        "family": LanguageFamily.GO,
        "aliases": ["golang"],
        "extensions": [".go"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": [],
        "maturity": "stable",
    },
    "swift": {
        "family": LanguageFamily.SWIFT,
        "aliases": [],
        "extensions": [".swift"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": [],
        "maturity": "stable",
    },
    "kotlin": {
        "family": LanguageFamily.KOTLIN,
        "aliases": ["kt"],
        "extensions": [".kt", ".kts"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.RUNTIME, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["jvm", "kotlin-native", "kotlin-js"],
        "maturity": "stable",
    },
    "dart": {
        "family": LanguageFamily.DART,
        "aliases": [],
        "extensions": [".dart"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.RUNTIME, ToolchainCategory.SDK, ToolchainCategory.BUILD_SYSTEM, ToolchainCategory.PACKAGE_MANAGER, ToolchainCategory.TEST_FRAMEWORK, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["dart-vm", "flutter"],
        "maturity": "stable",
    },
    "sql": {
        "family": LanguageFamily.SQL,
        "aliases": [],
        "extensions": [".sql"],
        "toolchain_categories": [ToolchainCategory.DATABASE_CLI],
        "runtimes": ["postgresql", "mysql", "sqlite", "sqlserver"],
        "maturity": "stable",
    },
    "html": {
        "family": LanguageFamily.HTML,
        "aliases": [],
        "extensions": [".html", ".htm", ".xhtml"],
        "toolchain_categories": [ToolchainCategory.LANGUAGE_SERVER, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER],
        "runtimes": ["browser"],
        "maturity": "stable",
    },
    "css": {
        "family": LanguageFamily.CSS,
        "aliases": [],
        "extensions": [".css", ".scss", ".sass", ".less"],
        "toolchain_categories": [ToolchainCategory.LANGUAGE_SERVER, ToolchainCategory.FORMATTER, ToolchainCategory.LINTER],
        "runtimes": ["browser"],
        "maturity": "stable",
    },
    "shell": {
        "family": LanguageFamily.SHELL,
        "aliases": ["bash", "sh"],
        "extensions": [".sh", ".bash"],
        "toolchain_categories": [ToolchainCategory.INTERPRETER, ToolchainCategory.LINTER],
        "runtimes": ["bash", "zsh", "fish"],
        "maturity": "stable",
    },
    "powershell": {
        "family": LanguageFamily.POWERSHELL,
        "aliases": ["ps1", "psm1", "psd1"],
        "extensions": [".ps1", ".psm1", ".psd1"],
        "toolchain_categories": [ToolchainCategory.INTERPRETER, ToolchainCategory.LINTER, ToolchainCategory.LANGUAGE_SERVER],
        "runtimes": ["powershell", "pwsh"],
        "maturity": "stable",
    },
    "assembly": {
        "family": LanguageFamily.ASSEMBLY,
        "aliases": ["asm"],
        "extensions": [".asm", ".s", ".S"],
        "toolchain_categories": [ToolchainCategory.COMPILER, ToolchainCategory.DEBUGGER],
        "runtimes": [],
        "maturity": "stable",
    },
    "glsl": {
        "family": LanguageFamily.GLSL,
        "aliases": ["hlsl", "spirv", "wgsl"],
        "extensions": [".glsl", ".vert", ".frag", ".vs", ".fs", ".hlsl", ".spirv", ".wgsl"],
        "toolchain_categories": [ToolchainCategory.SHADER_COMPILER],
        "runtimes": ["gpu", "vulkan", "opengl", "directx", "metal", "webgpu"],
        "maturity": "stable",
    },
    "arduino": {
        "family": LanguageFamily.ARDUINO,
        "aliases": ["ino"],
        "extensions": [".ino", ".pde"],
        "toolchain_categories": [ToolchainCategory.FIRMWARE_TOOLCHAIN, ToolchainCategory.COMPILER, ToolchainCategory.BUILD_SYSTEM],
        "runtimes": ["avr", "arm", "esp8266", "esp32", "risc-v"],
        "maturity": "stable",
    },
}


class LanguageRegistry:
    """Registry for language capabilities and toolchain mapping."""

    def __init__(self):
        self._capabilities: dict[str, LanguageCapability] = {}
        self._toolchain_registry = ToolchainRegistry()
        self._machine: MachineCapability | None = None
        self._environments: dict[str, ExecutionEnvironment] = {}
        self._toolchains: dict[str, Toolchain] = {}

    def _ensure_discovered(self) -> None:
        """Ensure toolchains and machine are discovered."""
        if self._machine is None:
            self._machine = discover_machine_capability()
        if not self._environments:
            self._environments = discover_execution_environments(self._machine)
        if not self._toolchains:
            self._toolchains = self._toolchain_registry.discover_all(self._machine, self._environments)

    def get_capability(self, language: str) -> LanguageCapability | None:
        """Get capability for a language."""
        self._ensure_discovered()
        
        if language in self._capabilities:
            return self._capabilities[language]
        
        # Build capability from definition
        definition = LANGUAGE_DEFINITIONS.get(language.lower())
        if not definition:
            return None
        
        cap = LanguageCapability()
        cap.language = language
        cap.family = definition["family"]
        cap.aliases = definition["aliases"]
        cap.file_extensions = definition["extensions"]
        cap.typical_runtimes = definition["runtimes"]
        cap.maturity = definition["maturity"]
        
        # Find available toolchains for this language
        for tc in self._toolchains.values():
            if language in tc.supported_languages:
                cap.available_toolchains.append(tc)
        
        # Find recommended (best ranked) toolchain
        if cap.available_toolchains:
            best = min(cap.available_toolchains, key=lambda t: t.rank)
            cap.recommended_toolchain = best.id
        
        # Determine support levels based on available toolchains
        cap.build_support = self._assess_support(cap, ToolchainCategory.BUILD_SYSTEM)
        cap.test_support = self._assess_support(cap, ToolchainCategory.TEST_FRAMEWORK)
        cap.debug_support = self._assess_support(cap, ToolchainCategory.DEBUGGER)
        cap.format_support = self._assess_support(cap, ToolchainCategory.FORMATTER)
        cap.lint_support = self._assess_support(cap, ToolchainCategory.LINTER)
        cap.language_server_support = self._assess_support(cap, ToolchainCategory.LANGUAGE_SERVER)
        cap.package_management_support = self._assess_support(cap, ToolchainCategory.PACKAGE_MANAGER)
        
        self._capabilities[language] = cap
        return cap

    def _assess_support(self, cap: LanguageCapability, category: ToolchainCategory) -> SupportLevel:
        """Assess support level for a category."""
        available = 0
        total = 0
        
        for tc in cap.available_toolchains:
            if tc.status != ToolchainStatus.AVAILABLE:
                continue
            for comp in tc.components:
                if comp.category == category:
                    total += 1
                    if comp.status == ToolchainStatus.AVAILABLE:
                        available += 1
        
        if total == 0:
            return SupportLevel.NONE
        elif available == total:
            return SupportLevel.FULL
        elif available > 0:
            return SupportLevel.PARTIAL
        return SupportLevel.MINIMAL

    def get_all_capabilities(self) -> dict[str, LanguageCapability]:
        """Get capabilities for all known languages."""
        self._ensure_discovered()
        for lang in LANGUAGE_DEFINITIONS:
            self.get_capability(lang)
        return self._capabilities

    def list_supported_languages(self, min_support: SupportLevel = SupportLevel.MINIMAL) -> list[str]:
        """List languages with at least minimum support."""
        self._ensure_discovered()
        result = []
        for lang in LANGUAGE_DEFINITIONS:
            cap = self.get_capability(lang)
            if cap and any([
                cap.build_support >= min_support,
                cap.test_support >= min_support,
                cap.debug_support >= min_support,
            ]):
                result.append(lang)
        return sorted(result)

    def list_fully_supported(self) -> list[str]:
        """List languages with full build+test support."""
        return self.list_supported_languages(SupportLevel.FULL)

    def find_language_for_extension(self, extension: str) -> str | None:
        """Find language by file extension."""
        for lang, defn in LANGUAGE_DEFINITIONS.items():
            if extension.lower() in [e.lower() for e in defn["extensions"]]:
                return lang
        return None

    def find_language_for_file(self, filepath: str) -> str | None:
        """Find language for a file path."""
        ext = Path(filepath).suffix.lower()
        return self.find_language_for_extension(ext)

    def get_toolchain_for_language(self, language: str, 
                                    preferred_env: str | None = None) -> Toolchain | None:
        """Get recommended toolchain for a language in an environment."""
        cap = self.get_capability(language)
        if not cap or not cap.recommended_toolchain:
            return None
        
        tc = self._toolchains.get(cap.recommended_toolchain)
        if tc and preferred_env and preferred_env not in tc.environments:
            # Find alternative in preferred environment
            for alt_tc in cap.available_toolchains:
                if preferred_env in alt_tc.environments:
                    return alt_tc
        return tc

    def get_available_toolchains_for_language(self, language: str) -> list[Toolchain]:
        """Get all available toolchains for a language."""
        cap = self.get_capability(language)
        if not cap:
            return []
        return [tc for tc in cap.available_toolchains if tc.status == ToolchainStatus.AVAILABLE]

    def to_dict(self) -> dict[str, Any]:
        """Convert all capabilities to dictionary."""
        return {k: asdict(v) for k, v in self._capabilities.items()}


def discover_language_capabilities(machine: MachineCapability | None = None,
                                    environments: dict[str, ExecutionEnvironment] | None = None) -> dict[str, LanguageCapability]:
    """Convenience function for one-shot discovery."""
    registry = LanguageRegistry()
    if machine:
        registry._machine = machine
    if environments:
        registry._environments = environments
    return registry.get_all_capabilities()


if __name__ == "__main__":
    import json
    from machine_capability import discover_machine_capability
    from execution_environment import discover_execution_environments
    
    machine = discover_machine_capability(force=True)
    environments = discover_execution_environments(machine)
    registry = LanguageRegistry()
    registry._machine = machine
    registry._environments = environments
    caps = registry.get_all_capabilities()
    print(json.dumps(registry.to_dict(), indent=2, default=str))