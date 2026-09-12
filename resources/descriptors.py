"""Resource descriptors (v0.8). Capability pool, workloads, pressure state.

Built FROM DeviceProfiler/HardwareProfiler output — never re-probes hardware.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# Resource kinds
CPU_COMPUTE = "CPU_COMPUTE"
GPU_COMPUTE = "GPU_COMPUTE"
NPU_COMPUTE = "NPU_COMPUTE"
MEMORY = "MEMORY"
VRAM = "VRAM"
STORAGE_IO = "STORAGE_IO"
CACHE = "CACHE"
NETWORK_IO = "NETWORK_IO"
REMOTE_NODE_COMPUTE = "REMOTE_NODE_COMPUTE"
MEDIA_ACCELERATOR = "MEDIA_ACCELERATOR"

RESOURCE_KINDS = (
    CPU_COMPUTE, GPU_COMPUTE, NPU_COMPUTE, MEMORY, VRAM,
    STORAGE_IO, CACHE, NETWORK_IO, REMOTE_NODE_COMPUTE, MEDIA_ACCELERATOR,
)

# Backend offload control marker
BACKEND_CONTROL_UNAVAILABLE = "BACKEND_CONTROL_UNAVAILABLE"

# Workload kinds
MODEL_INFERENCE = "MODEL_INFERENCE"
TOKENIZATION = "TOKENIZATION"
EMBEDDINGS = "EMBEDDINGS"
RAG_INDEXING = "RAG_INDEXING"
FILE_ANALYSIS = "FILE_ANALYSIS"
CODE_ANALYSIS = "CODE_ANALYSIS"
COMPILATION = "COMPILATION"
TESTING = "TESTING"
OCR = "OCR"
VISION = "VISION"
IMAGE_GENERATION = "IMAGE_GENERATION"
AUDIO_PROCESSING = "AUDIO_PROCESSING"
TTS = "TTS"
STT = "STT"
VIDEO_ENCODE = "VIDEO_ENCODE"
VIDEO_DECODE = "VIDEO_DECODE"
RENDER_3D = "3D_RENDERING"
BROWSER_RENDERING = "BROWSER_RENDERING"
DATABASE_QUERY = "DATABASE_QUERY"
NETWORK_TRANSFER = "NETWORK_TRANSFER"
CACHE_BUILD = "CACHE_BUILD"
BACKGROUND_INDEXING = "BACKGROUND_INDEXING"

WORKLOAD_KINDS = (
    MODEL_INFERENCE, TOKENIZATION, EMBEDDINGS, RAG_INDEXING,
    FILE_ANALYSIS, CODE_ANALYSIS, COMPILATION, TESTING, OCR, VISION,
    IMAGE_GENERATION, AUDIO_PROCESSING, TTS, STT, VIDEO_ENCODE,
    VIDEO_DECODE, RENDER_3D, BROWSER_RENDERING, DATABASE_QUERY,
    NETWORK_TRANSFER, CACHE_BUILD, BACKGROUND_INDEXING,
)

# Execution lanes (responsiveness reserve)
LANE_INTERACTIVE = "INTERACTIVE"
LANE_BALANCED = "BALANCED"
LANE_BACKGROUND = "BACKGROUND"
LANE_BATCH_MAXIMUM = "BATCH_MAXIMUM"


@dataclass
class ResourceDescriptor:
    """One poolable resource with its backend control surface."""
    resource_id: str
    kind: str
    display_name: str = ""
    # Capacity in kind-native units (cores, MB, Mbps, jobs).
    capacity: float = 0.0
    available: float = 0.0
    backend: str = ""  # e.g. "ollama", "vulkan", "directml", "psutil", "node:<id>"
    # Knobs the bridge can actually turn, or BACKEND_CONTROL_UNAVAILABLE.
    controls: list[str] = field(default_factory=list)
    # Workload kinds this resource can serve (compatibility gate).
    serves: list[str] = field(default_factory=list)
    shared: bool = True  # False reserves it for one workload at a time

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkloadDescriptor:
    """A schedulable unit of work."""
    workload_id: str
    kind: str
    display_name: str = ""
    min_ram_mb: int = 0
    min_vram_mb: int = 0
    needs_gpu: bool = False
    backend: str = ""  # required backend, "" = any compatible
    priority: int = 50  # 0-100
    size_estimate: str = "small"  # tiny/small/medium/large
    # Write-collision guard: files this workload mutates.
    writes_files: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    lane: str = LANE_BALANCED

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PressureState:
    """Point-in-time pressure snapshot (0.0-1.0 per axis)."""
    cpu: float = 0.0
    ram: float = 0.0
    vram: float = 0.0
    gpu: float = 0.0
    disk_io: float = 0.0
    battery_low: bool = False
    thermal: bool = False

    def hottest(self) -> tuple[str, float]:
        vals = {"cpu": self.cpu, "ram": self.ram, "vram": self.vram,
                "gpu": self.gpu, "disk_io": self.disk_io}
        return max(vals.items(), key=lambda kv: kv[1])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlacementDecision:
    """Scheduler/balancer output for one workload."""
    workload_id: str
    resource_id: str
    lane: str = LANE_BALANCED
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0
    deferred: bool = False
    fallback_resource_ids: list[str] = field(default_factory=list)
    benchmark_evidence_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
