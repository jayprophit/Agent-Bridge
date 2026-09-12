"""Node factory (v0.7). DeviceCapabilityProfile -> NodeDescriptor.

Single conversion point so hardware detection is never duplicated:

DeviceProfiler
      |
DeviceCapabilityProfile
      |
NodeDescriptor
      |
NodeRegistry
"""
from __future__ import annotations

from typing import Any

from nodes.node_descriptor import OWNER_NODE, NodeDescriptor


def node_from_device_profile(
    profile: Any,
    node_id: str,
    endpoint: str = "",
    trust_level: str = OWNER_NODE,
    models: list[str] | None = None,
    providers: list[str] | None = None,
    agents: list[str] | None = None,
    ides: list[str] | None = None,
    tools: list[str] | None = None,
    data_roots: list[str] | None = None,
) -> NodeDescriptor:
    """Build a NodeDescriptor from a DeviceCapabilityProfile (no re-probing)."""
    media = getattr(profile, "media", None)
    camera = bool(getattr(media, "camera_present", False))
    microphone = bool(getattr(media, "microphone_present", False))
    speaker = bool(getattr(media, "speaker_present", False))

    input_devices = []
    output_devices = []
    input_capabilities = []
    output_capabilities = []
    if camera:
        input_devices.append("camera")
        input_capabilities.append("video_input")
    if microphone:
        input_devices.append("microphone")
        input_capabilities.append("audio_input")
    if speaker:
        output_devices.append("speaker")
        output_capabilities.append("audio_output")
    if getattr(profile, "display", None) and getattr(profile.display, "resolution", ""):
        output_devices.append("display")
        output_capabilities.append("display")

    capabilities = list(getattr(profile, "capabilities", []) or [])
    for cap in ("camera", "microphone", "speaker"):
        present = {"camera": camera, "microphone": microphone, "speaker": speaker}[cap]
        if present and cap not in capabilities:
            capabilities.append(cap)

    gpu = getattr(profile, "gpu", None)
    memory = getattr(profile, "memory", None)
    storage = getattr(profile, "storage", None)
    battery = getattr(profile, "battery", None)
    network = getattr(profile, "network", None)
    cpu = getattr(profile, "cpu", None)

    return NodeDescriptor(
        node_id=node_id,
        device_class=getattr(profile, "device_class", "unknown"),
        platform=getattr(profile, "os", "unknown"),
        architecture=getattr(profile, "architecture", ""),
        runtime_role=getattr(profile, "runtime_role", ""),
        resource_class=getattr(profile, "resource_class", ""),
        online=True,
        trust_level=trust_level,
        tools=list(tools or []),
        models=list(models or []),
        providers=list(providers or []),
        agents=list(agents or []),
        ides=list(ides or []),
        memory_mb=int(getattr(memory, "total_mb", 0) or 0),
        storage_mb=int(getattr(storage, "total_mb", 0) or 0),
        battery_percent=int(getattr(battery, "level_percent", 0) or 0),
        network_available=bool(getattr(network, "connected", False)),
        cpu_cores=int(getattr(cpu, "logical_cores", 0) or 0),
        gpu_available=bool(getattr(gpu, "vendor", "") and getattr(gpu, "model", "")),
        gpu_memory_mb=int(getattr(gpu, "vram_mb", 0) or 0),
        ai_accelerator=bool(getattr(profile, "has_ai_accelerator", lambda: False)()),
        admin_capability=bool(getattr(profile, "admin_possible", False)),
        filesystem_write=bool(getattr(profile, "filesystem_write", False)),
        browser_available=bool(getattr(profile, "browser_available", False)),
        endpoint=endpoint,
        input_devices=input_devices,
        output_devices=output_devices,
        input_capabilities=input_capabilities,
        output_capabilities=output_capabilities,
        data_roots=list(data_roots or []),
        display_name=node_id,
        capabilities=capabilities,
    )
