"""Execution-Target Registry (P0 gap-closure: §63, §9).

Extends compute/providers.ComputeRecord to the full abstract execution-target
model from the Hybrid Cloud specification. Local PCs, WSL, Docker, cloud VMs
and serverless workers use the SAME abstract execution-target model.

Ownership: compute/execution_target_registry.py (extends canonically owned
compute/providers.py — does NOT duplicate ComputeRegistry).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# -- Target types ------------------------------------------------------------
# Each execution target is one of these abstract types, regardless of whether
# it is local or cloud.
TARGET_TYPE_LOCAL_PC = "local_pc"
TARGET_TYPE_WSL = "wsl"
TARGET_TYPE_DOCKER = "docker"
TARGET_TYPE_VM = "vm"
TARGET_TYPE_SSH = "ssh"
TARGET_TYPE_VPS = "vps"
TARGET_TYPE_LOCAL_OLLAMA = "local_ollama"
TARGET_TYPE_API_PROVIDER = "api_provider"
TARGET_TYPE_SERVERLESS = "serverless"
TARGET_TYPE_GPU_CLOUD = "gpu_cloud"
TARGET_TYPE_CPU_CLOUD = "cpu_cloud"

TARGET_TYPES = (
    TARGET_TYPE_LOCAL_PC,
    TARGET_TYPE_WSL,
    TARGET_TYPE_DOCKER,
    TARGET_TYPE_VM,
    TARGET_TYPE_SSH,
    TARGET_TYPE_VPS,
    TARGET_TYPE_LOCAL_OLLAMA,
    TARGET_TYPE_API_PROVIDER,
    TARGET_TYPE_SERVERLESS,
    TARGET_TYPE_GPU_CLOUD,
    TARGET_TYPE_CPU_CLOUD,
)

# -- Privacy / trust boundaries -----------------------------------------------
PRIVACY_LOCAL_ONLY = "LOCAL_ONLY"
PRIVACY_PROJECT = "PROJECT"
PRIVACY_PERSONAL = "PERSONAL"
PRIVACY_PUBLIC = "PUBLIC"

PRIVACY_CLASSES = (
    PRIVACY_LOCAL_ONLY,
    PRIVACY_PROJECT,
    PRIVACY_PERSONAL,
    PRIVACY_PUBLIC,
)

TRUST_LOCAL = "local"
TRUST_OWNER_CONTROLLED = "owner_controlled"
TRUST_THIRD_PARTY = "third_party"

TRUST_CLASSES = (TRUST_LOCAL, TRUST_OWNER_CONTROLLED, TRUST_THIRD_PARTY)

# -- Target states -----------------------------------------------------------
STATE_VERIFIED = "verified"
STATE_CONFIGURED = "configured"
STATE_PROVISIONING = "provisioning"
STATE_OFFLINE = "offline"
STATE_DRAINING = "draining"
STATE_DEGRADED = "degraded"

TARGET_STATES = (
    STATE_VERIFIED,
    STATE_CONFIGURED,
    STATE_PROVISIONING,
    STATE_OFFLINE,
    STATE_DRAINING,
    STATE_DEGRADED,
)

# -- Accelerator fields (§93) -------------------------------------------------
@dataclass
class AcceleratorSpec:
    vendor: str = ""           # "nvidia", "amd", "intel", "apple"
    model: str = ""            # "rtx-4090", "a100", "h100", "m2-max", "cpu-only"
    count: int = 0
    total_vram_gb: float = 0.0
    free_vram_gb: float = 0.0
    compute_capability: str = ""  # e.g. "sm_89", "avx2", "neon"
    fp16: bool = False
    bf16: bool = False
    fp8: bool = False
    int8: bool = False
    int4: bool = False
    binary_support: bool = False
    ternary_support: bool = False


@dataclass
class ExecutionTargetRecord:
    """A single execution target. Local and cloud use the same shape.

    Mirrors the abstract model in spec §63:
      execution_target:
        id, provider, type, owner, state,
        architecture, cpu, ram, gpu, vram, storage,
        region, network, startup_latency, cost, free_quota, quota_remaining,
        privacy, trust_boundary, supported_models, supported_capabilities,
        benchmark_ids, health, last_verified, fallback_targets
    """
    target_id: str = ""
    provider: str = "local"           # provider name or "local"
    type: str = TARGET_TYPE_LOCAL_PC
    owner: str = "Jonathan"
    state: str = STATE_CONFIGURED
    architecture: str = ""            # x86_64, aarch64, etc.
    cpu_cores: int = 0
    ram_gb: float = 0.0
    accelerators: list[AcceleratorSpec] = field(default_factory=list)
    storage_gb: float = 0.0
    region: str = "local"             # "local", "uk-lon-1", "us-east-1", etc.
    network: str = "localhost"        # network description / endpoint
    startup_latency_s: float = 0.0    # cold-start seconds
    cost_class: str = "FREE"          # FREE | HOBBY | PAID | UNKNOWN
    free_quota: dict[str, Any] = field(default_factory=dict)  # {"tokens": N, "gpu_seconds": N}
    quota_remaining: dict[str, Any] = field(default_factory=dict)
    privacy: str = PRIVACY_LOCAL_ONLY
    trust_boundary: str = TRUST_LOCAL
    supported_models: list[str] = field(default_factory=list)
    supported_capabilities: list[str] = field(default_factory=list)
    benchmark_ids: list[str] = field(default_factory=list)
    health: str = "UNKNOWN"           # HEALTHY | DEGRADED | UNAVAILABLE | UNKNOWN
    last_verified: float = 0.0        # epoch timestamp
    fallback_targets: list[str] = field(default_factory=list)  # other target_ids
    endpoint: str = ""                # API endpoint or connection string
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in TARGET_TYPES:
            raise ValueError(f"unknown target type: {self.type!r}")
        if self.privacy not in PRIVACY_CLASSES:
            raise ValueError(f"unknown privacy class: {self.privacy!r}")
        if self.trust_boundary not in TRUST_CLASSES:
            raise ValueError(f"unknown trust boundary: {self.trust_boundary!r}")

    def total_vram_gb(self) -> float:
        return sum(a.total_vram_gb for a in self.accelerators)

    def free_vram_gb(self) -> float:
        return sum(a.free_vram_gb for a in self.accelerators)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "provider": self.provider,
            "type": self.type,
            "owner": self.owner,
            "state": self.state,
            "architecture": self.architecture,
            "cpu_cores": self.cpu_cores,
            "ram_gb": self.ram_gb,
            "accelerators": [a.__dict__ for a in self.accelerators],
            "storage_gb": self.storage_gb,
            "region": self.region,
            "network": self.network,
            "startup_latency_s": self.startup_latency_s,
            "cost_class": self.cost_class,
            "free_quota": self.free_quota,
            "quota_remaining": self.quota_remaining,
            "privacy": self.privacy,
            "trust_boundary": self.trust_boundary,
            "supported_models": self.supported_models,
            "supported_capabilities": self.supported_capabilities,
            "benchmark_ids": self.benchmark_ids,
            "health": self.health,
            "last_verified": self.last_verified,
            "fallback_targets": self.fallback_targets,
            "endpoint": self.endpoint,
            "metadata": self.metadata,
        }


class ExecutionTargetRegistry:
    """ID-keyed registry of abstract execution targets.

    Local PCs, WSL, Docker, cloud VMs and serverless workers all register
    here. The registry is the single source of truth for where work can run.
    """

    def __init__(self) -> None:
        self._targets: dict[str, ExecutionTargetRecord] = {}

    def register(self, record: ExecutionTargetRecord) -> None:
        if not record.target_id:
            raise ValueError("target_id must be non-empty")
        if record.target_id in self._targets:
            raise ValueError(f"duplicate target_id: {record.target_id!r}")
        record.last_verified = record.last_verified or time.time()
        self._targets[record.target_id] = record

    def get(self, target_id: str) -> ExecutionTargetRecord:
        try:
            return self._targets[target_id]
        except KeyError:
            raise KeyError(f"unknown execution target: {target_id!r}")

    def ids(self) -> list[str]:
        return sorted(self._targets)

    def __len__(self) -> int:
        return len(self._targets)

    def list(self, provider: str = "", type_filter: str = "",
             privacy: str = "", state: str = "",
             local_only: bool = False) -> list[ExecutionTargetRecord]:
        out = []
        for rec in self._targets.values():
            if provider and rec.provider != provider:
                continue
            if type_filter and rec.type != type_filter:
                continue
            if privacy and rec.privacy != privacy:
                continue
            if state and rec.state != state:
                continue
            if local_only and rec.privacy != PRIVACY_LOCAL_ONLY:
                continue
            out.append(rec)
        return sorted(out, key=lambda r: r.target_id)

    def local_targets(self) -> list[ExecutionTargetRecord]:
        return [r for r in self._targets.values()
                if r.trust_boundary == TRUST_LOCAL]

    def remote_targets(self) -> list[ExecutionTargetRecord]:
        return [r for r in self._targets.values()
                if r.trust_boundary != TRUST_LOCAL]

    def available(self) -> list[ExecutionTargetRecord]:
        return [r for r in self._targets.values()
                if r.health in ("HEALTHY", "DEGRADED")]

    def by_capability(self, capability: str) -> list[ExecutionTargetRecord]:
        return sorted(
            (r for r in self._targets.values()
             if capability in r.supported_capabilities and r.health in ("HEALTHY", "DEGRADED")),
            key=lambda r: r.target_id,
        )

    def supports_model(self, model_id: str) -> list[ExecutionTargetRecord]:
        return sorted(
            (r for r in self._targets.values()
             if model_id in r.supported_models),
            key=lambda r: r.target_id,
        )

    def by_provider(self, provider: str) -> list[ExecutionTargetRecord]:
        return sorted(
            (r for r in self._targets.values() if r.provider == provider),
            key=lambda r: r.target_id,
        )

    def update_health(self, target_id: str, health: str) -> ExecutionTargetRecord:
        rec = self.get(target_id)
        rec.health = health
        rec.last_verified = time.time()
        return rec

    def to_dict(self) -> dict[str, Any]:
        return {tid: r.to_dict() for tid, r in self._targets.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionTargetRegistry":
        reg = cls()
        for tid, rdict in data.items():
            reg.register(ExecutionTargetRecord(**{
                k: v for k, v in rdict.items()
                if k in ExecutionTargetRecord.__dataclass_fields__
            }))
        return reg


def seed_local_targets() -> ExecutionTargetRegistry:
    """Register the verified local execution targets for this workstation.

    Hardware: Intel i7-870, 16GB RAM, NVIDIA GTX 1050 Ti, Windows 10.
    """
    reg = ExecutionTargetRegistry()
    gpu = AcceleratorSpec(
        vendor="nvidia",
        model="gtx-1050-ti",
        count=1,
        total_vram_gb=4.0,
        free_vram_gb=4.0,
        compute_capability="sm_61",
        fp16=True,
        bf16=False,
        fp8=False,
        int8=True,
        int4=True,
    )
    local_pc = ExecutionTargetRecord(
        target_id="EXEC-LOCAL-WIN-001",
        provider="local",
        type=TARGET_TYPE_LOCAL_PC,
        owner="Jonathan",
        state=STATE_VERIFIED,
        architecture="x86_64",
        cpu_cores=8,
        ram_gb=16.0,
        accelerators=[gpu],
        storage_gb=500.0,
        region="local",
        network="localhost",
        startup_latency_s=0.0,
        cost_class="FREE",
        privacy=PRIVACY_LOCAL_ONLY,
        trust_boundary=TRUST_LOCAL,
        supported_models=[
            "qwen3:0.6b", "qwen3:1.7b", "qwen3:latest",
            "qwen2.5-coder:3b-instruct-q4_K_M",
            "qwen2.5-coder:1.5b-instruct-q4_K_M",
            "qwen3.5:2b-q4_K_M",
            "granite3.3:2b", "granite4:3b",
            "phi4-mini:latest", "moondream:latest",
            "nomic-embed-text:latest",
            "deepseek-coder:1.3b-instruct-q4_K_M",
            "llama3.2:1b-instruct-q4_K_M",
        ],
        supported_capabilities=[
            "coding", "review", "reasoning", "vision", "embedding",
            "tool_calling", "structured_output", "streaming",
        ],
        health="HEALTHY",
        last_verified=time.time(),
        fallback_targets=[],
        endpoint="http://127.0.0.1:11434",
    )
    reg.register(local_pc)

    wsl = ExecutionTargetRecord(
        target_id="EXEC-LOCAL-WSL-001",
        provider="local",
        type=TARGET_TYPE_WSL,
        owner="Jonathan",
        state=STATE_VERIFIED,
        architecture="x86_64",
        cpu_cores=8,
        ram_gb=12.0,
        accelerators=[],  # WSL shares GPU via /dev/dxg
        storage_gb=200.0,
        region="local",
        network="localhost",
        startup_latency_s=2.0,
        cost_class="FREE",
        privacy=PRIVACY_LOCAL_ONLY,
        trust_boundary=TRUST_LOCAL,
        supported_models=[
            "qwen3:0.6b", "qwen3:1.7b", "qwen2.5-coder:3b-instruct-q4_K_M",
        ],
        supported_capabilities=["coding", "review", "reasoning"],
        health="HEALTHY",
        last_verified=time.time(),
        fallback_targets=["EXEC-LOCAL-WIN-001"],
        endpoint="wsl://Ubuntu-22.04",
    )
    reg.register(wsl)

    docker_pc = ExecutionTargetRecord(
        target_id="EXEC-LOCAL-DOCKER-001",
        provider="local",
        type=TARGET_TYPE_DOCKER,
        owner="Jonathan",
        state=STATE_VERIFIED,
        architecture="x86_64",
        cpu_cores=8,
        ram_gb=8.0,  # container limit
        accelerators=[],
        storage_gb=100.0,
        region="local",
        network="localhost",
        startup_latency_s=3.0,  # image pull + container start
        cost_class="FREE",
        privacy=PRIVACY_LOCAL_ONLY,
        trust_boundary=TRUST_LOCAL,
        supported_models=["qwen3:0.6b", "qwen3:1.7b"],
        supported_capabilities=["coding", "review"],
        health="HEALTHY",
        last_verified=time.time(),
        fallback_targets=["EXEC-LOCAL-WIN-001"],
        endpoint="docker://local",
    )
    reg.register(docker_pc)

    return reg


# -- Convenience alias ---------------------------------------------------------
ExecutionTarget = ExecutionTargetRecord


__all__ = [
    "ExecutionTargetRecord",
    "ExecutionTarget",
    "ExecutionTargetRegistry",
    "AcceleratorSpec",
    "seed_local_targets",
    "TARGET_TYPE_LOCAL_PC",
    "TARGET_TYPE_WSL",
    "TARGET_TYPE_DOCKER",
    "TARGET_TYPE_VM",
    "TARGET_TYPE_SSH",
    "TARGET_TYPE_VPS",
    "TARGET_TYPE_LOCAL_OLLAMA",
    "TARGET_TYPE_API_PROVIDER",
    "TARGET_TYPE_SERVERLESS",
    "TARGET_TYPE_GPU_CLOUD",
    "TARGET_TYPE_CPU_CLOUD",
    "TARGET_TYPES",
    "PRIVACY_LOCAL_ONLY",
    "PRIVACY_PROJECT",
    "PRIVACY_PERSONAL",
    "PRIVACY_PUBLIC",
    "PRIVACY_CLASSES",
    "TRUST_LOCAL",
    "TRUST_OWNER_CONTROLLED",
    "TRUST_THIRD_PARTY",
    "TRUST_CLASSES",
    "STATE_VERIFIED",
    "STATE_CONFIGURED",
    "STATE_OFFLINE",
    "STATE_DEGRADED",
    "STATE_PROVISIONING",
    "STATE_DRAINING",
    "TARGET_STATES",
]
