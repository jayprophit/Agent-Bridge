"""Adaptive resource orchestration (v0.8).

Capability pool built from DeviceProfiler/HardwareProfiler output; rule-based
workload classification; dependency-aware scheduling; evidence-weighted
adaptive placement with lane reserves. No hardware probing here.
"""
from __future__ import annotations

from resources.descriptors import (
    BACKEND_CONTROL_UNAVAILABLE,
    BACKGROUND_INDEXING, BROWSER_RENDERING, CACHE_BUILD, CODE_ANALYSIS,
    COMPILATION, DATABASE_QUERY, EMBEDDINGS, FILE_ANALYSIS, IMAGE_GENERATION,
    LANE_BACKGROUND, LANE_BALANCED, LANE_BATCH_MAXIMUM, LANE_INTERACTIVE,
    MODEL_INFERENCE, NETWORK_TRANSFER, OCR, RAG_INDEXING, RENDER_3D,
    STT, TESTING, TOKENIZATION, TTS, VIDEO_DECODE, VIDEO_ENCODE, VISION,
    AUDIO_PROCESSING, CACHE, CPU_COMPUTE, GPU_COMPUTE, MEDIA_ACCELERATOR,
    MEMORY, NETWORK_IO, NPU_COMPUTE, REMOTE_NODE_COMPUTE, STORAGE_IO, VRAM,
    RESOURCE_KINDS, WORKLOAD_KINDS,
    PlacementDecision, PressureState, ResourceDescriptor, WorkloadDescriptor,
)
from resources.pool import ResourcePool, pool_from_device_profile, remote_node_resource
from resources.classifier import WorkloadClassifier
from resources.monitor import PressureMonitor, LANE_RESERVE
from resources.scheduler import ResourceScheduler
from resources.balancer import AdaptiveBalancer, DEFAULT_WEIGHTS

__all__ = [
    "BACKEND_CONTROL_UNAVAILABLE",
    "BACKGROUND_INDEXING", "BROWSER_RENDERING", "CACHE_BUILD", "CODE_ANALYSIS",
    "COMPILATION", "DATABASE_QUERY", "EMBEDDINGS", "FILE_ANALYSIS",
    "IMAGE_GENERATION", "LANE_BACKGROUND", "LANE_BALANCED", "LANE_BATCH_MAXIMUM",
    "LANE_INTERACTIVE", "MODEL_INFERENCE", "NETWORK_TRANSFER", "OCR",
    "RAG_INDEXING", "RENDER_3D", "STT", "TESTING", "TOKENIZATION", "TTS",
    "VIDEO_DECODE", "VIDEO_ENCODE", "VISION", "AUDIO_PROCESSING", "CACHE",
    "CPU_COMPUTE", "GPU_COMPUTE", "MEDIA_ACCELERATOR", "MEMORY", "NETWORK_IO",
    "NPU_COMPUTE", "REMOTE_NODE_COMPUTE", "STORAGE_IO", "VRAM",
    "RESOURCE_KINDS", "WORKLOAD_KINDS",
    "PlacementDecision", "PressureState", "ResourceDescriptor", "WorkloadDescriptor",
    "ResourcePool", "pool_from_device_profile", "remote_node_resource",
    "WorkloadClassifier", "PressureMonitor", "LANE_RESERVE",
    "ResourceScheduler", "AdaptiveBalancer", "DEFAULT_WEIGHTS",
]
