"""ModelRegistry (v0.7). Catalog of available AI models with capabilities.

Models are the reasoning engines that the runtime uses. Each model is
registered with its provider, capabilities, and hardware requirements.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# model statuses
MODEL_AVAILABLE = "MODEL_AVAILABLE"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
NOT_INSTALLED = "NOT_INSTALLED"
PROVIDER_REQUIRED = "PROVIDER_REQUIRED"
OFFLINE = "OFFLINE"

MODEL_STATUSES = (
    MODEL_AVAILABLE, MODEL_UNAVAILABLE, NOT_INSTALLED,
    PROVIDER_REQUIRED, OFFLINE
)

# model capability tags
CAPABILITY_CODING = "coding"
CAPABILITY_VISION = "vision"
CAPABILITY_AUDIO_INPUT = "audio_input"
CAPABILITY_AUDIO_OUTPUT = "audio_output"
CAPABILITY_TOOL_CALLING = "tool_calling"
CAPABILITY_STREAMING = "streaming"
CAPABILITY_STRUCTURED_OUTPUT = "structured_output"
CAPABILITY_REASONING = "reasoning"
CAPABILITY_REVIEW = "review"
CAPABILITY_MATH = "math"
CAPABILITY_CODE_STRENGTH = "code_strength"
CAPABILITY_REVIEW_STRENGTH = "review_strength"

CAPABILITY_TAGS = (
    CAPABILITY_CODING, CAPABILITY_VISION, CAPABILITY_AUDIO_INPUT,
    CAPABILITY_AUDIO_OUTPUT, CAPABILITY_TOOL_CALLING, CAPABILITY_STREAMING,
    CAPABILITY_STRUCTURED_OUTPUT, CAPABILITY_REASONING, CAPABILITY_REVIEW,
    CAPABILITY_MATH, CAPABILITY_CODE_STRENGTH, CAPABILITY_REVIEW_STRENGTH
)

# privacy classifications
PRIVACY_LOCAL = "PRIVACY_LOCAL"
PRIVACY_CLOUD = "PRIVACY_CLOUD"
PRIVACY_HYBRID = "PRIVACY_HYBRID"
PRIVACY_UNKNOWN = "PRIVACY_UNKNOWN"

PRIVACY_CLASSES = (PRIVACY_LOCAL, PRIVACY_CLOUD, PRIVACY_HYBRID, PRIVACY_UNKNOWN)

# capability evidence levels (shared vocabulary with benchmarks)
EVIDENCE_DECLARED = "DECLARED"
EVIDENCE_PROVIDER_REPORTED = "PROVIDER_REPORTED"
EVIDENCE_PROBE_VERIFIED = "PROBE_VERIFIED"
EVIDENCE_BENCHMARK_VERIFIED = "BENCHMARK_VERIFIED"
EVIDENCE_UNKNOWN = "UNKNOWN"
EVIDENCE_FAILED_PROBE = "FAILED_PROBE"

CAPABILITY_EVIDENCE_LEVELS = (
    EVIDENCE_DECLARED,
    EVIDENCE_PROVIDER_REPORTED,
    EVIDENCE_PROBE_VERIFIED,
    EVIDENCE_BENCHMARK_VERIFIED,
    EVIDENCE_UNKNOWN,
    EVIDENCE_FAILED_PROBE,
)

# tool-calling modes (distinct abilities; do not conflate)
TOOL_CALL_NATIVE = "NATIVE_TOOL_CALLING"
TOOL_CALL_BRIDGE_STRUCTURED = "BRIDGE_STRUCTURED_ACTION"
TOOL_CALL_STRUCTURED_JSON = "STRUCTURED_JSON"
TOOL_CALL_CONTENT_INTENT = "CONTENT_TOOL_INTENT"

TOOL_CALL_MODES = (
    TOOL_CALL_NATIVE,
    TOOL_CALL_BRIDGE_STRUCTURED,
    TOOL_CALL_STRUCTURED_JSON,
    TOOL_CALL_CONTENT_INTENT,
)


@dataclass
class ModelRecord:
    model_id: str
    provider: str = ""
    display_name: str = ""
    description: str = ""
    version: str = "0.7.0"
    status: str = NOT_INSTALLED
    local_or_remote: str = "unknown"  # "local" | "remote" | "unknown"
    installed: bool = False
    reachable: bool = False
    context_length: int = 0
    tool_calling: bool = False
    vision: bool = False
    audio_input: bool = False
    audio_output: bool = False
    streaming: bool = False
    structured_output: bool = False
    code_strength: str = ""  # "high" | "medium" | "low" | ""
    review_strength: str = ""  # "high" | "medium" | "low" | ""
    ram_requirement_mb: int = 0
    vram_requirement_mb: int = 0
    quantization: str = ""  # e.g. "q4_k_m", "q8_0", "f16"
    architecture: str = ""  # e.g. "llama", "qwen", "gpt"
    latency_ms: int = 0  # measured latency if available
    tokens_per_second: float = 0.0  # measured throughput if available
    cost_metadata: dict = field(default_factory=dict)
    privacy_classification: str = PRIVACY_UNKNOWN
    offline_capable: bool = False
    device_compatibility: list = field(default_factory=list)
    capability_tags: list = field(default_factory=list)
    # Evidence-qualified capability metadata. The boolean flags above (e.g.
    # tool_calling/vision) record provider-advertised or legacy claims; the
    # authoritative per-capability confidence lives here.
    capability_evidence: dict = field(default_factory=dict)
    # How this model performs tool calls, when known. One of TOOL_CALL_MODES
    # or "" when unknown. CONTENT_TOOL_INTENT must never be upgraded to
    # NATIVE_TOOL_CALLING.
    tool_calling_mode: str = ""
    limitations: str = ""
    
    def __post_init__(self) -> None:
        if self.status not in MODEL_STATUSES:
            raise ValueError(f"unknown model status: {self.status}")
        if self.privacy_classification not in PRIVACY_CLASSES:
            raise ValueError(f"unknown privacy class: {self.privacy_classification}")
        if self.tool_calling_mode and self.tool_calling_mode not in TOOL_CALL_MODES:
            raise ValueError(f"unknown tool calling mode: {self.tool_calling_mode}")
        for cap, ev in self.capability_evidence.items():
            if ev not in CAPABILITY_EVIDENCE_LEVELS:
                raise ValueError(f"unknown evidence level for {cap}: {ev}")

    def evidence_for(self, capability: str, default: str = EVIDENCE_UNKNOWN) -> str:
        """Return evidence level for a capability (never infers from name)."""
        return self.capability_evidence.get(capability, default)

    def annotate_capability(self, capability: str, evidence: str,
                            tool_mode: str = "") -> None:
        """Record a capability with explicit evidence level.

        Adds the capability tag (if missing) and records how it was
        established. CONTENT_TOOL_INTENT is never upgraded to
        NATIVE_TOOL_CALLING by this helper.
        """
        if evidence not in CAPABILITY_EVIDENCE_LEVELS:
            raise ValueError(f"unknown evidence level: {evidence}")
        if tool_mode and tool_mode not in TOOL_CALL_MODES:
            raise ValueError(f"unknown tool calling mode: {tool_mode}")
        if capability not in self.capability_tags:
            self.capability_tags.append(capability)
        self.capability_evidence[capability] = evidence
        if capability == CAPABILITY_TOOL_CALLING and tool_mode:
            if tool_mode == TOOL_CALL_NATIVE and \
                    self.tool_calling_mode == TOOL_CALL_CONTENT_INTENT:
                raise ValueError("refusing to upgrade CONTENT_TOOL_INTENT to NATIVE_TOOL_CALLING")
            self.tool_calling_mode = tool_mode
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ModelRegistry:
    """ID-keyed model registry. Models are registered by providers."""
    
    def __init__(self):
        self._models: dict[str, ModelRecord] = {}
    
    def register(self, record: ModelRecord) -> None:
        if not record.model_id:
            raise ValueError("model_id must be non-empty")
        if record.model_id in self._models:
            raise ValueError(f"duplicate model_id: {record.model_id}")
        self._models[record.model_id] = record
    
    def get(self, model_id: str) -> ModelRecord:
        try:
            return self._models[model_id]
        except KeyError:
            raise KeyError(f"unknown model: {model_id!r}")
    
    def ids(self) -> list[str]:
        return sorted(self._models)
    
    def __len__(self) -> int:
        return len(self._models)
    
    def list(self, provider: str = "", status: str = "",
             local_or_remote: str = "", capability: str = "") -> list[ModelRecord]:
        out = []
        for rec in self._models.values():
            if provider and rec.provider != provider:
                continue
            if status and rec.status != status:
                continue
            if local_or_remote and rec.local_or_remote != local_or_remote:
                continue
            if capability and capability not in rec.capability_tags:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r.model_id)
    
    def search(self, query: str, limit: int = 20) -> list[ModelRecord]:
        words = [w.lower() for w in query.split() if w]
        scored = []
        for rec in self._models.values():
            hay = f"{rec.model_id} {rec.display_name} {rec.description} " \
                  f"{' '.join(rec.capability_tags)}".lower()
            score = sum(2 for w in words if w in hay)
            if score:
                scored.append((score, rec))
        scored.sort(key=lambda t: (-t[0], t[1].model_id))
        return [r for _, r in scored[:limit]]
    
    def describe(self, model_id: str) -> dict[str, Any]:
        return self.get(model_id).to_dict()
    
    def status_of(self, model_id: str) -> dict[str, Any]:
        rec = self.get(model_id)
        return {"model_id": rec.model_id, "status": rec.status,
                "available": rec.status == MODEL_AVAILABLE,
                "provider": rec.provider, "local_or_remote": rec.local_or_remote,
                "installed": rec.installed, "reachable": rec.reachable,
                "limitations": rec.limitations}
    
    def available_models(self) -> list[ModelRecord]:
        return [m for m in self._models.values()
                if m.status == MODEL_AVAILABLE]
    
    def local_models(self) -> list[ModelRecord]:
        return [m for m in self._models.values()
                if m.local_or_remote == "local"]
    
    def remote_models(self) -> list[ModelRecord]:
        return [m for m in self._models.values()
                if m.local_or_remote == "remote"]
    
    def models_with_capability(self, capability: str) -> list[ModelRecord]:
        return [m for m in self._models.values()
                if capability in m.capability_tags and m.status == MODEL_AVAILABLE]
    
    def coding_models(self) -> list[ModelRecord]:
        return self.models_with_capability(CAPABILITY_CODING)
    
    def vision_models(self) -> list[ModelRecord]:
        return self.models_with_capability(CAPABILITY_VISION)
    
    def tool_calling_models(self) -> list[ModelRecord]:
        return self.models_with_capability(CAPABILITY_TOOL_CALLING)
    
    def offline_capable_models(self) -> list[ModelRecord]:
        return [m for m in self._models.values()
                if m.offline_capable and m.status == MODEL_AVAILABLE]