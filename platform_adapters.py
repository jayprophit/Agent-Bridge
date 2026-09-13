"""Cross-platform / cross-device adapter architecture (v0.9.0).

ONE AGENT BRIDGE ARCHITECTURE, MANY PLATFORM ADAPTERS, MANY DEVICE CLASSES,
MANY EXECUTION ENVIRONMENTS.

Core rule: Agent Bridge requests CAPABILITIES, never OS commands.
  BAD:  if Windows: run "winget install cmake"
  GOOD: capability.install("cmake") -> PlatformAdapter -> PackageProvider
        -> InstallationPlan -> Policy -> Execute -> Verify.

The current Windows 10 machine is the FIRST implementation target and test
machine, NOT the architectural limit. Platform-specific behaviour lives
behind the adapter contracts below; the registries, planners, policy and
managers stay OS-neutral.

Support honesty: every platform/capability pair reports one of
SUPPORTED | PARTIALLY_SUPPORTED | DISCOVERY_ONLY | REMOTE_ONLY | PLANNED |
UNSUPPORTED, plus separate ARCHITECTURE_SUPPORT / IMPLEMENTED_ADAPTER /
TESTED_PLATFORM / VERIFIED_CAPABILITIES. Never claim operational support
from an interface alone.

Additive only: nothing here modifies existing modules. No import-time side
effects. No mutations except through policy-gated managers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


# --------------------------------------------------------------------------
# Taxonomies
# --------------------------------------------------------------------------

class SupportLevel(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    DISCOVERY_ONLY = "DISCOVERY_ONLY"
    REMOTE_ONLY = "REMOTE_ONLY"
    PLANNED = "PLANNED"
    UNSUPPORTED = "UNSUPPORTED"


class ControlLevel(str, Enum):
    FULL_CONTROL = "FULL_CONTROL"
    MANAGED_CONTROL = "MANAGED_CONTROL"
    LIMITED_CONTROL = "LIMITED_CONTROL"
    READ_ONLY = "READ_ONLY"
    REMOTE_EXECUTION_ONLY = "REMOTE_EXECUTION_ONLY"
    UNSUPPORTED = "UNSUPPORTED"


class RuntimeProfile(str, Enum):
    FULL = "AGENT_BRIDGE_FULL"
    LIGHT = "AGENT_BRIDGE_LIGHT"
    EDGE = "AGENT_BRIDGE_EDGE"
    CLIENT = "AGENT_BRIDGE_CLIENT"
    REMOTE = "AGENT_BRIDGE_REMOTE"


class Readiness(str, Enum):
    READY = "READY"
    READY_AFTER_SAFE_PROVISIONING = "READY_AFTER_SAFE_PROVISIONING"
    READY_AFTER_APPROVAL = "READY_AFTER_APPROVAL"
    PARTIAL = "PARTIAL"
    REMOTE_RECOMMENDED = "REMOTE_RECOMMENDED"
    INCOMPATIBLE = "INCOMPATIBLE"


class Arch(str, Enum):
    X86 = "x86"
    X86_64 = "x86_64"
    ARM = "arm"
    ARM64 = "arm64"
    RISCV = "riscv"
    UNKNOWN = "unknown"


class PlatformId(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    WSL = "wsl"
    DOCKER = "docker"
    KUBERNETES = "kubernetes"
    CODESPACE = "codespace"
    CLOUD_VM = "cloud_vm"
    SERVER = "server"
    VM = "vm"
    SBC = "sbc"
    ANDROID = "android"
    IOS = "ios"
    EMBEDDED_LINUX = "embedded_linux"
    RTOS = "rtos"
    MCU = "mcu"
    ROBOTICS_GATEWAY = "robotics_gateway"
    AETHERIUS = "aetherius"
    AGENT_BRIDGE_DEVICE = "agent_bridge_device"


# Default control levels per platform (conservative; adapters may narrow).
DEFAULT_CONTROL: dict[str, ControlLevel] = {
    PlatformId.WINDOWS: ControlLevel.FULL_CONTROL,
    PlatformId.LINUX: ControlLevel.FULL_CONTROL,
    PlatformId.MACOS: ControlLevel.FULL_CONTROL,
    PlatformId.WSL: ControlLevel.FULL_CONTROL,
    PlatformId.DOCKER: ControlLevel.MANAGED_CONTROL,
    PlatformId.KUBERNETES: ControlLevel.MANAGED_CONTROL,
    PlatformId.CODESPACE: ControlLevel.FULL_CONTROL,
    PlatformId.CLOUD_VM: ControlLevel.FULL_CONTROL,
    PlatformId.SERVER: ControlLevel.MANAGED_CONTROL,
    PlatformId.VM: ControlLevel.MANAGED_CONTROL,
    PlatformId.SBC: ControlLevel.MANAGED_CONTROL,
    PlatformId.ANDROID: ControlLevel.LIMITED_CONTROL,
    PlatformId.IOS: ControlLevel.LIMITED_CONTROL,
    PlatformId.EMBEDDED_LINUX: ControlLevel.MANAGED_CONTROL,
    PlatformId.RTOS: ControlLevel.LIMITED_CONTROL,
    PlatformId.MCU: ControlLevel.LIMITED_CONTROL,
    PlatformId.ROBOTICS_GATEWAY: ControlLevel.MANAGED_CONTROL,
    PlatformId.AETHERIUS: ControlLevel.MANAGED_CONTROL,
    PlatformId.AGENT_BRIDGE_DEVICE: ControlLevel.FULL_CONTROL,
}


# --------------------------------------------------------------------------
# Adapter contracts
# --------------------------------------------------------------------------

class CapabilityAdapter(ABC):
    """Generic capability contract: every provider/tool plugs in here.

    Core orchestration talks to this interface only; products never leak
    OS-specific commands upward.
    """
    capability: str = ""

    @abstractmethod
    def detect(self) -> dict[str, Any]: ...

    @abstractmethod
    def plan(self, requirement: dict[str, Any],
             detection: dict[str, Any]) -> list[str]: ...

    @abstractmethod
    def verify(self) -> dict[str, Any]: ...


class PackageManagerAdapter(ABC):
    """Discover + install via one package ecosystem. No OS commands in core."""
    name: str = ""
    platforms: tuple[str, ...] = ()
    archs: tuple[str, ...] = ("x86_64", "arm64")

    def supports(self, platform: str, arch: str) -> bool:
        return platform in self.platforms and arch in self.archs

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def install_plan(self, package: str, version: str = "") -> list[str]: ...


class ServiceManagerAdapter(ABC):
    """Core requests service.start(name); adapters map to OS primitives."""
    @abstractmethod
    def status(self, name: str) -> dict[str, Any]: ...
    @abstractmethod
    def start(self, name: str) -> dict[str, Any]: ...
    @abstractmethod
    def stop(self, name: str) -> dict[str, Any]: ...


class ShellAdapter(ABC):
    @abstractmethod
    def run(self, command: str, timeout_s: float = 60.0) -> dict[str, Any]: ...


class FilesystemAdapter(ABC):
    """Path semantics per platform; reuse/extend WSL contracts."""
    @abstractmethod
    def normalize(self, path: str) -> str: ...
    @abstractmethod
    def translate(self, path: str, target: str) -> str: ...


class ContainerAdapter(ABC):
    runtime_name: str = ""

    @abstractmethod
    def available(self) -> bool: ...
    @abstractmethod
    def supports_compose(self) -> bool: ...


class VirtualizationAdapter(ABC):
    @abstractmethod
    def available(self) -> dict[str, Any]: ...


class DeviceAdapter(ABC):
    platform: str = ""

    def control_level(self) -> ControlLevel:
        return DEFAULT_CONTROL.get(self.platform, ControlLevel.UNSUPPORTED)

    @abstractmethod
    def sensors(self) -> list[str]: ...


class DriverAdapter(ABC):
    @abstractmethod
    def detect(self) -> list[dict[str, Any]]: ...
    # Replacement plans are approval-gated by MaintenancePolicy; no execute here.


class FirmwareMetadataAdapter(ABC):
    @abstractmethod
    def versions(self) -> list[dict[str, Any]]: ...
    @abstractmethod
    def update_metadata(self, device: str) -> dict[str, Any]: ...
    # Flashing is NEVER implemented on adapters; owner-approved flow only.


class RemoteExecutionAdapter(ABC):
    environment: str = ""

    @abstractmethod
    def reachable(self) -> bool: ...
    @abstractmethod
    def submit(self, workload: dict[str, Any],
               dry_run: bool = True) -> dict[str, Any]: ...


class PlatformAdapter(ABC):
    """Binds one platform to its providers. The core talks only to this."""
    platform: PlatformId = PlatformId.LINUX
    arch: Arch = Arch.X86_64

    @abstractmethod
    def package_providers(self) -> list[PackageManagerAdapter]: ...
    @abstractmethod
    def service_manager(self) -> ServiceManagerAdapter: ...
    @abstractmethod
    def shell(self) -> ShellAdapter: ...
    @abstractmethod
    def filesystem(self) -> FilesystemAdapter: ...
    @abstractmethod
    def support(self, capability: str) -> SupportLevel: ...

    def control_level(self) -> ControlLevel:
        return DEFAULT_CONTROL.get(self.platform.value, ControlLevel.UNSUPPORTED)


# --------------------------------------------------------------------------
# Registry + support matrix (honesty by default: UNSUPPORTED)
# --------------------------------------------------------------------------

class PlatformRegistry:
    def __init__(self):
        self._adapters: dict[str, PlatformAdapter] = {}
        self._matrix: dict[tuple[str, str], SupportLevel] = {}

    def register(self, adapter: PlatformAdapter,
                 capabilities: dict[str, SupportLevel] | None = None) -> None:
        self._adapters[adapter.platform.value] = adapter
        for cap, level in (capabilities or {}).items():
            self._matrix[(adapter.platform.value, cap)] = level

    def get(self, platform: str) -> PlatformAdapter | None:
        return self._adapters.get(platform)

    def platforms(self) -> list[str]:
        return sorted(self._adapters)

    def support(self, platform: str, capability: str) -> SupportLevel:
        if platform not in self._adapters:
            return SupportLevel.UNSUPPORTED
        return self._matrix.get((platform, capability), SupportLevel.UNSUPPORTED)

    def support_report(self, platform: str) -> dict[str, Any]:
        adapter = self.get(platform)
        if adapter is None:
            return {"platform": platform,
                    "architecture_support": "ABSENT",
                    "implemented_adapter": False,
                    "tested_platform": False,
                    "verified_capabilities": []}
        caps = {cap: lvl.value for (plat, cap), lvl in self._matrix.items()
                if plat == platform}
        return {"platform": platform,
                "architecture_support": "PRESENT",
                "implemented_adapter": True,
                "tested_platform": False,
                "verified_capabilities": sorted(
                    c for c, v in caps.items() if v == "SUPPORTED"),
                "capabilities": caps}


# --------------------------------------------------------------------------
# Capability-based resolution (no OS commands in core)
# --------------------------------------------------------------------------

# capability -> platform -> provider preference (data, not code paths).
PROVIDER_MAP: dict[str, dict[str, str]] = {
    "cmake": {"windows": "winget", "linux": "apt-or-distro",
              "macos": "brew", "wsl": "apt", "codespace": "devcontainer",
              "remote": "remote-adapter"},
    "python": {"windows": "winget", "linux": "apt-or-distro",
               "macos": "brew", "wsl": "apt", "codespace": "devcontainer",
               "remote": "remote-adapter"},
    "node": {"windows": "winget", "linux": "distro-or-nvm",
             "macos": "brew", "wsl": "apt", "codespace": "devcontainer",
             "remote": "remote-adapter"},
    "docker": {"windows": "official-installer", "linux": "distro-or-official",
               "macos": "official-installer", "wsl": "host-docker",
               "codespace": "preinstalled", "remote": "remote-adapter"},
}


def resolve_capability(capability: str, platform: str,
                       providers: list[PackageManagerAdapter] | None = None,
                       arch: str = "x86_64") -> dict[str, Any]:
    """capability.install(name): pick provider for platform+arch, or explain why not."""
    hint = PROVIDER_MAP.get(capability, {}).get(platform, "")
    compatible = [p for p in (providers or [])
                  if p.supports(platform, arch) and p.is_available()]
    if compatible:
        best = sorted(compatible, key=lambda p: p.name)[0]
        return {"capability": capability, "platform": platform,
                "provider": best.name, "hint": hint, "ok": True}
    if hint:
        return {"capability": capability, "platform": platform,
                "provider": "", "hint": hint, "ok": False,
                "reason": "no available provider on this platform"}
    return {"capability": capability, "platform": platform,
            "provider": "", "hint": "", "ok": False,
            "reason": "unknown capability or unsupported platform"}


def check_arch_compatible(required_arch: str, host_arch: str) -> bool:
    if required_arch == host_arch:
        return True
    # ARM64 hosts can usually run ARM; nothing else is assumed compatible.
    if host_arch == Arch.ARM64.value and required_arch == Arch.ARM.value:
        return True
    return False


INFERENCE_BACKENDS: tuple[tuple[str, str], ...] = (
    ("cuda", "NVIDIA CUDA system"),
    ("metal", "Apple Silicon"),
    ("vulkan", "generic GPU"),
    ("cpu", "CPU-only device"),
    ("remote", "insufficient local resources"),
)


def resolve_inference(gpu_vendor: str, arch: str, ram_gb: float,
                      vram_mb: float) -> dict[str, Any]:
    """Request local_ai_inference, not 'install CUDA'."""
    vendor = (gpu_vendor or "").lower()
    if "nvidia" in vendor and vram_mb >= 2000:
        return {"request": "local_ai_inference", "backend": "cuda",
                "reason": "NVIDIA GPU with sufficient VRAM"}
    if arch == Arch.ARM64.value and ("apple" in vendor or not vendor):
        return {"request": "local_ai_inference", "backend": "metal",
                "reason": "Apple Silicon unified memory"}
    if vram_mb >= 1000:
        return {"request": "local_ai_inference", "backend": "vulkan",
                "reason": "generic GPU fallback"}
    if ram_gb >= 8:
        return {"request": "local_ai_inference", "backend": "cpu",
                "reason": "CPU-only runtime, small models"}
    return {"request": "local_ai_inference", "backend": "remote",
            "reason": "LOCAL_UNSUITABLE: route to remote execution"}


# --------------------------------------------------------------------------
# Environment selection across all registered environments
# --------------------------------------------------------------------------

@dataclass
class EnvironmentScore:
    environment: str = ""
    score: int = 0  # lower is better
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class EnvironmentSelector:
    """Evaluate ALL registered environments; pick by compatibility, health,
    performance, resource cost, security, privacy, availability, latency."""

    WEIGHTS = {"incompatible": 10000, "unhealthy": 1000, "degraded": 100,
               "privacy": 50, "cost": 10, "latency": 5}

    def select(self, requirement: str,
               environments: list[dict[str, Any]]) -> list[EnvironmentScore]:
        scored = []
        for env in environments:
            s = EnvironmentScore(environment=str(env.get("name", "")))
            caps = set(env.get("capabilities", []))
            if requirement not in caps:
                s.score += self.WEIGHTS["incompatible"]
                s.warnings.append(f"lacks {requirement}")
                scored.append(s)
                continue
            health = str(env.get("health", "UNKNOWN"))
            if health != "HEALTHY":
                s.score += self.WEIGHTS["degraded"] if health == "DEGRADED" \
                    else self.WEIGHTS["unhealthy"]
                s.warnings.append(f"health={health}")
            s.score += int(env.get("cost", 0)) * self.WEIGHTS["cost"]
            s.score += int(env.get("latency_ms", 0)) // 100 * self.WEIGHTS["latency"]
            if env.get("remote") and env.get("private_data"):
                s.score += self.WEIGHTS["privacy"]
                s.warnings.append("private data would leave the machine")
            s.reasons.append(f"provides {requirement}")
            scored.append(s)
        scored.sort(key=lambda e: (e.score, e.environment))
        return scored


# --------------------------------------------------------------------------
# Device capability passport (portable, no private hardware IDs)
# --------------------------------------------------------------------------

@dataclass
class DeviceCapabilityPassport:
    device_id: str = ""  # opaque local identifier, never a serial/MAC
    device_class: str = ""
    operating_system: str = ""
    os_version: str = ""
    architecture: str = ""
    cpu: str = ""
    memory_gb: float = 0.0
    gpu: str = ""
    vram_mb: float = 0.0
    storage_gb: float = 0.0
    power_profile: str = ""
    network: str = ""
    execution_environments: list[str] = field(default_factory=list)
    package_providers: list[str] = field(default_factory=list)
    available_toolchains: list[str] = field(default_factory=list)
    available_languages: list[str] = field(default_factory=list)
    container_capabilities: list[str] = field(default_factory=list)
    virtualisation: str = ""
    ai_runtimes: list[str] = field(default_factory=list)
    sensors: list[str] = field(default_factory=list)
    connected_devices: list[str] = field(default_factory=list)
    control_level: str = ""
    health: str = ""
    supported_capabilities: list[str] = field(default_factory=list)
    degraded_capabilities: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_passport(machine: Any, environments: list[str],
                   control_level: str = "") -> DeviceCapabilityPassport:
    """Build a passport from a Phase 1 machine snapshot (read-only)."""
    cpu = getattr(machine, "cpu", None)
    mem = getattr(machine, "memory", None)
    gpus = getattr(machine, "gpus", None) or []
    gpu0 = gpus[0] if gpus else None
    tools = [getattr(t, "name", "") for t in (getattr(machine, "tools", None) or [])
             if getattr(t, "working", False)]
    total_ram_mb = getattr(mem, "total_mb", 0) if mem else 0
    return DeviceCapabilityPassport(
        operating_system=str(getattr(getattr(machine, "os", None),
                                     "platform", "")),
        architecture=str(getattr(cpu, "architecture", "")) if cpu else "",
        cpu=str(getattr(cpu, "model", "")) if cpu else "",
        memory_gb=round((total_ram_mb or 0) / 1024, 1),
        gpu=str(getattr(gpu0, "model", "")) if gpu0 else "",
        vram_mb=float(getattr(gpu0, "vram_mb", 0) or 0) if gpu0 else 0.0,
        execution_environments=list(environments),
        available_toolchains=[],
        available_languages=[],
        control_level=control_level,
    )


# --------------------------------------------------------------------------
# Project readiness: CAN_THIS_ENVIRONMENT_RUN_THIS_PROJECT?
# --------------------------------------------------------------------------

def evaluate_readiness(requirements: list[str], present: list[str],
                       degraded: list[str] | None = None,
                       approval_needed: list[str] | None = None,
                       remote_available: bool = False) -> dict[str, Any]:
    degraded = set(degraded or [])
    approval_needed = set(approval_needed or [])
    missing = [r for r in requirements if r not in present]
    if missing:
        if remote_available:
            return {"readiness": Readiness.REMOTE_RECOMMENDED.value,
                    "missing": missing}
        return {"readiness": Readiness.INCOMPATIBLE.value, "missing": missing}
    bad = [r for r in requirements if r in degraded]
    gated = [r for r in requirements if r in approval_needed]
    if gated:
        return {"readiness": Readiness.READY_AFTER_APPROVAL.value,
                "gated": gated}
    if bad:
        return {"readiness": Readiness.READY_AFTER_SAFE_PROVISIONING.value,
                "degraded": bad}
    if degraded:
        return {"readiness": Readiness.PARTIAL.value,
                "notes": "unrelated capabilities degraded"}
    return {"readiness": Readiness.READY.value}


# --------------------------------------------------------------------------
# Physical safety (SCOPES): intent validation outranks reasoning agents
# --------------------------------------------------------------------------

DENIED_INTENTS = frozenset({"weapon", "harm", "bypass_safety", "disable_interlock"})


class SafetySupervisor:
    """AI requests INTENT; safety layer decides. Never auto-approve physical."""

    def __init__(self, limits: dict[str, Any] | None = None):
        self.limits = limits or {}

    def validate_intent(self, intent: str, target: str,
                        low_level_control: bool = False) -> dict[str, Any]:
        text = f"{intent} {target}".lower()
        if any(bad in text for bad in DENIED_INTENTS):
            return {"intent": intent, "decision": "DENY",
                    "reason": "prohibited intent class"}
        if low_level_control:
            return {"intent": intent, "decision": "REQUIRE_APPROVAL",
                    "reason": "low-level physical control needs safety review"}
        envelope = self.limits.get(intent)
        if envelope is None:
            return {"intent": intent, "decision": "REQUIRE_APPROVAL",
                    "reason": "no safety envelope registered"}
        return {"intent": intent, "decision": "ALLOW_WITHIN_ENVELOPE",
                "reason": f"within {intent} envelope"}
