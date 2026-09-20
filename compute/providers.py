"""VM-B compute provider registry + routing policy (P9).

Providers describe EXTERNAL compute (the VM-B laboratory): Genesis never
runs inside them and they never define Genesis identity. Simulated
backends (ternary emulator, quantum simulator) are labeled simulated and
are never credited with physical performance they do not possess.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass, field
from typing import Callable

STATUS_AVAILABLE = "available"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"
STATUS_SIMULATED = "simulated"

EVIDENCE_OBSERVED = "observed"
EVIDENCE_DECLARED = "declared"
EVIDENCE_SIMULATED = "simulated"

PRIVACY_LOCAL_FIRST = "local-first"
PRIVACY_BALANCED = "balanced"
PRIVACY_REMOTE_OK = "remote-ok"


@dataclass
class ComputeRecord:
    provider_id: str
    kind: str  # local-cpu | ollama | ternary-emu | sim-qpu
    backend: str
    local_or_remote: str = "unknown"  # local | remote | unknown
    status: str = STATUS_UNAVAILABLE
    evidence: str = EVIDENCE_DECLARED
    controls: str = "BACKEND_CONTROL_UNAVAILABLE"
    note: str = ""


@dataclass
class ComputeDecision:
    provider_id: str
    kind: str
    reasons: list[str] = field(default_factory=list)
    fallback_used: bool = False
    fallback_from: str = ""
    simulated: bool = False


class ComputeRegistry:
    """Catalog of VM-B compute providers with honest status labels."""

    def __init__(self) -> None:
        self._providers: dict[str, ComputeRecord] = {}

    def register(self, record: ComputeRecord) -> None:
        if not record.provider_id:
            raise ValueError("provider_id is required")
        self._providers[record.provider_id] = record

    def describe(self, provider_id: str) -> ComputeRecord | None:
        return self._providers.get(provider_id)

    def __len__(self) -> int:
        return len(self._providers)

    def list_available(self) -> list[ComputeRecord]:
        return [r for r in self._providers.values()
                if r.status in (STATUS_AVAILABLE, STATUS_DEGRADED, STATUS_SIMULATED)]

    @staticmethod
    def default_records(ollama_reachable: bool = False) -> list[ComputeRecord]:
        return [
            ComputeRecord(
                provider_id="local-cpu",
                kind="local-cpu",
                backend="cpu",
                local_or_remote="local",
                status=STATUS_AVAILABLE,
                evidence=EVIDENCE_OBSERVED,
                controls="local-process",
                note="Host CPU via local process execution.",
            ),
            ComputeRecord(
                provider_id="ollama",
                kind="ollama",
                backend="ollama:/api/chat",
                local_or_remote="local",
                status=STATUS_AVAILABLE if ollama_reachable else STATUS_UNAVAILABLE,
                evidence=EVIDENCE_OBSERVED if ollama_reachable else EVIDENCE_DECLARED,
                controls="local-daemon" if ollama_reachable else "BACKEND_CONTROL_UNAVAILABLE",
                note="Local Ollama daemon." if ollama_reachable
                else "Ollama daemon not reached; not used.",
            ),
            ComputeRecord(
                provider_id="ternary-emu",
                kind="ternary-emu",
                backend="emulated-encoder",
                local_or_remote="local",
                status=STATUS_SIMULATED,
                evidence=EVIDENCE_SIMULATED,
                note="Ternary/bitpacked emulation only; no ternary silicon.",
            ),
            ComputeRecord(
                provider_id="sim-qpu",
                kind="sim-qpu",
                backend="cpu-fallback",
                local_or_remote="local",
                status=STATUS_SIMULATED,
                evidence=EVIDENCE_SIMULATED,
                note="Quantum simulator on CPU; no quantum effects, no QPU.",
            ),
        ]


def probe_ollama(host: str = "127.0.0.1", port: int = 11434,
                 timeout_s: float = 1.0) -> bool:
    """True when a local Ollama daemon answers TCP. Never blocks long."""
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False


def route_compute(capability: str,
                  privacy: str = PRIVACY_LOCAL_FIRST,
                  registry: ComputeRegistry | None = None,
                  preferred_provider: str = "",
                  ollama_probe: Callable[[], bool] | None = None) -> ComputeDecision:
    """Route a compute request to a provider. Simulated stays simulated."""
    registry = registry or ComputeRegistry()
    if len(registry) == 0:
        for record in ComputeRegistry.default_records(
                ollama_reachable=(ollama_probe or probe_ollama)()):
            registry.register(record)

    available = {r.provider_id: r for r in registry.list_available()}
    reasons: list[str] = []

    def decide(provider_id: str, reason: str, fallback_from: str = "") -> ComputeDecision:
        record = available[provider_id]
        reasons.append(reason)
        return ComputeDecision(
            provider_id=provider_id,
            kind=record.kind,
            reasons=list(reasons),
            fallback_used=bool(fallback_from),
            fallback_from=fallback_from,
            simulated=record.status == STATUS_SIMULATED,
        )

    if preferred_provider and preferred_provider in available:
        return decide(preferred_provider, "preferred provider available")

    capability = (capability or "").lower()
    if capability in ("qpu", "quantum", "quantum-sim"):
        if "sim-qpu" in available:
            return decide("sim-qpu", "quantum capability runs on the simulator only")
        reasons.append("no quantum provider available")
    elif capability in ("ml-inference", "llm", "chat"):
        if privacy in (PRIVACY_LOCAL_FIRST, PRIVACY_BALANCED) and "ollama" in available:
            return decide("ollama", "local model preferred for inference")
        if "ollama" in available and privacy == PRIVACY_REMOTE_OK:
            return decide("ollama", "local model available")
        if "local-cpu" in available:
            return decide("local-cpu", "inference falls back to host CPU",
                          fallback_from="ollama")
    elif capability in ("ternary", "bitnet", "low-bit"):
        if "ternary-emu" in available:
            return decide("ternary-emu", "low-bit capability runs on the emulator only")

    if "local-cpu" in available:
        return decide("local-cpu", "default host-CPU placement",
                      fallback_from="preferred" if preferred_provider else "")
    remaining = [pid for pid in available if pid != "local-cpu"]
    if remaining:
        return decide(remaining[0], "only non-CPU provider available",
                      fallback_from="local-cpu")
    raise RuntimeError("no compute provider available")
