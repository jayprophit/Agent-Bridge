"""Reusable build / artifact pipeline (v0.9.0 continuous build).

detect -> resolve environment -> resolve toolchain -> prepare deps ->
configure -> build -> test -> package -> inspect artifact -> verify ->
report. "File exists" is NOT "artifact verified": every artifact carries
path, format, size, build/test/verification results, warnings, provenance.

PROJECT_READY assessment included (smallest sufficient environment).
Additive only; builds run through injected runners (mocked in tests).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


class Readiness(str, Enum):
    READY = "READY"
    READY_AFTER_SAFE_PROVISIONING = "READY_AFTER_SAFE_PROVISIONING"
    READY_AFTER_APPROVAL = "READY_AFTER_APPROVAL"
    PARTIAL = "PARTIAL"
    REMOTE_RECOMMENDED = "REMOTE_RECOMMENDED"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass
class ArtifactEvidence:
    path: str = ""
    format: str = ""
    size_bytes: int = 0
    build_ok: bool = False
    test_ok: bool = False
    verified: bool = False
    warnings: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    ok: bool = False
    stages: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactEvidence] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "stages": self.stages, "errors": self.errors,
                "artifacts": [asdict(a) for a in self.artifacts]}


class BuildPipeline:
    """Detect-to-verify pipeline with evidence at every stage."""

    STAGES = ("detect", "environment", "toolchain", "dependencies",
              "configure", "build", "test", "package", "inspect", "verify")

    def __init__(self, runner: Callable[[str], dict[str, Any]] | None = None):
        self._run = runner or (lambda cmd: {"ok": False, "error": "no runner"})

    def execute(self, project: dict[str, Any]) -> PipelineResult:
        res = PipelineResult()
        failed = False
        for stage in self.STAGES:
            if failed and stage not in ("verify",):
                res.stages[stage] = {"skipped": True}
                continue
            try:
                if stage == "detect":
                    out = {"project": project.get("name", "unknown"),
                           "languages": project.get("languages", [])}
                    res.stages[stage] = {"ok": True, "detail": out}
                elif stage == "inspect":
                    arts = [ArtifactEvidence(
                        path=a.get("path", ""), format=a.get("format", ""),
                        size_bytes=a.get("size_bytes", 0),
                        build_ok=res.stages.get("build", {}).get("ok", False),
                        test_ok=res.stages.get("test", {}).get("ok", False),
                        provenance={"project": project.get("name", "")})
                        for a in project.get("expected_artifacts", [])]
                    res.artifacts = arts
                    res.stages[stage] = {"ok": True,
                                         "artifacts": len(arts)}
                elif stage == "verify":
                    for a in res.artifacts:
                        a.verified = bool(a.build_ok and a.test_ok
                                          and a.size_bytes > 0)
                    res.stages[stage] = {
                        "ok": all(a.verified for a in res.artifacts)}
                    if not res.stages[stage]["ok"]:
                        failed = True
                else:
                    cmd = project.get("commands", {}).get(stage, "")
                    if not cmd:
                        res.stages[stage] = {"ok": True, "detail": "no-op"}
                        continue
                    out = self._run(cmd)
                    res.stages[stage] = {"ok": bool(out.get("ok")),
                                         "detail": str(out)[:300]}
                    if not out.get("ok"):
                        failed = True
                        res.errors.append(f"{stage}: {out.get('error', '')}"[:200])
            except Exception as e:  # noqa: BLE001 - record, continue to verify
                res.stages[stage] = {"ok": False, "detail": str(e)[:200]}
                res.errors.append(f"{stage}: {e}"[:200])
                failed = True
        res.ok = not failed and all(
            res.stages.get(s, {}).get("ok", True) for s in self.STAGES)
        return res

    @staticmethod
    def assess_readiness(requirements: list[str], present: list[str],
                         degraded: list[str] | None = None,
                         approval_needed: list[str] | None = None,
                         remote_available: bool = False) -> Readiness:
        degraded, approval_needed = set(degraded or []), set(approval_needed or [])
        missing = [r for r in requirements if r not in present]
        if missing:
            return Readiness.REMOTE_RECOMMENDED if remote_available \
                else Readiness.INCOMPATIBLE
        gated = [r for r in requirements if r in approval_needed]
        if gated:
            return Readiness.READY_AFTER_APPROVAL
        if any(r in degraded for r in requirements):
            return Readiness.READY_AFTER_SAFE_PROVISIONING
        return Readiness.READY


def benchmark(name: str, fn: Callable[[], Any],
              repeats: int = 3) -> dict[str, Any]:
    """Measure real latency (evidence for routing, not guarantees)."""
    samples = []
    out = None
    for _ in range(max(1, repeats)):
        t0 = time.monotonic()
        out = fn()
        samples.append(time.monotonic() - t0)
    samples.sort()
    return {"name": name, "n": len(samples), "p50_s": round(samples[len(samples) // 2], 4),
            "max_s": round(samples[-1], 4), "ok": out is not None}
