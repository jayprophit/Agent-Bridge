"""ResourcePool (v0.8). Builds the capability pool from profiler output.

Consumes DeviceCapabilityProfile dicts (and optional trusted-node summaries).
Never probes hardware itself.
"""
from __future__ import annotations

from typing import Any

from resources.descriptors import (
    BACKEND_CONTROL_UNAVAILABLE, CACHE, CPU_COMPUTE, GPU_COMPUTE,
    MEDIA_ACCELERATOR, MEMORY, NETWORK_IO, NPU_COMPUTE, REMOTE_NODE_COMPUTE,
    STORAGE_IO, VRAM, ResourceDescriptor,
    BACKGROUND_INDEXING, BROWSER_RENDERING, CACHE_BUILD, CODE_ANALYSIS,
    COMPILATION, DATABASE_QUERY, EMBEDDINGS, FILE_ANALYSIS, MODEL_INFERENCE,
    NETWORK_TRANSFER, OCR, RAG_INDEXING, RENDER_3D, TESTING, TOKENIZATION,
    TTS, VIDEO_DECODE, VIDEO_ENCODE, VISION,
)

# Ollama exposes per-request GPU offload ("options": {"num_gpu": N}).
# Declared-partial: documented control, not benchmark-verified here.
OLLAMA_OFFLOAD_CONTROLS = ["num_gpu", "num_thread"]


def pool_from_device_profile(profile: dict[str, Any],
                             node_id: str = "local") -> list[ResourceDescriptor]:
    """Build pool resources from a DeviceCapabilityProfile dict."""
    pool: list[ResourceDescriptor] = []
    cpu = profile.get("cpu", {}) or {}
    gpu = profile.get("gpu", {}) or {}
    memory = profile.get("memory", {}) or {}
    network = profile.get("network", {}) or {}
    accelerators = profile.get("accelerators", []) or []
    media = profile.get("media", {}) or {}

    logical = int(cpu.get("logical_cores", 0) or 0)
    if logical:
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:cpu", kind=CPU_COMPUTE,
            display_name=f"CPU ({cpu.get('model', 'unknown')})",
            capacity=float(logical), available=float(logical),
            backend="psutil", controls=["num_thread", "worker_count"],
            serves=[TOKENIZATION, FILE_ANALYSIS, CODE_ANALYSIS, COMPILATION,
                    TESTING, DATABASE_QUERY, CACHE_BUILD, BACKGROUND_INDEXING,
                    RAG_INDEXING, EMBEDDINGS, MODEL_INFERENCE]))
    ram_mb = int(memory.get("total_mb", 0) or 0)
    if ram_mb:
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:ram", kind=MEMORY,
            display_name=f"RAM ({ram_mb} MB)",
            capacity=float(ram_mb),
            available=float(memory.get("available_mb", 0) or 0),
            backend="psutil", controls=["cache_size_mb", "concurrency"],
            serves=[MODEL_INFERENCE, RAG_INDEXING, EMBEDDINGS, CACHE_BUILD,
                    BACKGROUND_INDEXING, DATABASE_QUERY]))
    if gpu.get("vendor") and gpu.get("model"):
        vram = int(gpu.get("vram_mb", 0) or 0)
        serves = [MODEL_INFERENCE, VISION, OCR, RENDER_3D, BROWSER_RENDERING,
                  VIDEO_ENCODE, VIDEO_DECODE]
        controls = list(OLLAMA_OFFLOAD_CONTROLS) if vram else [BACKEND_CONTROL_UNAVAILABLE]
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:gpu", kind=GPU_COMPUTE,
            display_name=f"GPU ({gpu.get('model')})",
            capacity=100.0, available=100.0,
            backend="ollama/vulkan/directml", controls=controls, serves=serves))
        if vram:
            pool.append(ResourceDescriptor(
                resource_id=f"{node_id}:vram", kind=VRAM,
                display_name=f"VRAM ({vram} MB)",
                capacity=float(vram), available=float(vram),
                backend="ollama", controls=list(OLLAMA_OFFLOAD_CONTROLS),
                serves=[MODEL_INFERENCE, VISION]))
    for acc in accelerators:
        if isinstance(acc, dict) and acc.get("available"):
            pool.append(ResourceDescriptor(
                resource_id=f"{node_id}:npu", kind=NPU_COMPUTE,
                display_name=f"NPU ({acc.get('model', 'unknown')})",
                capacity=100.0, available=100.0,
                backend=str(acc.get("vendor", "")) or "unknown",
                controls=[BACKEND_CONTROL_UNAVAILABLE],
                serves=[MODEL_INFERENCE, VISION, OCR]))
    if network.get("connected"):
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:net", kind=NETWORK_IO,
            display_name=f"Network ({network.get('interface_type', 'unknown')})",
            capacity=100.0, available=100.0, backend="psutil",
            controls=[BACKEND_CONTROL_UNAVAILABLE],
            serves=[NETWORK_TRANSFER, BROWSER_RENDERING]))
    storage = profile.get("storage", {}) or {}
    if int(storage.get("total_mb", 0) or 0):
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:storage", kind=STORAGE_IO,
            display_name="Storage I/O", capacity=100.0, available=100.0,
            backend="psutil", controls=["cache_size_mb"],
            serves=[CACHE_BUILD, RAG_INDEXING, BACKGROUND_INDEXING,
                    DATABASE_QUERY]))
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:cache", kind=CACHE,
            display_name="Storage cache", capacity=100.0, available=100.0,
            backend="bridge-cache", controls=["cache_size_mb"],
            serves=[CACHE_BUILD, RAG_INDEXING, EMBEDDINGS]))
    if media.get("camera_present") or media.get("microphone_present"):
        pool.append(ResourceDescriptor(
            resource_id=f"{node_id}:media", kind=MEDIA_ACCELERATOR,
            display_name="Media devices (presence only)",
            capacity=1.0, available=1.0, backend="os-enumeration",
            controls=[BACKEND_CONTROL_UNAVAILABLE],
            serves=[VISION, OCR]))
    return pool


def remote_node_resource(node_id: str, display_name: str = "",
                         capacity_jobs: float = 2.0) -> ResourceDescriptor:
    """Advertise a trusted remote node as a compute resource."""
    return ResourceDescriptor(
        resource_id=f"node:{node_id}", kind=REMOTE_NODE_COMPUTE,
        display_name=display_name or f"Remote node {node_id}",
        capacity=capacity_jobs, available=capacity_jobs,
        backend=f"node:{node_id}", controls=["delegate", "cancel"],
        serves=[MODEL_INFERENCE, CODE_ANALYSIS, FILE_ANALYSIS, TESTING,
                RAG_INDEXING, EMBEDDINGS])


class ResourcePool:
    """ID-keyed pool with availability accounting."""

    def __init__(self, resources: list[ResourceDescriptor] | None = None):
        self._resources: dict[str, ResourceDescriptor] = {}
        for r in resources or []:
            self._resources[r.resource_id] = r

    def add(self, resource: ResourceDescriptor) -> None:
        self._resources[resource.resource_id] = resource

    def get(self, resource_id: str) -> ResourceDescriptor:
        return self._resources[resource_id]

    def ids(self) -> list[str]:
        return sorted(self._resources)

    def __len__(self) -> int:
        return len(self._resources)

    def by_kind(self, kind: str) -> list[ResourceDescriptor]:
        return [r for r in self._resources.values() if r.kind == kind]

    def compatible(self, workload) -> list[ResourceDescriptor]:
        """Resources whose serves-list includes the workload kind (and backend).

        CPU remains compatible with MODEL_INFERENCE (Ollama CPU fallback is
        real); VRAM-heavy workloads additionally filter by min_vram downstream.
        needs_gpu only excludes resources that cannot serve the kind at all.
        """
        out = []
        for r in self._resources.values():
            if workload.kind not in r.serves:
                continue
            if workload.backend and workload.backend != r.backend \
                    and workload.backend not in r.backend.split("/"):
                continue
            out.append(r)
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"resources": [r.to_dict() for r in self._resources.values()]}
