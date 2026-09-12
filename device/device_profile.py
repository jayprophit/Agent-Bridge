"""DeviceCapabilityProfile (v0.7). Normalized device capability representation.

Provides a standardized representation of device capabilities across
different platforms and device classes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


# Device classes
DEVICE_CLASS_DESKTOP = "desktop"
DEVICE_CLASS_WORKSTATION = "workstation"
DEVICE_CLASS_SERVER = "server"
DEVICE_CLASS_LAPTOP = "laptop"
DEVICE_CLASS_ANDROID = "android"
DEVICE_CLASS_PHONE = "phone"
DEVICE_CLASS_TABLET = "tablet"
DEVICE_CLASS_IPAD = "ipad"
DEVICE_CLASS_SMARTWATCH = "smartwatch"
DEVICE_CLASS_SMART_RING = "smart_ring"
DEVICE_CLASS_SMART_GLASSES = "smart_glasses"
DEVICE_CLASS_SMART_TV = "smart_tv"
DEVICE_CLASS_EMBEDDED = "embedded"
DEVICE_CLASS_IOT = "iot"
DEVICE_CLASS_UNKNOWN = "unknown"

DEVICE_CLASSES = (
    DEVICE_CLASS_DESKTOP, DEVICE_CLASS_WORKSTATION, DEVICE_CLASS_SERVER,
    DEVICE_CLASS_LAPTOP, DEVICE_CLASS_ANDROID, DEVICE_CLASS_PHONE, DEVICE_CLASS_TABLET,
    DEVICE_CLASS_IPAD, DEVICE_CLASS_SMARTWATCH, DEVICE_CLASS_SMART_RING,
    DEVICE_CLASS_SMART_GLASSES, DEVICE_CLASS_SMART_TV, DEVICE_CLASS_EMBEDDED,
    DEVICE_CLASS_IOT, DEVICE_CLASS_UNKNOWN
)

# OS families
OS_WINDOWS = "windows"
OS_MACOS = "macos"
OS_LINUX = "linux"
OS_CHROMEOS = "chromeos"
OS_ANDROID = "android"
OS_IOS = "ios"
OS_IPADOS = "ipados"
OS_WATCHOS = "watchos"
OS_TVOS = "tvos"
OS_UNKNOWN = "unknown"

OS_FAMILIES = (
    OS_WINDOWS, OS_MACOS, OS_LINUX, OS_CHROMEOS,
    OS_ANDROID, OS_IOS, OS_IPADOS, OS_WATCHOS, OS_TVOS, OS_UNKNOWN
)

# Performance profiles
PROFILE_ULTRA_LOW_RESOURCE = "ULTRA_LOW_RESOURCE"
PROFILE_MOBILE = "MOBILE"
PROFILE_MOBILE_POWER_SAVE = "MOBILE_POWER_SAVE"
PROFILE_LOW_RESOURCE = "LOW_RESOURCE"
PROFILE_BALANCED = "BALANCED"
PROFILE_PERFORMANCE = "PERFORMANCE"
PROFILE_WORKSTATION = "WORKSTATION"
PROFILE_SERVER = "SERVER"

PERFORMANCE_PROFILES = (
    PROFILE_ULTRA_LOW_RESOURCE, PROFILE_MOBILE, PROFILE_MOBILE_POWER_SAVE,
    PROFILE_LOW_RESOURCE, PROFILE_BALANCED, PROFILE_PERFORMANCE,
    PROFILE_WORKSTATION, PROFILE_SERVER
)


# Runtime roles (NODE ROLE axis: what function the node serves).
# Kept for backwards compatibility; resource-driven entries below are
# superseded by RESOURCE_CLASS_* but remain valid values.
RUNTIME_ROLE_FULL_RUNTIME = "FULL_RUNTIME"
RUNTIME_ROLE_CONSTRAINED_RUNTIME = "CONSTRAINED_RUNTIME"
RUNTIME_ROLE_CLIENT_NODE = "CLIENT_NODE"
RUNTIME_ROLE_DELEGATION_NODE = "DELEGATION_NODE"
RUNTIME_ROLE_SENSOR_NODE = "SENSOR_NODE"
RUNTIME_ROLE_DISPLAY_NODE = "DISPLAY_NODE"

RUNTIME_ROLES = (
    RUNTIME_ROLE_FULL_RUNTIME, RUNTIME_ROLE_CONSTRAINED_RUNTIME,
    RUNTIME_ROLE_CLIENT_NODE, RUNTIME_ROLE_DELEGATION_NODE,
    RUNTIME_ROLE_SENSOR_NODE, RUNTIME_ROLE_DISPLAY_NODE
)

# Resource classes (RESOURCE axis: what the hardware can sustain).
# Orthogonal to node role: e.g. this PC is resource_class CONSTRAINED_RUNTIME
# (16GB RAM, 4GB VRAM) while serving node role DELEGATION_NODE/FULL_RUNTIME.
RESOURCE_CLASS_CONSTRAINED_RUNTIME = "CONSTRAINED_RUNTIME"
RESOURCE_CLASS_FULL_RUNTIME = "FULL_RUNTIME"

RESOURCE_CLASSES = (
    RESOURCE_CLASS_CONSTRAINED_RUNTIME,
    RESOURCE_CLASS_FULL_RUNTIME,
)


@dataclass
class CPUInfo:
    """CPU information."""
    vendor: str = ""
    model: str = ""
    architecture: str = ""  # e.g. "x86_64", "arm64"
    physical_cores: int = 0
    logical_cores: int = 0
    frequency_mhz: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GPUInfo:
    """GPU information."""
    vendor: str = ""
    model: str = ""
    vram_mb: int = 0
    architecture: str = ""
    cuda_available: bool = False
    metal_available: bool = False
    vulkan_available: bool = False
    directml_available: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AcceleratorInfo:
    """AI accelerator information."""
    type: str = ""  # e.g. "npu", "tpu", "other"
    vendor: str = ""
    model: str = ""
    available: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryInfo:
    """Memory information."""
    total_mb: int = 0
    available_mb: int = 0
    swap_total_mb: int = 0
    swap_available_mb: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StorageInfo:
    """Storage information."""
    total_mb: int = 0
    free_mb: int = 0
    drive_type: str = ""  # "ssd", "hdd", "nvme", "unknown"
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatteryInfo:
    """Battery information (if available)."""
    present: bool = False
    charging: bool = False
    level_percent: int = 0
    time_remaining_minutes: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NetworkInfo:
    """Network information."""
    connected: bool = False
    interface_type: str = ""  # "wifi", "ethernet", "cellular", "unknown"
    bandwidth_mbps: int = 0
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DisplayInfo:
    """Display information."""
    resolution: str = ""  # e.g. "1920x1080"
    scaling: float = 1.0
    color_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Media device states: presence detection only (never activates devices)
MEDIA_NOT_PRESENT = "NOT_PRESENT"
MEDIA_HARDWARE_PRESENT = "HARDWARE_PRESENT"
MEDIA_PERMISSION_UNKNOWN = "PERMISSION_UNKNOWN"
MEDIA_AVAILABLE = "AVAILABLE"
MEDIA_DENIED = "DENIED"


@dataclass
class MediaInfo:
    """Presence-only media device information (never records/activates)."""
    camera_present: bool = False
    camera_state: str = MEDIA_PERMISSION_UNKNOWN
    microphone_present: bool = False
    microphone_state: str = MEDIA_PERMISSION_UNKNOWN
    speaker_present: bool = False
    speaker_state: str = MEDIA_PERMISSION_UNKNOWN
    audio_input: bool = False
    audio_output: bool = False
    video_input: bool = False
    detection_method: str = ""
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PackageManagerInfo:
    """Detected package manager (detection only; never installs)."""
    name: str = ""
    path: str = ""
    detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeviceCapabilityProfile:
    """Normalized device capability profile."""
    device_id: str = ""
    device_class: str = DEVICE_CLASS_UNKNOWN
    os: str = OS_UNKNOWN
    os_version: str = ""
    architecture: str = ""
    
    cpu: CPUInfo = field(default_factory=CPUInfo)
    gpu: GPUInfo = field(default_factory=GPUInfo)
    accelerators: list[AcceleratorInfo] = field(default_factory=list)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    storage: StorageInfo = field(default_factory=StorageInfo)
    battery: BatteryInfo = field(default_factory=BatteryInfo)
    network: NetworkInfo = field(default_factory=NetworkInfo)
    display: DisplayInfo = field(default_factory=DisplayInfo)
    media: MediaInfo = field(default_factory=MediaInfo)
    package_managers: list[PackageManagerInfo] = field(default_factory=list)
    
    # Capabilities
    local_inference: bool = False
    browser_available: bool = False
    filesystem_write: bool = False
    background_agent: bool = False
    admin_possible: bool = False
    
    # Performance profile
    performance_profile: str = PROFILE_BALANCED
    
    # Runtime role (cross-device architecture)
    runtime_role: str = RUNTIME_ROLE_FULL_RUNTIME
    # Resource class (hardware capacity axis, orthogonal to runtime_role)
    resource_class: str = RESOURCE_CLASS_FULL_RUNTIME
    
    # Additional metadata
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        data = asdict(self)
        # Convert nested objects to dicts
        data["cpu"] = self.cpu.to_dict()
        data["gpu"] = self.gpu.to_dict()
        data["accelerators"] = [acc.to_dict() for acc in self.accelerators]
        data["memory"] = self.memory.to_dict()
        data["storage"] = self.storage.to_dict()
        data["battery"] = self.battery.to_dict()
        data["network"] = self.network.to_dict()
        data["display"] = self.display.to_dict()
        data["media"] = self.media.to_dict()
        data["package_managers"] = [p.to_dict() for p in self.package_managers]
        return data
    
    def is_mobile(self) -> bool:
        """Check if this is a mobile device."""
        return self.device_class in (DEVICE_CLASS_PHONE, DEVICE_CLASS_TABLET,
                                   DEVICE_CLASS_IPAD, DEVICE_CLASS_SMARTWATCH,
                                   DEVICE_CLASS_SMART_RING, DEVICE_CLASS_SMART_GLASSES)
    
    def is_desktop(self) -> bool:
        """Check if this is a desktop-class device."""
        return self.device_class in (DEVICE_CLASS_DESKTOP, DEVICE_CLASS_WORKSTATION,
                                   DEVICE_CLASS_SERVER, DEVICE_CLASS_LAPTOP)
    
    def has_gpu(self) -> bool:
        """Check if device has a GPU."""
        return bool(self.gpu.vendor and self.gpu.model)
    
    def has_ai_accelerator(self) -> bool:
        """Check if device has an AI accelerator."""
        return any(acc.available for acc in self.accelerators)
    
    def is_battery_powered(self) -> bool:
        """Check if device is battery-powered."""
        return self.battery.present
    
    def is_low_resource(self) -> bool:
        """Check if device is low-resource."""
        return self.performance_profile in (PROFILE_ULTRA_LOW_RESOURCE, PROFILE_MOBILE,
                                          PROFILE_LOW_RESOURCE)
    
    def can_run_local_models(self) -> bool:
        """Check if device can run local AI models."""
        return self.local_inference and self.memory.total_mb >= 4000  # Minimum 4GB RAM