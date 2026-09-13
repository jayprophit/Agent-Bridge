"""Universal Environment & Provisioning Manager (v0.9.0).

Expands the Machine Maintenance system into a general capability that can
prepare, configure, repair, update and verify the computer and development
environment for Agent Bridge itself, the current project and future approved
projects — without bloating or destabilising the machine.

Pipeline:
  DISCOVER -> REQUIREMENT ANALYSIS -> COMPARE -> DIAGNOSE -> PLAN
  -> POLICY CHECK -> CONFIGURE/REPAIR/INSTALL -> VERIFY
  -> REGISTER CAPABILITY -> CONTINUE ORIGINAL TASK.

Rules (enforced, not advisory):
  - ADDITIVE ONLY: reuses MaintenancePolicy/managers/history and the Phase 1
    registries. No existing module is modified or duplicated.
  - Products (Windows, Docker, kubectl, Python, ...) are ADAPTERS behind
    generic capability contracts. Nothing is hardcoded around a product.
  - Smallest sufficient solution wins; duplicates are rejected.
  - Never report INSTALLED/CONFIGURED/REPAIRED/UPDATED/HEALTHY unverified.
  - Never delete user containers/images/volumes/networks/projects, never
    overwrite unrelated kubeconfig contexts, never destroy clusters, never
    flash firmware or replace drivers without explicit owner approval.
  - Nothing mutates on import. Mutations only via policy-gated execute().
"""
from __future__ import annotations

import shutil
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable

from machine_maintenance import (
    ActionKind,
    HealthState,
    InstallationManager,
    MaintenanceHistory,
    MaintenanceMode,
    MaintenancePolicy,
    MaintenanceSettings,
    PlanStep,
    PolicyDecision,
    RepairManager,
    UpdateManager,
)

__all__ = [
    "RequirementKind", "RequiredCapability", "UpdateDecision",
    "CapabilityAdapter", "Detection", "ProvisionGraph",
    "DockerManager", "KubernetesManager", "PackageManagerAdapters",
    "ConfigAmendment", "ConfigurationApplier", "AutoFix",
    "UpdateDecider", "FirmwareManager", "DriverManager",
    "WindowsFeatureManager", "ResourceAdvisor", "RemoteRouter",
    "AGENT_BRIDGE_REQUIREMENTS", "prepare_self_requirements",
    "build_provision_plan", "verify_provisioning",
]


# --------------------------------------------------------------------------
# Requirements
# --------------------------------------------------------------------------

class RequirementKind(str, Enum):
    TOOL = "TOOL"
    RUNTIME = "RUNTIME"
    SERVICE = "SERVICE"
    SDK = "SDK"
    EXTENSION = "EXTENSION"
    FEATURE = "FEATURE"


class UpdateDecision(str, Enum):
    KEEP = "KEEP"
    REPAIR = "REPAIR"
    UPDATE = "UPDATE"
    SIDE_BY_SIDE = "SIDE_BY_SIDE"
    DEFER = "DEFER"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"


@dataclass
class RequiredCapability:
    """One thing a project (or Agent Bridge itself) needs."""
    name: str = ""            # e.g. docker-compose, python, kubectl
    kind: RequirementKind = RequirementKind.TOOL
    min_version: str = ""
    constraints: dict[str, Any] = field(default_factory=dict)
    required_by: str = ""     # project/component name
    optional: bool = False


@dataclass
class Detection:
    capability: str = ""
    present: bool = False
    version: str = ""
    state: HealthState = HealthState.UNVERIFIED
    detail: str = ""
    executable: str = ""


# --------------------------------------------------------------------------
# Generic adapter contract (products plug in here, never hardcoded above)
# --------------------------------------------------------------------------

class CapabilityAdapter:
    """Contract every environment adapter implements."""
    capability: str = ""

    def detect(self) -> Detection:
        return Detection(capability=self.capability)

    def plan(self, req: RequiredCapability, det: Detection) -> list[PlanStep]:
        return []

    def verify(self) -> dict[str, Any]:
        return {"capability": self.capability, "ok": False,
                "note": "no verifier registered"}


class BinaryAdapter(CapabilityAdapter):
    """Adapter for a plain executable with a version probe."""

    def __init__(self, capability: str, binary: str,
                 probe_args: list[str] | None = None,
                 install_source: str = "winget",
                 install_package: str = ""):
        self.capability = capability
        self.binary = binary
        self.probe_args = probe_args or ["--version"]
        self.install_source = install_source
        self.install_package = install_package or binary

    def detect(self) -> Detection:
        exe = shutil.which(self.binary)
        if not exe:
            return Detection(capability=self.capability, present=False,
                             state=HealthState.MISSING)
        return Detection(capability=self.capability, present=True,
                         state=HealthState.UNVERIFIED, executable=exe)

    def plan(self, req: RequiredCapability, det: Detection) -> list[PlanStep]:
        if det.present:
            return []
        if req.optional:
            return []
        return [PlanStep(action=ActionKind.INSTALL, tool=self.capability,
                         reason=f"required by {req.required_by or 'project'}",
                         command=[], source=self.install_source,
                         verification=f"re-probe {self.capability}")]

    def verify(self) -> dict[str, Any]:
        det = self.detect()
        return {"capability": self.capability, "ok": det.present,
                "executable": det.executable}


ADAPTERS: dict[str, CapabilityAdapter] = {}


def register_adapter(adapter: CapabilityAdapter) -> CapabilityAdapter:
    ADAPTERS[adapter.capability] = adapter
    return adapter


def _default_adapters() -> dict[str, CapabilityAdapter]:
    if ADAPTERS:
        return ADAPTERS
    for cap, binary, args, src, pkg in [
        ("git", "git", ["--version"], "winget", "Git.Git"),
        ("git-lfs", "git-lfs", ["version"], "winget", "GitHub.GitLFS"),
        ("gh", "gh", ["--version"], "winget", "GitHub.cli"),
        ("python", "python", ["--version"], "winget", "Python.Python.3.13"),
        ("uv", "uv", ["--version"], "winget", "astral-sh.uv"),
        ("node", "node", ["--version"], "winget", "OpenJS.NodeJS.LTS"),
        ("cargo", "cargo", ["--version"], "winget", "Rustlang.Rustup"),
        ("cmake", "cmake", ["--version"], "winget", "Kitware.CMake"),
        ("ninja", "ninja", ["--version"], "winget", "Ninja-build.Ninja"),
        ("dotnet", "dotnet", ["--list-sdks"], "winget", "Microsoft.DotNet.SDK.10"),
        ("kubectl", "kubectl", ["version", "--client"], "winget",
         "Kubernetes.kubectl"),
        ("helm", "helm", ["version"], "winget", "Helm.Helm"),
    ]:
        register_adapter(BinaryAdapter(cap, binary, args, src, pkg))
    return ADAPTERS


# --------------------------------------------------------------------------
# Dependency graph (ordered layers; stop when a layer fails)
# --------------------------------------------------------------------------

@dataclass
class ProvisionNode:
    capability: str = ""
    depends_on: list[str] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)


class ProvisionGraph:
    """Ordered provisioning graph with stop-on-dependency-failure semantics."""

    def __init__(self):
        self.nodes: dict[str, ProvisionNode] = {}

    def add(self, node: ProvisionNode) -> None:
        self.nodes[node.capability] = node

    def ordered(self) -> list[ProvisionNode]:
        """Topological order (dependencies first); deterministic by name."""
        order: list[ProvisionNode] = []
        visited: dict[str, int] = {}

        def visit(name: str) -> None:
            mark = visited.get(name, 0)
            if mark == 2:
                return
            if mark == 1:
                raise ValueError(f"dependency cycle at {name!r}")
            visited[name] = 1
            node = self.nodes.get(name)
            if node is not None:
                for dep in sorted(node.depends_on):
                    if dep in self.nodes:
                        visit(dep)
                order.append(node)
            visited[name] = 2

        for name in sorted(self.nodes):
            visit(name)
        return order

    def execute(self, runner: Callable[[PlanStep], dict[str, Any]]) -> dict[str, Any]:
        """Run layer by layer; never install later layers if one fails."""
        done: list[str] = []
        failed: str = ""
        for node in self.ordered():
            for dep in node.depends_on:
                if dep in self.nodes and dep not in done:
                    return {"ok": False, "completed": done,
                            "failed": node.capability,
                            "error": f"dependency {dep} not satisfied"}
            for step in node.steps:
                res = runner(step)
                if not res.get("ok") and not res.get("dry_run"):
                    failed = node.capability
                    return {"ok": False, "completed": done,
                            "failed": failed, "error": res}
            done.append(node.capability)
        _ = failed
        return {"ok": True, "completed": done}


def build_provision_plan(requirements: list[RequiredCapability],
                         detections: dict[str, Detection],
                         dependencies: dict[str, list[str]] | None = None
                         ) -> ProvisionGraph:
    """Compare requirements against detections -> ordered dependency graph."""
    _default_adapters()
    dependencies = dependencies or {}
    graph = ProvisionGraph()
    for req in requirements:
        det = detections.get(req.name, Detection(capability=req.name))
        adapter = ADAPTERS.get(req.name, CapabilityAdapter())
        adapter.capability = req.name
        steps = adapter.plan(req, det)
        graph.add(ProvisionNode(capability=req.name,
                                depends_on=list(dependencies.get(req.name, [])),
                                steps=steps))
    return graph


# --------------------------------------------------------------------------
# Docker manager
# --------------------------------------------------------------------------

DISPOSABLE_PREFIX = "ab-"


class DockerManager:
    """Docker installation/version/health/config management (read-first)."""

    def __init__(self, runner: Callable[[list[str]], dict[str, Any]] | None = None):
        from machine_maintenance import _run as _default_run
        self._runner = runner or _default_run

    def detect(self) -> dict[str, Any]:
        cli = shutil.which("docker")
        compose = shutil.which("docker-compose") or shutil.which("docker")
        info: dict[str, Any] = {"cli_present": bool(cli), "cli_path": cli or "",
                                "compose_present": False, "daemon": False,
                                "contexts": [], "wsl_backend": False}
        if not cli:
            return info
        r = self._runner(["docker", "version", "--format",
                          "{{.Client.Version}}|{{.Server.Version}}"])
        if r.get("ok"):
            info["daemon"] = True
        r2 = self._runner(["docker", "compose", "version"])
        info["compose_present"] = bool(r2.get("ok"))
        r3 = self._runner(["docker", "context", "ls", "--format", "{{.Name}}"])
        if r3.get("ok"):
            info["contexts"] = (r3.get("stdout") or "").split()
        return info

    def health(self) -> dict[str, Any]:
        det = self.detect()
        checks = {
            "cli": det["cli_present"],
            "daemon": det["daemon"],
            "compose": det["compose_present"],
        }
        return {"ok": all(checks.values()), "checks": checks, "detail": det}

    def plan_repairs(self) -> list[PlanStep]:
        """Safe repairs only; never touches user resources."""
        h = self.health()
        steps = []
        if not h["checks"]["cli"]:
            steps.append(PlanStep(action=ActionKind.INSTALL, tool="docker",
                                  reason="Docker CLI missing",
                                  source="winget",
                                  verification="re-probe docker"))
        elif not h["checks"]["daemon"]:
            steps.append(PlanStep(action=ActionKind.SERVICE_RESTART,
                                  tool="docker-desktop",
                                  reason="daemon unreachable; start Docker Desktop",
                                  source="none",
                                  verification="docker version shows server"))
        if h["checks"]["cli"] and not h["checks"]["compose"]:
            steps.append(PlanStep(action=ActionKind.REPAIR, tool="docker-compose",
                                  reason="Compose plugin missing",
                                  source="winget",
                                  verification="docker compose version"))
        return steps

    def verify_container(self, image: str = "hello-world") -> dict[str, Any]:
        """Disposable container test; image removed afterwards."""
        r = self._runner(["docker", "run", "--rm", image])
        if not r.get("ok"):
            return {"ok": False, "stage": "run", "result": r}
        c = self._runner(["docker", "image", "rm", image])
        return {"ok": True, "run": r, "cleanup": c}

    @staticmethod
    def is_disposable(name: str) -> bool:
        return name.startswith(DISPOSABLE_PREFIX)


# --------------------------------------------------------------------------
# Kubernetes manager (OPTIONAL capability)
# --------------------------------------------------------------------------

class KubernetesManager:
    """Optional Kubernetes support with lightest-solution selection."""

    PROVIDERS = ("compose", "kind", "k3d", "minikube", "existing")

    def __init__(self, runner: Callable[[list[str]], dict[str, Any]] | None = None):
        from machine_maintenance import _run as _default_run
        self._runner = runner or _default_run

    def detect(self) -> dict[str, Any]:
        det: dict[str, Any] = {
            "kubectl": bool(shutil.which("kubectl")),
            "helm": bool(shutil.which("helm")),
            "kubeconfig": bool((Path.home() / ".kube" / "config").exists()),
            "contexts": [], "current_context": "",
            "api_reachable": False, "nodes": [],
            "providers": {"kind": bool(shutil.which("kind")),
                          "k3d": bool(shutil.which("k3d")),
                          "minikube": bool(shutil.which("minikube")),
                          "compose": bool(shutil.which("docker"))},
        }
        if det["kubectl"]:
            r = self._runner(["kubectl", "config", "get-contexts", "-o=name"])
            if r.get("ok"):
                det["contexts"] = (r.get("stdout") or "").split()
            r2 = self._runner(["kubectl", "config", "current-context"])
            if r2.get("ok"):
                det["current_context"] = (r2.get("stdout") or "").strip()
            r3 = self._runner(["kubectl", "version", "--request-timeout=10s"])
            det["api_reachable"] = bool(r3.get("ok"))
        return det

    def select_lightest(self, requires_k8s_apis: bool,
                        resources: dict[str, Any] | None = None) -> str:
        """compose < kind/k3d/minikube < existing/full; never heavies by default."""
        if not requires_k8s_apis:
            return "compose"
        resources = resources or {}
        low_ram = (resources.get("ram_gb") or 99) < 8
        providers = self.detect()["providers"]
        for candidate in ("kind", "k3d", "minikube"):
            if providers.get(candidate):
                return candidate
        if low_ram:
            return "compose"
        return "kind"

    def plan(self, requires_k8s_apis: bool) -> list[PlanStep]:
        det = self.detect()
        steps = []
        if not det["kubectl"]:
            steps.append(PlanStep(action=ActionKind.INSTALL, tool="kubectl",
                                  reason="kubectl missing for k8s workflows",
                                  source="winget",
                                  verification="kubectl version --client"))
        choice = self.select_lightest(requires_k8s_apis)
        if choice != "compose" and not det["providers"].get(choice, False):
            steps.append(PlanStep(action=ActionKind.INSTALL, tool=choice,
                                  reason=f"lightest local provider ({choice})",
                                  source="winget",
                                  verification=f"re-probe {choice}"))
        return steps

    def verify_test_workload(self, namespace: str = "ab-verify") -> dict[str, Any]:
        """Disposable namespace workload; namespace deleted afterwards."""
        seq = [
            ["kubectl", "create", "namespace", namespace],
            ["kubectl", "run", "ab-probe", "--image=hello-world",
             "-n", namespace],
            ["kubectl", "wait", "--for=condition=ready", "pod/ab-probe",
             "-n", namespace, "--timeout=120s"],
        ]
        results = [self._runner(cmd) for cmd in seq]
        cleanup = self._runner(["kubectl", "delete", "namespace", namespace])
        ok = all(r.get("ok") for r in results)
        return {"ok": ok, "stages": results, "cleanup": cleanup}


# --------------------------------------------------------------------------
# Package / extension adapters (preflight before install)
# --------------------------------------------------------------------------

class PackageManagerAdapters:
    """Preflight-checked install planning across ecosystems."""

    ECOSYSTEMS = ("winget", "apt", "pip", "uv", "npm", "pnpm", "yarn",
                  "cargo", "rustup", "dotnet", "maven", "gradle", "go")

    @staticmethod
    def preflight(package: str, ecosystem: str, disk_mb_needed: int = 0,
                  is_present: bool = False, equivalent: str = "") -> dict[str, Any]:
        if ecosystem not in PackageManagerAdapters.ECOSYSTEMS:
            return {"ok": False, "error": f"unsupported ecosystem: {ecosystem}"}
        if is_present:
            return {"ok": False, "decision": "KEEP",
                    "reason": f"{package} already installed"}
        if equivalent:
            return {"ok": False, "decision": "KEEP",
                    "reason": f"equivalent installed: {equivalent}"}
        if disk_mb_needed:
            try:
                free_mb = shutil.disk_usage("C:\\" if os_is_windows() else "/").free // (1024 * 1024)
            except OSError:
                free_mb = 0
            if free_mb < disk_mb_needed:
                return {"ok": False, "decision": "DEFER",
                        "reason": f"disk shortfall: {free_mb}MB < {disk_mb_needed}MB"}
        return {"ok": True, "decision": "INSTALL"}


def os_is_windows() -> bool:
    import platform
    return platform.system() == "Windows"


# --------------------------------------------------------------------------
# Configuration management (backup before amend)
# --------------------------------------------------------------------------

@dataclass
class ConfigAmendment:
    target: str = ""       # e.g. PATH, env name, file path
    operation: str = ""    # APPEND_PATH | SET_ENV | WRITE_FILE
    value: str = ""
    backup: str = ""       # previous value captured at apply time


class ConfigurationApplier:
    """PATH/env/file amendments with backup; dry-run default."""

    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def apply(self, amendment: ConfigAmendment,
              dry_run: bool = True) -> dict[str, Any]:
        step = PlanStep(action=ActionKind.CONFIGURE, tool=amendment.target,
                        reason=f"{amendment.operation} {amendment.target}",
                        source="none",
                        verification=f"read back {amendment.target}")
        if self.policy.decide(step) != PolicyDecision.ALLOW or dry_run:
            return {"ok": False, "dry_run": True,
                    "decision": self.policy.decide(step).value}
        if amendment.operation == "APPEND_PATH":
            import winreg
            if not os_is_windows():
                return {"ok": False, "error": "PATH amend only on Windows"}
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment",
                                 0, winreg.KEY_READ | winreg.KEY_WRITE)
            current, _ = winreg.QueryValueEx(key, "Path")
            amendment.backup = current
            if amendment.value not in current:
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ,
                                  current + ";" + amendment.value)
            return {"ok": True, "backup": amendment.backup}
        return {"ok": False, "error": f"unsupported operation: {amendment.operation}"}


# --------------------------------------------------------------------------
# Auto-fix (build failure -> root cause -> allowed repair)
# --------------------------------------------------------------------------

AUTOFIX_RULES: tuple[tuple[str, str, str], ...] = (
    ("cmake", "not recognized", "install cmake"),
    ("docker", "cannot find the file", "start Docker Desktop"),
    ("kubectl", "not recognized", "install kubectl"),
    ("node", "not recognized", "install node LTS"),
    ("python", "No module named", "pip install missing module"),
    ("cargo", "no override and no default toolchain", "rustup default stable"),
    ("compiler", "iostream", "use MinGW target or install MSVC STL"),
    ("PATH", "not recognized", "repair PATH entry"),
    ("service", "connection refused", "restart development service"),
    ("SDK", "not found", "install required SDK"),
)


class AutoFix:
    """Maps failure signatures to diagnosis + policy-gated repair steps."""

    @staticmethod
    def diagnose(tool: str, output: str) -> dict[str, Any]:
        lowered = (output or "").lower()
        for area, signature, repair in AUTOFIX_RULES:
            if signature.lower() in lowered and (
                    area.lower() in tool.lower() or area in ("PATH", "service")):
                return {"tool": tool, "root_cause": signature,
                        "repair": repair}
        return {"tool": tool, "root_cause": "unknown",
                "repair": "manual diagnosis required"}

    @staticmethod
    def plan_for(tool: str, output: str) -> list[PlanStep]:
        diag = AutoFix.diagnose(tool, output)
        if diag["root_cause"] == "unknown":
            return []
        return [PlanStep(action=ActionKind.REPAIR, tool=tool,
                         reason=f"{diag['root_cause']} -> {diag['repair']}",
                         source="none", verification=f"retry {tool}")]


# --------------------------------------------------------------------------
# Update decider / firmware / drivers / Windows features
# --------------------------------------------------------------------------

class UpdateDecider:
    """KEEP | REPAIR | UPDATE | SIDE_BY_SIDE | DEFER | REQUIRES_APPROVAL."""

    @staticmethod
    def decide(current: str, latest: str, security: bool = False,
               required_feature: bool = False, breaks_others: bool = False,
               side_by_side_possible: bool = False) -> UpdateDecision:
        if breaks_others and side_by_side_possible:
            return UpdateDecision.SIDE_BY_SIDE
        if breaks_others:
            return UpdateDecision.REQUIRES_APPROVAL
        if not latest or current == latest:
            return UpdateDecision.KEEP
        if security or required_feature:
            return UpdateDecision.UPDATE
        return UpdateDecision.DEFER


class FirmwareManager:
    """Detect + plan only. Execution ALWAYS requires explicit approval."""

    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def check(self, device: str, current: str, available: str) -> dict[str, Any]:
        step = PlanStep(action=ActionKind.UPDATE, tool=f"firmware:{device}",
                        reason=f"{current} -> {available}",
                        risk_class="firmware", source="official",
                        verification="read back firmware version")
        return {"device": device, "current": current, "available": available,
                "decision": self.policy.decide(step).value,
                "note": "flashing requires explicit owner approval"}


class DriverManager(FirmwareManager):
    """Same gate as firmware: detect/prepare freely, replace on approval."""

    def check(self, device: str, current: str, available: str) -> dict[str, Any]:
        step = PlanStep(action=ActionKind.UPDATE, tool=f"driver:{device}",
                        reason=f"{current} -> {available}",
                        risk_class="driver", source="official",
                        verification="read back driver version")
        return {"device": device, "current": current, "available": available,
                "decision": self.policy.decide(step).value,
                "note": "driver replacement requires explicit owner approval"}


class WindowsFeatureManager:
    """Detect Windows feature requirements; enabling is approval-gated."""

    def __init__(self, policy: MaintenancePolicy | None = None):
        self.policy = policy or MaintenancePolicy()

    def require(self, feature: str, reason: str) -> dict[str, Any]:
        step = PlanStep(action=ActionKind.CONFIGURE, tool=f"windows-feature:{feature}",
                        reason=reason, risk_class="os_upgrade", source="official",
                        admin_required=True,
                        verification=f"query {feature} state")
        return {"feature": feature,
                "decision": self.policy.decide(step).value}


# --------------------------------------------------------------------------
# Resource-aware routing (local vs remote, compose vs k8s)
# --------------------------------------------------------------------------

class ResourceAdvisor:
    """MAXIMUM USEFUL CAPABILITY with MINIMUM bloat/services/duplication."""

    @staticmethod
    def advise(resources: dict[str, Any], needs_k8s_apis: bool = False,
               heavy_local_ok: bool = False) -> dict[str, Any]:
        ram_gb = resources.get("ram_gb", 16)
        free_disk_gb = resources.get("free_disk_gb", 100)
        if free_disk_gb < 10:
            return {"place": "remote", "reason": "local disk below 10GB free"}
        if needs_k8s_apis and (ram_gb < 8 and not heavy_local_ok):
            return {"place": "compose-or-remote",
                    "reason": "k8s APIs needed but RAM constrained"}
        if needs_k8s_apis:
            return {"place": "local-k8s-light",
                    "reason": "lightest local provider preferred"}
        return {"place": "local", "reason": "local machine sufficient"}


class RemoteRouter:
    """Recommend WSL/Docker/remote/cloud when local is inefficient."""

    OPTIONS = ("local", "wsl", "docker", "codespace", "remote-machine",
               "cloud-build", "remote-k8s")

    @staticmethod
    def route(requirement: str, local_ok: bool,
              environments: list[str] | None = None) -> dict[str, Any]:
        environments = environments or ["local"]
        if local_ok:
            return {"requirement": requirement, "route": "local",
                    "reason": "local machine satisfies it"}
        for candidate in ("wsl", "docker", "codespace", "remote-machine",
                          "cloud-build", "remote-k8s"):
            if candidate in environments:
                return {"requirement": requirement, "route": candidate,
                        "reason": "local insufficient; registered alternative"}
        return {"requirement": requirement, "route": "local",
                "reason": "no alternative registered; install locally or register one"}


# --------------------------------------------------------------------------
# Self-requirements (same policy, no special privileges)
# --------------------------------------------------------------------------

AGENT_BRIDGE_REQUIREMENTS: tuple[RequiredCapability, ...] = (
    RequiredCapability(name="git", kind=RequirementKind.TOOL,
                       required_by="agent-bridge"),
    RequiredCapability(name="python", kind=RequirementKind.RUNTIME,
                       min_version="3.10", required_by="agent-bridge"),
    RequiredCapability(name="gh", kind=RequirementKind.TOOL,
                       required_by="agent-bridge-release"),
    RequiredCapability(name="docker", kind=RequirementKind.SERVICE,
                       required_by="agent-bridge-containers", optional=True),
    RequiredCapability(name="cmake", kind=RequirementKind.TOOL,
                       required_by="agent-bridge-native", optional=True),
)


def prepare_self_requirements(settings: MaintenanceSettings | None = None,
                              detections: dict[str, Detection] | None = None
                              ) -> dict[str, Any]:
    """Agent Bridge's own dependencies through the SAME policy (no privilege)."""
    policy = MaintenancePolicy(settings or MaintenanceSettings())
    graph = build_provision_plan(list(AGENT_BRIDGE_REQUIREMENTS), detections or {})
    steps = [s for node in graph.ordered() for s in node.steps]
    gated = [(s, policy.decide(s)) for s in steps]
    return {"steps": [asdict(s) for s, _ in gated],
            "decisions": [d.value for _, d in gated],
            "privileged_bypass": False}


# --------------------------------------------------------------------------
# Verification gates (never report unverified)
# --------------------------------------------------------------------------

def verify_provisioning(checks: dict[str, Callable[[], dict[str, Any]]]
                        ) -> dict[str, Any]:
    results = {}
    for name, fn in checks.items():
        try:
            r = fn()
            results[name] = {"ok": bool(r.get("ok")), "detail": r}
        except Exception as e:  # noqa: BLE001 - verification must not raise
            results[name] = {"ok": False, "detail": str(e)[:200]}
    return {"ok": all(v["ok"] for v in results.values()), "checks": results}


# --------------------------------------------------------------------------
# End-to-end entry point (policy-gated, dry-run default)
# --------------------------------------------------------------------------

def provision_for_project(workspace: str,
                          settings: MaintenanceSettings | None = None,
                          dry_run: bool = True) -> dict[str, Any]:
    """PROJECT_READY flow: requirements -> compare -> plan -> (gated) execute."""
    from project_detector import inspect_project
    from project_model import build_project_model

    settings = settings or MaintenanceSettings(mode=settings.mode
                                               if settings else MaintenanceMode.PROJECT_READY)
    _default_adapters()
    profile = inspect_project(workspace)
    model = build_project_model(profile)
    requirements: list[RequiredCapability] = []
    for comp in model.components:
        for lang in comp.languages:
            requirements.append(RequiredCapability(
                name=lang, kind=RequirementKind.RUNTIME,
                required_by=f"{comp.role}:{comp.name}"))
    if model.has_containers:
        requirements.append(RequiredCapability(name="docker-compose",
                                               kind=RequirementKind.SERVICE,
                                               required_by="containers"))
    detections = {name: adapter.detect()
                  for name, adapter in ADAPTERS.items()}
    graph = build_provision_plan(requirements, detections)
    policy = MaintenancePolicy(settings)
    history = MaintenanceHistory()
    installer = InstallationManager(policy, history)
    ordered_steps = [s for node in graph.ordered() for s in node.steps]
    executed = [installer.execute(s, dry_run=dry_run) for s in ordered_steps]
    _ = time.time()
    return {"workspace": workspace, "dry_run": dry_run,
            "requirements": [asdict(r) for r in requirements],
            "steps": len(ordered_steps), "executed": executed}
