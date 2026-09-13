"""Tool Selection Engine (v0.9.0 Phase 1).

Minimal deterministic selector:

  PROJECT REQUIREMENT + AVAILABLE MACHINE CAPABILITIES = COMPATIBLE TOOLCHAIN OPTIONS.

No hard-coded vendor wins. Rank with documented criteria. Allow future user override.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from toolchain_registry import Toolchain, ToolchainRegistry, ToolchainStatus


@dataclass
class ProjectRequirement:
    """What a project component needs."""
    language: str = ""
    min_version: str = ""  # e.g., "17" for C++17, "3.10" for Python
    build_system: str = ""  # e.g., cmake, meson, cargo, npm
    test_framework: str = ""
    environment: str = ""  # preferred execution environment id
    standards: list[str] = field(default_factory=list)  # e.g., ["c++17"]
    constraints: dict[str, Any] = field(default_factory=dict)
    user_override_toolchain: str = ""  # future user override


@dataclass
class ToolchainOption:
    toolchain_id: str = ""
    name: str = ""
    score: int = 0  # lower is better
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    compatible: bool = False


def _parse_version(text: str) -> tuple[int, ...]:
    """Extract leading numeric version tuple from free-form version output."""
    import re
    m = re.search(r"(\d+(?:\.\d+)*)", text or "")
    if not m:
        return ()
    try:
        return tuple(int(x) for x in m.group(1).split(".")[:3])
    except ValueError:
        return ()


def _meets_min_version(actual: str, minimum: str) -> bool:
    if not minimum:
        return True
    a = _parse_version(actual)
    b = _parse_version(minimum)
    if not a or not b:
        return True  # cannot determine -> do not reject
    # Compare with padding
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a >= b


class ToolSelectionEngine:
    """Deterministic toolchain selector."""

    def __init__(self, registry: ToolchainRegistry | None = None):
        self._registry = registry or ToolchainRegistry()

    def recommend(
        self,
        requirement: ProjectRequirement,
        toolchains: list[Toolchain] | None = None,
    ) -> list[ToolchainOption]:
        """Return ranked compatible toolchain options for a requirement."""
        # User override wins (if it exists)
        if requirement.user_override_toolchain:
            tc = self._registry.get(requirement.user_override_toolchain)
            if tc is None and toolchains:
                tc = next((t for t in toolchains if t.id == requirement.user_override_toolchain), None)
            if tc is not None:
                return [ToolchainOption(
                    toolchain_id=tc.id, name=tc.name, score=-1000,
                    reasons=["explicit user override"], compatible=True,
                )]

        if toolchains is None:
            toolchains = self._registry.list_available(language=requirement.language) \
                if requirement.language else self._registry.list()

        options: list[ToolchainOption] = []
        for tc in toolchains:
            # Language filter
            if requirement.language and requirement.language not in tc.supported_languages:
                continue
            opt = ToolchainOption(toolchain_id=tc.id, name=tc.name, score=tc.rank)
            opt.reasons.append(f"supports {requirement.language or 'multiple languages'}")

            # Only consider usable toolchains
            if tc.status != ToolchainStatus.AVAILABLE:
                opt.compatible = False
                opt.warnings.append(f"toolchain status is {tc.status}")
                opt.score += 10000
                options.append(opt)
                continue

            # Environment preference (soft constraint)
            if requirement.environment:
                if requirement.environment in tc.environments:
                    opt.score -= 5
                    opt.reasons.append(f"available in {requirement.environment}")
                else:
                    opt.score += 50
                    opt.warnings.append(f"not verified in {requirement.environment}")

            # Build system preference (soft constraint)
            if requirement.build_system:
                names = [c.name.lower() for c in tc.components]
                if requirement.build_system.lower() in names:
                    opt.score -= 5
                    opt.reasons.append(f"includes {requirement.build_system}")
                else:
                    opt.score += 20
                    opt.warnings.append(f"missing preferred build system {requirement.build_system}")

            # Min version check against primary compiler/interpreter component
            if requirement.min_version:
                primary = next(
                    (c for c in tc.components
                     if c.status == ToolchainStatus.AVAILABLE and c.version), None)
                if primary and not _meets_min_version(primary.version, requirement.min_version):
                    opt.score += 1000
                    opt.warnings.append(
                        f"{primary.name} {primary.version} below minimum {requirement.min_version}")
                    opt.compatible = False
                    options.append(opt)
                    continue
                elif primary:
                    opt.reasons.append(f"{primary.name} {primary.version} meets minimum")

            # Standards note (informational only in Phase 1)
            for s in requirement.standards:
                opt.reasons.append(f"standard {s} assumed supported (verify at build)")

            opt.compatible = opt.score < 1000
            options.append(opt)

        # Deterministic ordering: compatible first, then score, then id
        options.sort(key=lambda o: ((0 if o.compatible else 1), o.score, o.toolchain_id))
        return options

    def best(self, requirement: ProjectRequirement,
             toolchains: list[Toolchain] | None = None) -> ToolchainOption | None:
        opts = self.recommend(requirement, toolchains)
        for o in opts:
            if o.compatible:
                return o
        return None


def recommend_toolchain(requirement: ProjectRequirement,
                        toolchains: list[Toolchain] | None = None) -> list[dict[str, Any]]:
    """Convenience function returning plain dicts."""
    engine = ToolSelectionEngine()
    return [asdict(o) for o in engine.recommend(requirement, toolchains)]


if __name__ == "__main__":
    import json
    eng = ToolSelectionEngine()
    req = ProjectRequirement(language="cpp", build_system="cmake", standards=["c++17"])
    # Note: requires prior discovery; empty registry yields empty list (no crash).
    print(json.dumps([asdict(o) for o in eng.recommend(req, [])], indent=2))
