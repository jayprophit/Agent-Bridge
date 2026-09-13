"""System Adaptation + Kernel Capability Layer (v0.9.0).

LOCKED ARCHITECTURE SENTENCE:
"Aetherius may be developed and tested from existing operating systems,
virtual machines and cloud environments, but the final Aetherius
architecture must be capable of booting and operating directly on
supported hardware without requiring a host operating system."

Stack (current dev host is ONE node, not the target):
  Applications / Projects / AI -> Agent Bridge -> SystemAdaptationLayer
  -> OSConfigurationAdapter / KernelCapabilityAdapter -> OS/Kernel -> HW.

Final target: HARDWARE -> AETHERIUS -> AGENT BRIDGE -> GENESIS -> OE/APPS.

Rules:
  - ADDITIVE ONLY. Reuses Phase 1 registries + maintenance/provisioning
    managers. No kernel modification, no bootloader/disk/firmware changes,
    no custom drivers — contracts only.
  - Core requests capabilities (package.install, service.start,
    filesystem.resolve, process.limit, resource.allocate); platform and
    kernel specifics live behind adapters.
  - Risk levels L0-L5 gate every operation; L3+ always needs explicit
    approval; L5 needs separate explicit approval, never silent.
  - Aetherius contracts below are DEFINED interfaces for a PLANNED system:
    standalone OS, bootable image and installer are NOT_IMPLEMENTED.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


LOCKED_SENTENCE = (
    "Aetherius may be developed and tested from existing operating systems, "
    "virtual machines and cloud environments, but the final Aetherius "
    "architecture must be capable of booting and operating directly on "
    "supported hardware without requiring a host operating system."
)

ARCHITECTURE_PRINCIPLES: tuple[str, ...] = (
    "Agent Bridge is not a Windows application architecture.",
    "The current Windows PC is the first development/test node.",
    "System configuration belongs behind platform-neutral capability contracts.",
    "Kernel control is optional and platform-dependent.",
    "Prefer user-space/system adaptation before kernel modification.",
    "High-risk kernel/driver/firmware/boot operations remain approval gated.",
    "Aetherius is intended to become a standalone bootable operating system.",
    "Aetherius must eventually run without a host OS.",
    "A Linux kernel foundation is acceptable and preferred initially.",
    "Custom kernel configuration/patches only with documented benefit.",
    "Agent Bridge must survive the transition to Aetherius-native deployment.",
    "Genesis reasons; Agent Bridge executes/enforces; Aetherius hosts.",
    "Build/test safely in VMs before bare-metal installation.",
    "Capability-based design overrides product-specific hardcoding.",
)

ROADMAP: tuple[tuple[str, str], ...] = (
    ("STAGE A", "Agent Bridge portable user-space runtime"),
    ("STAGE B", "Cross-platform provisioning + system adaptation"),
    ("STAGE C", "Linux-native deeper integration"),
    ("STAGE D", "Aetherius userspace prototype"),
    ("STAGE E", "Aetherius bootable VM image"),
    ("STAGE F", "Aetherius installer/live image"),
    ("STAGE G", "Spare-hardware fresh installation"),
    ("STAGE H", "Hardware compatibility expansion"),
    ("STAGE I", "Custom kernel configuration where justified"),
    ("STAGE J", "Production standalone Aetherius OS"),
)


# --------------------------------------------------------------------------
# Risk levels L0-L5
# --------------------------------------------------------------------------

class RiskLevel(str, Enum):
    L0_READ_ONLY = "LEVEL_0_READ_ONLY"
    L1_USER_SPACE_SAFE = "LEVEL_1_USER_SPACE_SAFE"
    L2_OS_CONFIGURATION = "LEVEL_2_OS_CONFIGURATION"
    L3_DRIVER_OR_KERNEL = "LEVEL_3_DRIVER_OR_KERNEL_CONFIGURATION"
    L4_KERNEL_DEVELOPMENT = "LEVEL_4_KERNEL_DEVELOPMENT"
    L5_FIRMWARE_BOOT_DISK = "LEVEL_5_FIRMWARE_BOOT_DISK"


RISK_POLICY: dict[str, str] = {
    RiskLevel.L0_READ_ONLY: "ALLOW",
    RiskLevel.L1_USER_SPACE_SAFE: "POLICY",
    RiskLevel.L2_OS_CONFIGURATION: "POLICY",
    RiskLevel.L3_DRIVER_OR_KERNEL: "REQUIRE_APPROVAL",
    RiskLevel.L4_KERNEL_DEVELOPMENT: "REQUIRE_APPROVAL_DEV_WORKFLOW",
    RiskLevel.L5_FIRMWARE_BOOT_DISK: "REQUIRE_SEPARATE_APPROVAL",
}


def risk_decision(level: RiskLevel, policy_allows: bool = False) -> str:
    """Map a risk level to a decision. L3+ can never be auto-allowed."""
    base = RISK_POLICY[level]
    if level in (RiskLevel.L3_DRIVER_OR_KERNEL, RiskLevel.L4_KERNEL_DEVELOPMENT,
                 RiskLevel.L5_FIRMWARE_BOOT_DISK):
        return base
    if base == "POLICY":
        return "ALLOW" if policy_allows else "REQUIRE_APPROVAL"
    return base


# --------------------------------------------------------------------------
# Kernel capability adapter (optional, platform-specific, policy-controlled)
# --------------------------------------------------------------------------

class KernelCapability(str, Enum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    READ_ONLY = "READ_ONLY"
    CONFIGURATION_ONLY = "CONFIGURATION_ONLY"
    MANAGED = "MANAGED"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    FULL_PLATFORM_CONTROL = "FULL_PLATFORM_CONTROL"


class KernelCapabilityAdapter(ABC):
    """Optional kernel abstraction. Core never requires kernel modification."""
    platform: str = ""

    @abstractmethod
    def level(self) -> KernelCapability: ...

    @abstractmethod
    def facilities(self) -> dict[str, str]: ...


WINDOWS_KERNEL_INTERFACES: dict[str, str] = {
    "process APIs": "CONFIGURATION_ONLY",
    "Job Objects": "CONFIGURATION_ONLY",
    "Windows Services": "CONFIGURATION_ONLY",
    "power-management APIs": "CONFIGURATION_ONLY",
    "supported networking configuration": "CONFIGURATION_ONLY",
    "WSL": "MANAGED",
    "Hyper-V/virtualisation interfaces": "CONFIGURATION_ONLY",
    "filesystem APIs": "READ_ONLY",
    "device APIs": "READ_ONLY",
    "custom kernel drivers": "DEVELOPMENT_ONLY",
    "kernel patch/replacement": "NOT_AVAILABLE",
}

LINUX_KERNEL_FACILITIES: dict[str, str] = {
    "cgroups": "CONFIGURATION_ONLY",
    "namespaces": "CONFIGURATION_ONLY",
    "sysctl": "CONFIGURATION_ONLY",
    "I/O priorities": "CONFIGURATION_ONLY",
    "CPU affinity": "CONFIGURATION_ONLY",
    "scheduler-exposed controls": "CONFIGURATION_ONLY",
    "network namespaces": "CONFIGURATION_ONLY",
    "mounts/filesystems": "CONFIGURATION_ONLY",
    "huge-page configuration": "CONFIGURATION_ONLY",
    "CPU governors": "CONFIGURATION_ONLY",
    "eBPF capabilities": "READ_ONLY",
    "kernel-module discovery": "READ_ONLY",
    "arbitrary module loading": "DEVELOPMENT_ONLY",
}

MOBILE_CONSTRAINTS: dict[str, str] = {
    "android": "LIMITED_CONTROL: sandbox + permissions only",
    "ios": "LIMITED_CONTROL: sandbox + permissions only",
}


class WindowsKernelAdapter(KernelCapabilityAdapter):
    platform = "windows"

    def level(self) -> KernelCapability:
        return KernelCapability.CONFIGURATION_ONLY

    def facilities(self) -> dict[str, str]:
        return dict(WINDOWS_KERNEL_INTERFACES)


class LinuxKernelAdapter(KernelCapabilityAdapter):
    platform = "linux"

    def level(self) -> KernelCapability:
        return KernelCapability.CONFIGURATION_ONLY

    def facilities(self) -> dict[str, str]:
        return dict(LINUX_KERNEL_FACILITIES)


# --------------------------------------------------------------------------
# Hardware capability adapter (factual, read-first)
# --------------------------------------------------------------------------

class HardwareCapabilityAdapter(ABC):
    @abstractmethod
    def detect(self) -> dict[str, Any]: ...


class StaticHardwareAdapter(HardwareCapabilityAdapter):
    """Factual snapshot supplied by MachineCapabilityRegistry (no probing)."""

    def __init__(self, snapshot: dict[str, Any]):
        self.snapshot = snapshot

    def detect(self) -> dict[str, Any]:
        keys = ("architecture", "cpu", "memory_gb", "gpu", "vram_mb",
                "storage_gb", "power_profile", "network",
                "virtualisation", "sensors", "connected_devices")
        return {k: self.snapshot.get(k) for k in keys}


# --------------------------------------------------------------------------
# System adaptation layer (coordinator; delegates, never duplicates)
# --------------------------------------------------------------------------

class SystemAdaptationLayer:
    """Coordinates resource/process/service/environment/storage/network/
    device/container/VM/power/performance/security/provisioning/repair/
    configuration/verification through existing registries and managers."""

    def __init__(self, machine: Any = None):
        self.machine = machine

    def capability_snapshot(self) -> dict[str, Any]:
        if self.machine is None:
            from machine_capability import discover_machine_capability
            from machine_capability import MachineCapabilityRegistry
            self.machine = discover_machine_capability()
            return MachineCapabilityRegistry().to_dict(self.machine)
        from machine_capability import MachineCapabilityRegistry
        return MachineCapabilityRegistry().to_dict(self.machine)

    def describe(self) -> dict[str, Any]:
        return {"layer": "SystemAdaptationLayer",
                "delegates": ["MachineCapabilityRegistry",
                              "ExecutionEnvironmentRegistry",
                              "ToolchainRegistry", "LanguageRegistry",
                              "RepairManager", "UpdateManager",
                              "InstallationManager", "VerificationManager"],
                "kernel": "optional adapters only",
                "mutations": "policy-gated managers only"}


# --------------------------------------------------------------------------
# Optimizer (pure decisions; execution stays with gated managers)
# --------------------------------------------------------------------------

@dataclass
class ResourceSnapshot:
    ram_total_gb: float = 0.0
    ram_free_gb: float = 0.0
    consumers_gb: dict[str, float] = field(default_factory=dict)
    disk_free_gb: float = 0.0
    cpu_load_pct: float = 0.0
    battery_pct: float | None = None


@dataclass
class OptimizationAction:
    action: str = ""
    target: str = ""
    reason: str = ""
    reversible: bool = True
    risk: RiskLevel = RiskLevel.L1_USER_SPACE_SAFE


class ResourcePlacementEngine:
    """OPTIMUM whole-system utilisation, not maximum consumption."""

    @staticmethod
    def plan(snapshot: ResourceSnapshot, demand_gb: float,
             remotes: list[str] | None = None) -> list[OptimizationAction]:
        actions: list[OptimizationAction] = []
        free = snapshot.ram_free_gb
        if free >= demand_gb:
            return [OptimizationAction("execute", "local",
                                       "sufficient headroom")]
        # Free headroom first: models, disposable containers, idle services.
        for consumer in ("ai-model", "docker-disposable", "dev-service"):
            used = snapshot.consumers_gb.get(consumer, 0.0)
            if used > 0 and free < demand_gb:
                actions.append(OptimizationAction(
                    "release", consumer,
                    f"reclaim {used}GB headroom", True))
                free += used
        if free >= demand_gb:
            actions.append(OptimizationAction("execute", "local",
                                              "headroom reclaimed"))
            return actions
        actions.append(OptimizationAction("reduce-parallelism", "build",
                                          "lower peak memory"))
        if remotes:
            actions.append(OptimizationAction(
                "route-remote", remotes[0],
                "LOCAL_UNSUITABLE for demand", True,
                RiskLevel.L0_READ_ONLY))
        actions.append(OptimizationAction("execute", "local",
                                          "best effort after shaping"))
        return actions


class SystemOptimizer:
    def __init__(self):
        self.placement = ResourcePlacementEngine()

    def optimize(self, snapshot: ResourceSnapshot, demand_gb: float,
                 remotes: list[str] | None = None) -> dict[str, Any]:
        actions = self.placement.plan(snapshot, demand_gb, remotes)
        return {"actions": [asdict(a) for a in actions],
                "principle": "optimum utilisation, verified + reversible"}


# --------------------------------------------------------------------------
# Passport extension (§26 fields; no private hardware IDs)
# --------------------------------------------------------------------------

PASSPORT_SYSTEM_FIELDS: tuple[str, ...] = (
    "kernel_family", "kernel_version", "kernel_capability_level",
    "boot_environment", "firmware_interface", "service_manager",
    "package_providers", "filesystem_capabilities",
    "virtualisation_capabilities", "container_capabilities",
    "resource_control_capabilities", "power_management_capabilities",
    "device_control_capabilities", "system_adaptation_capabilities",
)


def extend_passport(base: dict[str, Any],
                    system: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(base)
    provided = system or {}
    for name in PASSPORT_SYSTEM_FIELDS + PASSPORT_COMPUTE_FIELDS:
        merged.setdefault(name, provided.get(name, ""))
    return merged


# --------------------------------------------------------------------------
# Aetherius reservations (DEFINED contracts, NOT_IMPLEMENTED system)
# --------------------------------------------------------------------------

class AetheriusAdapterContract:
    """Base for all Aetherius adapters: honest PLANNED status."""
    platform = "aetherius"
    maturity = "DEFINED_CONTRACT"

    def support(self, capability: str) -> str:
        return "PLANNED"

    def control_level(self) -> str:
        return "MANAGED_CONTROL"


class AetheriusPlatformAdapter(AetheriusAdapterContract):
    pass


class AetheriusPackageAdapter(AetheriusAdapterContract):
    pass


class AetheriusServiceAdapter(AetheriusAdapterContract):
    pass


class AetheriusFilesystemAdapter(AetheriusAdapterContract):
    pass


class AetheriusKernelAdapter(AetheriusAdapterContract):
    pass


class AetheriusDeviceAdapter(AetheriusAdapterContract):
    pass


class AetheriusSecurityAdapter(AetheriusAdapterContract):
    pass


class AetheriusBootAdapter(AetheriusAdapterContract):
    pass


class AetheriusUpdateAdapter(AetheriusAdapterContract):
    pass


AETHERIUS_MATURITY = {
    "architecture_contract": "DEFINED",
    "adapter_implemented": False,
    "integration_tested": False,
    "real_hardware_tested": False,
    "production_ready": False,
    "standalone_os": "NOT_IMPLEMENTED",
    "bootable_image": "NOT_IMPLEMENTED",
    "initial_kernel_strategy": "LINUX_KERNEL_FOUNDATION",
    "bootstrap_kernel_strategy": "LINUX_KERNEL_FOUNDATION",
    "final_kernel_strategy": "AETHERIUS_NATIVE_KERNEL",
    "binary_domain": "PLANNED",
    "ternary_domain": "PLANNED",
    "quantum_domain": "PLANNED",
    "hybrid_compute": "PLANNED",
}


def maturity_report() -> dict[str, Any]:
    return {"aetherius": dict(AETHERIUS_MATURITY),
            "standalone_requirement_locked": True,
            "host_os_dependency_final": False}


# --------------------------------------------------------------------------
# Native-kernel amendment: long-term AETHERIUS_NATIVE_KERNEL target.
# Linux is BOOTSTRAP/REFERENCE/COMPAT target, NOT the permanent kernel.
# Nothing below implements a kernel; it locks requirements + research map.
# --------------------------------------------------------------------------

AETHERIUS_BOOTSTRAP_KERNEL_STRATEGY = "LINUX_KERNEL_FOUNDATION"
AETHERIUS_FINAL_KERNEL_STRATEGY = "AETHERIUS_NATIVE_KERNEL"


class ComputeDomain(str, Enum):
    BINARY = "BINARY"
    TERNARY = "TERNARY"
    QUANTUM = "QUANTUM"
    HYBRID = "HYBRID"


class WorkloadKind(str, Enum):
    BINARY_ONLY = "BINARY_ONLY"
    TERNARY_ONLY = "TERNARY_ONLY"
    QUANTUM_ONLY = "QUANTUM_ONLY"
    BINARY_TERNARY = "BINARY_TERNARY"
    BINARY_QUANTUM = "BINARY_QUANTUM"
    TERNARY_QUANTUM = "TERNARY_QUANTUM"
    HYBRID = "HYBRID"


class QuantumBackend(str, Enum):
    SIMULATOR = "SIMULATOR"
    LOCAL_ACCELERATOR = "LOCAL_ACCELERATOR"
    REMOTE_BACKEND = "REMOTE_BACKEND"
    NOT_AVAILABLE = "NOT_AVAILABLE"


# Balanced-trit utilities. EMULATED on binary hardware; never presented as
# native ternary silicon. Trit values are strictly -1, 0, +1.
TRIT_VALUES: tuple[int, ...] = (-1, 0, 1)


def pack_trits(trits: list[int]) -> bytes:
    """Encode balanced trits into bytes (emulation transport, not hardware)."""
    for t in trits:
        if t not in TRIT_VALUES:
            raise ValueError(f"not a trit: {t!r}")
    out = bytearray()
    for i in range(0, len(trits), 5):  # 3^5=243 fits one byte
        chunk = (trits[i:i + 5] + [0] * 5)[:5]  # pad tail with 0-trits
        value = 0
        for t in chunk:
            value = value * 3 + (t + 1)
        out.append(value)
    return bytes(out)


def unpack_trits(data: bytes, count: int) -> list[int]:
    trits: list[int] = []
    for byte in data:
        digits: list[int] = []
        value = byte
        for _ in range(5):
            digits.append((value % 3) - 1)
            value //= 3
        trits.extend(reversed(digits))
    return trits[:count]


def ternary_add(a: list[int], b: list[int]) -> list[int]:
    """Balanced-ternary addition (least-significant trit first)."""
    out: list[int] = []
    carry = 0
    for x, y in zip(a, b):
        total = x + y + carry
        if total > 1:
            out.append(total - 3)
            carry = 1
        elif total < -1:
            out.append(total + 3)
            carry = -1
        else:
            out.append(total)
            carry = 0
    if carry:
        out.append(carry)
    return out


class UnifiedComputeArchitecture:
    """One capability request in, planned domain/backend out.

    Callers request solve(problem, requirements); never a backend directly.
    """

    @staticmethod
    def request(problem: str, requirements: dict[str, Any],
                backends: dict[str, bool] | None = None) -> dict[str, Any]:
        backends = backends or {}
        wants_quantum = bool(requirements.get("quantum_suitable"))
        wants_lowbit = bool(requirements.get("low_bit_inference"))
        precision = str(requirements.get("precision", "standard"))
        if wants_quantum:
            if backends.get("quantum_simulator"):
                return {"problem": problem, "domain": "QUANTUM",
                        "backend": QuantumBackend.SIMULATOR.value}
            if backends.get("quantum_remote"):
                return {"problem": problem, "domain": "QUANTUM",
                        "backend": QuantumBackend.REMOTE_BACKEND.value}
            return {"problem": problem, "domain": "BINARY",
                    "backend": "cpu-fallback",
                    "note": "QUANTUM_BACKEND_NOT_AVAILABLE; classical fallback"}
        if wants_lowbit and precision != "high" and backends.get("ternary"):
            return {"problem": problem, "domain": "TERNARY",
                    "backend": "emulated-encoder"}
        return {"problem": problem, "domain": "BINARY", "backend": "native"}


class ExecutionPlanner:
    """Plans BINARY/TERNARY/QUANTUM/HYBRID placement from task traits."""

    @staticmethod
    def plan(task: dict[str, Any],
             backends: dict[str, bool] | None = None) -> dict[str, Any]:
        parts = []
        if task.get("needs_control_io"):
            parts.append("BINARY")
        if task.get("needs_lowbit"):
            parts.append("TERNARY")
        if task.get("needs_quantum"):
            parts.append("QUANTUM")
        kind = {"BINARY": "BINARY_ONLY", "TERNARY": "TERNARY_ONLY",
                "QUANTUM": "QUANTUM_ONLY"}.get("+".join(parts), "HYBRID" if len(parts) > 1 else "BINARY_ONLY")
        routed = UnifiedComputeArchitecture.request(
            task.get("name", "task"), task, backends)
        return {"workload": kind, "routed": routed}


KERNEL_RESEARCH_AREAS: tuple[str, ...] = (
    "boot", "interrupt handling", "system calls", "processes", "threads",
    "scheduling", "memory management", "virtual memory", "IPC",
    "capability/security model", "drivers", "device abstraction",
    "filesystems", "storage", "network stack", "timers", "power management",
    "multiprocessing", "NUMA", "accelerators", "virtualisation",
    "containers/isolation", "real-time workloads", "fault isolation",
    "logging", "recovery", "debugging", "binary compatibility",
    "ternary compute", "quantum compute interfaces", "distributed compute",
)

KERNEL_ARCH_OPTIONS: tuple[str, ...] = (
    "monolithic", "microkernel", "hybrid", "exokernel", "unikernel",
    "novel-hybrid",
)

KERNEL_MILESTONES: tuple[str, ...] = (
    "boot", "console output", "interrupt handling", "memory management",
    "scheduler", "processes/tasks", "IPC", "basic device support",
    "filesystem", "userspace", "networking", "Agent Bridge minimal runtime",
    "broader hardware support",
)

MIGRATION_PATH: tuple[str, ...] = (
    "Aetherius-Linux matures userspace + Agent Bridge + Genesis + OE",
    "Aetherius Native Kernel prototype keeps higher-level interfaces",
    "progressively migrate services",
)

PASSPORT_COMPUTE_FIELDS: tuple[str, ...] = (
    "binary_compute", "ternary_compute", "quantum_compute",
    "hybrid_compute", "compute_backends",
)
