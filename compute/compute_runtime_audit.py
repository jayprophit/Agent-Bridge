"""Compute-Runtime Audit (§19–§25 of the lifecycle/verification directive).

WHY THIS MODULE EXISTS

The Hybrid Cloud phase needs to know what each inference runtime is FOR
before it can place a model on one. Ollama is installed and working today;
vLLM, SGLang and llama.cpp are not. Deciding between them by marketing
claims is exactly the mistake §74 forbids — routing must follow measured
evidence, and an absent runtime cannot be measured.

So this module records what is KNOWN, what is MEASURED, and what is merely
DESIGNED, and keeps those three states separate. A runtime that is not
installed is reported as NOT_INSTALLED, never as "available".

WHAT IS DELIBERATELY NOT DONE (§91)

Runtimes are NOT installed, downloaded or benchmarked here. "Do not install
all runtimes blindly" — each candidate is evaluated for its intended role,
and only what the current hardware and the current phase justify is
recommended. The audit is the decision input, not the deployment.

HONESTY RULES (§139)

Evidence states are enforced by the vocabulary, not by convention:

    INSTALLED_VERIFIED  — the runtime answered a real probe on this host
    DECLARED           — a capability is claimed by documentation/source
    DESIGNED           — a role is assigned, no runtime present
    NOT_INSTALLED      — probed and absent
    RESEARCH_ONLY      — evaluated, no current Aetherius role
    SUPERSEDED         — replaced by a canonical owner

A DECLARED capability is never reported as INSTALLED_VERIFIED. Nothing in
this module may say "supported" about a runtime it did not probe.
"""

from __future__ import annotations

import shutil
import subprocess
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

# --------------------------------------------------------------------------
# Evidence vocabulary (§139) — the states this audit is allowed to report
# --------------------------------------------------------------------------


class RuntimeState(str, Enum):
    INSTALLED_VERIFIED = "INSTALLED_VERIFIED"
    DECLARED = "DECLARED"
    DESIGNED = "DESIGNED"
    NOT_INSTALLED = "NOT_INSTALLED"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    SUPERSEDED = "SUPERSEDED"


class ReuseDecision(str, Enum):
    """§25 — the decision each fork/runtime is being fed into."""

    KEEP_DEPENDENCY = "KEEP_DEPENDENCY"
    PRIMARY_RUNTIME = "PRIMARY_RUNTIME"
    CLOUD_SERVING_TARGET = "CLOUD_SERVING_TARGET"
    FUTURE_FIRST_PARTY_BACKEND = "FUTURE_FIRST_PARTY_BACKEND"
    REFERENCE_FOR_AETHERIUS_RUNTIME = "REFERENCE_FOR_AETHERIUS_RUNTIME"
    TEMPORARY_RUNTIME = "TEMPORARY_RUNTIME"
    RESEARCH_ONLY = "RESEARCH_ONLY"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


# --------------------------------------------------------------------------
# §91 runtime attribute vocabulary
#
# The fields a runtime record must answer, per the directive. Recording them
# as an explicit tuple means a runtime cannot quietly omit an axis.
# --------------------------------------------------------------------------

RUNTIME_ATTRIBUTES: tuple[str, ...] = (
    "platform",
    "cpu_support",
    "gpu_support",
    "supported_architectures",
    "supported_formats",
    "quantization_support",
    "tool_call_support",
    "continuous_batching",
    "prefix_caching",
    "kv_cache_support",
    "distributed_support",
    "memory_use",
    "startup_time",
    "throughput",
    "licence",
    "maintenance",
    "security",
    "aetherius_suitability",
)


@dataclass
class RuntimeRecord:
    """One inference runtime, evaluated for a stated role (§91, §25).

    `declared` holds capability claims from documentation — honest about
    their provenance, and never promoted to verified. `measured` holds what
    a real probe on this host returned. The distinction is the whole point:
    §91 forbids installing runtimes blindly, so the audit must not pretend
    an unmeasured runtime was measured.
    """

    runtime_id: str
    name: str
    upstream: str = ""
    licence: str = ""
    state: RuntimeState = RuntimeState.DESIGNED
    # WHAT it is for (§19)
    purpose: str = ""
    # WHEN it is used (§19) — the triggering condition, not a schedule
    trigger: str = ""
    # WHERE it belongs (§19) — the owning plane/component
    owner: str = ""
    # HOW it is integrated (§19)
    integration: str = ""
    reuse_decision: ReuseDecision = ReuseDecision.RESEARCH_ONLY
    declared: dict[str, Any] = field(default_factory=dict)
    measured: dict[str, Any] = field(default_factory=dict)
    # Retirement/integration follow-ups (§25)
    integration_path: str = ""
    migration_task: str = ""
    test_requirement: str = ""
    retirement_condition: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return OrderedDict([
            ("runtime_id", self.runtime_id),
            ("name", self.name),
            ("upstream", self.upstream),
            ("licence", self.licence),
            ("state", self.state.value),
            ("reuse_decision", self.reuse_decision.value),
            ("what", self.purpose),
            ("when", self.trigger),
            ("where", self.owner),
            ("how", self.integration),
            ("declared", OrderedDict(sorted(self.declared.items()))),
            ("measured", OrderedDict(sorted(self.measured.items()))),
            ("integration_path", self.integration_path),
            ("migration_task", self.migration_task),
            ("test_requirement", self.test_requirement),
            ("retirement_condition", self.retirement_condition),
            ("notes", list(self.notes)),
        ])

    @property
    def evidence_gap(self) -> list[str]:
        """Attributes claimed but not measured — the honest gap list.

        A runtime whose `declared` says it supports CUDA while `measured`
        is empty is not verified on that axis. This property exists so the
        gap is computed rather than remembered.
        """
        if self.state is RuntimeState.INSTALLED_VERIFIED:
            return []
        return sorted(self.declared)


# --------------------------------------------------------------------------
# Probing — the ONLY place a runtime is touched
# --------------------------------------------------------------------------


def _probe_command(args: list[str], timeout: float = 5.0) -> dict[str, Any]:
    """Run a version probe, capturing output without ever raising.

    `present` means the executable resolves AND answered a version request
    with a successful exit. A module that imports but fails to start — vLLM
    and SGLang both answer `python -m vllm` with exit 1 when the GPU stack
    is absent — is NOT a usable runtime, and counting it as installed would
    be the exact false claim §139 forbids.
    """
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout,
            shell=False, check=False)
    except FileNotFoundError:
        return {"present": False, "reason": "not on PATH"}
    except subprocess.TimeoutExpired:
        return {"present": True, "answered": False,
                "reason": "probe timed out"}
    except Exception as exc:  # noqa: BLE001 - probing must not raise
        return {"present": True, "answered": False,
                "reason": f"probe failed: {exc}"}
    out = (proc.stdout or "").strip().splitlines()
    answered = proc.returncode == 0
    return {"present": bool(args) and answered,
            "resolved": True,
            "answered": answered,
            "reason": "answered" if answered
                      else f"resolved but exited {proc.returncode}",
            "exit_code": proc.returncode,
            "first_line": out[0] if out else ""}


class RuntimeProber:
    """Probes the host for installed inference runtimes.

    Read-only: version probes and PATH lookups only. Nothing is installed,
    downloaded or started (§91).
    """

    DEFAULT_PROBES: dict[str, list[str]] = {
        "ollama": ["ollama", "--version"],
        "llama_cpp": ["llama-server", "--version"],
        "vllm": ["python", "-m", "vllm", "--version"],
        "sglang": ["python", "-m", "sglang", "--version"],
    }

    def __init__(self, runner: Callable[..., dict[str, Any]] | None = None,
                 which: Callable[[str], str | None] | None = None) -> None:
        self._runner = runner or _probe_command
        self._which = which or (lambda name: shutil.which(name))

    def probe(self, runtime_id: str) -> dict[str, Any]:
        args = self.DEFAULT_PROBES.get(runtime_id)
        if not args:
            return {"present": False, "reason": "no probe defined"}
        if self._which(args[0]) is None:
            return {"present": False, "reason": f"{args[0]} not on PATH"}
        return self._runner(args)

    def probe_all(self, runtime_ids: list[str] | None = None) -> dict[str, Any]:
        ids = runtime_ids or list(self.DEFAULT_PROBES)
        return {rid: self.probe(rid) for rid in ids}


# --------------------------------------------------------------------------
# The audit
# --------------------------------------------------------------------------


class ComputeRuntimeAudit:
    """Answers WHAT/WHEN/WHERE/HOW for each candidate runtime (§19).

    Feed it the existing fork/runtime inventory and it reconciles against
    what the host actually has, so the output distinguishes a runtime that
    is installed and working from one that is only a good idea.
    """

    def __init__(self, prober: RuntimeProber | None = None) -> None:
        self.prober = prober or RuntimeProber()

    # -- the candidate set (§20–§23) ---------------------------------------
    @staticmethod
    def candidate_runtimes() -> list[RuntimeRecord]:
        """The §20–§23 candidate set, honestly scoped.

        Each record states its intended role for THIS programme and THIS
        hardware. Roles are recommendations, not installations: vLLM is
        recorded as the cloud serving target because that is where it earns
        its keep, not because it is present on a 16 GB CPU-first desktop.
        """
        return [
            RuntimeRecord(
                runtime_id="ollama",
                name="Ollama",
                upstream="ollama/ollama",
                licence="MIT",
                state=RuntimeState.INSTALLED_VERIFIED,
                purpose="Current local runtime: model pull, lifecycle, HTTP API",
                trigger="Any local inference request on the workstation",
                owner="compute/ollama_provider_v2.py (canonical adapter)",
                integration="Provider V2 discovers capabilities from /api/show",
                reuse_decision=ReuseDecision.KEEP_DEPENDENCY,
                declared={
                    "platform": "Windows/Linux/macOS",
                    "cpu_support": True,
                    "gpu_support": True,
                    "supported_formats": "GGUF",
                    "tool_call_support": True,
                    "continuous_batching": False,
                    "prefix_caching": False,
                    "memory_use": "residency per model, keep_alive controlled",
                    "licence": "MIT",
                    "maintenance": "active",
                },
                measured={"models_installed": "discovered live"},
                integration_path="Already integrated; provider owns leases",
                migration_task="none — canonical owner",
                test_requirement="test_model_lifecycle_leases.py",
                retirement_condition="Replaced only by a first-party runtime "
                                     "that passes the same lifecycle tests",
                notes=[
                    "Not assumed permanent (§21): KEEP_DEPENDENCY, not "
                    "PRIMARY_FOREVER.",
                ],
            ),
            RuntimeRecord(
                runtime_id="llama_cpp",
                name="llama.cpp",
                upstream="ggml-org/llama.cpp",
                licence="MIT",
                state=RuntimeState.DESIGNED,
                purpose="CPU-first local inference; GGUF; low-bit quantization",
                trigger="CPU-only or low-bit/ternary workloads (§95)",
                owner="models/providers/llama_cpp_provider.py (adapter exists)",
                integration="OpenAI-compatible endpoint via existing adapter",
                reuse_decision=ReuseDecision.FUTURE_FIRST_PARTY_BACKEND,
                declared={
                    "platform": "Windows/Linux/macOS",
                    "cpu_support": True,
                    "gpu_support": True,
                    "supported_formats": "GGUF, GGML",
                    "quantization_support": "INT8/INT4/2-bit/ternary",
                    "continuous_batching": False,
                    "memory_use": "low; CPU-friendly",
                    "licence": "MIT",
                    "maintenance": "active",
                },
                measured={},
                integration_path="Ollama already wraps GGUF — do not "
                                 "duplicate (§20)",
                migration_task="Benchmark against the Ollama layer before "
                               "adopting as a separate backend",
                test_requirement="Real inference parity vs Ollama on one "
                                 "identical model",
                retirement_condition="Not retired; adopted only on measured "
                                     "advantage",
                notes=[
                    "A 39-line OpenAI-compatible adapter already exists; the "
                    "gap is an actual runtime, not an adapter.",
                ],
            ),
            RuntimeRecord(
                runtime_id="vllm",
                name="vLLM",
                upstream="vllm-project/vllm",
                licence="Apache-2.0",
                state=RuntimeState.DESIGNED,
                purpose="High-throughput GPU/cloud serving; continuous batching",
                trigger="Cloud worker serving, multi-user throughput (§22)",
                owner="Hybrid Cloud serving target (not yet provisioned)",
                integration="Cloud execution target behind the AI gateway",
                reuse_decision=ReuseDecision.CLOUD_SERVING_TARGET,
                declared={
                    "platform": "Linux (GPU)",
                    "cpu_support": "limited",
                    "gpu_support": True,
                    "supported_formats": "safetensors, GGUF (partial)",
                    "continuous_batching": True,
                    "prefix_caching": True,
                    "kv_cache_support": "paged attention",
                    "distributed_support": "tensor/pipeline parallel",
                    "memory_use": "high; GPU-resident",
                    "licence": "Apache-2.0",
                    "maintenance": "active",
                },
                measured={},
                integration_path="Provision a cloud GPU target, then route "
                                 "BATCH/INTERACTIVE cloud workloads here",
                migration_task="Blocked on owner credential rotation and a "
                               "cloud GPU target",
                test_requirement="Throughput + TTFT vs the local runtime on "
                                 "an identical model",
                retirement_condition="Not applicable while cloud serving is "
                                     "unprovisioned",
                notes=[
                    "Explicitly NOT the current desktop default (§22): the "
                    "workstation is CPU-first with limited GPU.",
                ],
            ),
            RuntimeRecord(
                runtime_id="sglang",
                name="SGLang",
                upstream="sgl-project/sglang",
                licence="Apache-2.0",
                state=RuntimeState.RESEARCH_ONLY,
                purpose="High-throughput serving with RadixAttention",
                trigger="Only if vLLM proves insufficient (§91 comparison)",
                owner="none — research",
                integration="Not integrated",
                reuse_decision=ReuseDecision.RESEARCH_ONLY,
                declared={
                    "platform": "Linux (GPU)",
                    "gpu_support": True,
                    "continuous_batching": True,
                    "prefix_caching": "RadixAttention",
                    "licence": "Apache-2.0",
                },
                measured={},
                integration_path="Compare against vLLM only when cloud "
                                 "serving is actually provisioned",
                migration_task="none while RESEARCH_ONLY",
                test_requirement="Head-to-head with vLLM on the same target",
                retirement_condition="Superseded by vLLM if it wins the "
                                     "comparison",
            ),
            RuntimeRecord(
                runtime_id="ggml",
                name="GGML / GGUF",
                upstream="ggml-org/ggml",
                licence="MIT",
                state=RuntimeState.DESIGNED,
                purpose="Tensor/runtime library + model format ecosystem",
                trigger="Any GGUF model load; quantization pipeline (§23, §95)",
                owner="Consumed via llama.cpp / Ollama — not a separate "
                      "service",
                integration="Format + library beneath the runtimes above",
                reuse_decision=ReuseDecision.REFERENCE_FOR_AETHERIUS_RUNTIME,
                declared={
                    "supported_formats": "GGUF, GGML",
                    "quantization_support": "INT8/INT4/2-bit/ternary/binary",
                    "licence": "MIT",
                    "maintenance": "active",
                },
                measured={},
                integration_path="Distinguished from llama.cpp per §23: "
                                 "GGML is the format/library, llama.cpp is "
                                 "an engine using it",
                migration_task="Map the low-bit/ternary pipeline onto it "
                               "when that research phase begins",
                test_requirement="Quantization parity test on one model",
                retirement_condition="Not retired",
                notes=[
                    "Recorded separately from llama.cpp on purpose (§23).",
                ],
            ),
        ]

    # -- reconciliation ----------------------------------------------------
    def audit(self, records: list[RuntimeRecord] | None = None) -> dict[str, Any]:
        """Probe the host and reconcile against the candidate set.

        A record claiming INSTALLED_VERIFIED whose probe fails is
        DOWNGRADED, not trusted. §15 ordering: live evidence over
        declaration.
        """
        records = records or self.candidate_runtimes()
        probes = self.prober.probe_all([r.runtime_id for r in records])
        rows: list[dict[str, Any]] = []
        for rec in records:
            probe = probes.get(rec.runtime_id, {})
            present = bool(probe.get("present"))
            if rec.state is RuntimeState.INSTALLED_VERIFIED and not present:
                # Live evidence contradicts the declaration (§15).
                rec.state = RuntimeState.NOT_INSTALLED
                rec.notes.append(
                    f"downgraded from INSTALLED_VERIFIED: probe said "
                    f"{probe.get('reason')}")
            if present:
                # Every present runtime records what the probe actually saw.
                # An INSTALLED_VERIFIED claim with no recorded evidence is
                # indistinguishable from a guess, so verification carries its
                # proof rather than relying on the declaration (§132).
                rec.measured["probe"] = (probe.get("first_line")
                                         or probe.get("reason", ""))
            if probe.get("resolved") and not probe.get("answered"):
                # The executable resolves but does not answer a version
                # request. That is a broken or unprovisioned runtime, not a
                # working one, and the distinction must survive into the
                # report rather than collapsing into "not installed".
                rec.notes.append(
                    f"resolved on PATH but not functional: "
                    f"{probe.get('reason')}")
            row = rec.to_dict()
            row["probe"] = probe
            row["evidence_gap"] = rec.evidence_gap
            rows.append(row)
        return OrderedDict([
            ("runtimes", rows),
            ("by_state", self._count(rows, "state")),
            ("by_decision", self._count(rows, "reuse_decision")),
            ("installed", [r["runtime_id"] for r in rows
                           if r["probe"].get("present")]),
            ("not_installed", [r["runtime_id"] for r in rows
                               if not r["probe"].get("present")]),
            ("unverified_claims", {
                r["runtime_id"]: r["evidence_gap"] for r in rows
                if r["evidence_gap"]}),
        ])

    @staticmethod
    def _count(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in rows:
            out[row[key]] = out.get(row[key], 0) + 1
        return OrderedDict(sorted(out.items()))

    # -- §25 fork-use-case output -----------------------------------------
    @staticmethod
    def fork_use_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """§25 shape: repo, upstream, license, unique commits, decision.

        This does NOT build a second registry. It produces the rows the
        existing Fork Migration Registry consumes.
        """
        return [OrderedDict([
            ("repo", row["upstream"]),
            ("runtime", row["name"]),
            ("license", row["licence"]),
            ("unique_commits", "from migration/unique_audit — not restated"),
            ("capability", row["what"]),
            ("current_aetherius_equivalent", row["where"]),
            ("reuse_decision", row["reuse_decision"]),
            ("integration_path", row["how"]),
            ("migration_task", row["migration_task"]),
            ("test_requirement", row["test_requirement"]),
            ("retirement_condition", row["retirement_condition"]),
            ("evidence_state", row["state"]),
        ]) for row in rows]


# --------------------------------------------------------------------------
# §95 low-bit honesty — SIMULATED is not PHYSICAL
# --------------------------------------------------------------------------

LOW_BIT_EVIDENCE_STATES: tuple[str, ...] = (
    "SIMULATED",
    "EMULATED",
    "SOFTWARE_RUNTIME",
    "PHYSICAL_HARDWARE",
)


def low_bit_evidence_state(claimed: str) -> str:
    """§24 — refuse to promote emulation into hardware.

    Software cannot demonstrate ternary or 1-bit HARDWARE. A software
    runtime executing a quantized model is SOFTWARE_RUNTIME, and calling it
    anything stronger would be a false claim about physical capability.
    """
    normalised = (claimed or "").strip().upper()
    if normalised in LOW_BIT_EVIDENCE_STATES:
        return normalised
    return "SOFTWARE_RUNTIME"
