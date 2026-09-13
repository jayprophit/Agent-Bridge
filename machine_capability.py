"""Machine Capability Registry (v0.9.0 Phase 1).

Structured discovery of host machine capabilities.
Read-only probing only — no mutations, no package installs.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from localdirs import local_root


@dataclass
class CPUInfo:
    architecture: str = ""
    vendor: str = ""
    model: str = ""
    physical_cores: int = 0
    logical_processors: int = 0
    features: list[str] = field(default_factory=list)
    frequency_mhz: float = 0.0


@dataclass
class MemoryInfo:
    total_mb: int = 0
    available_mb: int = 0
    swap_total_mb: int = 0
    swap_available_mb: int = 0


@dataclass
class GPUInfo:
    vendor: str = ""
    model: str = ""
    vram_mb: int = 0
    driver_version: str = ""
    apis: list[str] = field(default_factory=list)
    compute_capability: str = ""


@dataclass
class StorageInfo:
    device: str = ""
    mount_point: str = ""
    total_gb: float = 0.0
    free_gb: float = 0.0
    filesystem: str = ""
    is_removable: bool = False


@dataclass
class VirtualizationInfo:
    enabled: bool = False
    hypervisor: str = ""
    wsl_version: str = ""
    wsl_distros: list[dict[str, Any]] = field(default_factory=list)
    docker_available: bool = False
    podman_available: bool = False


@dataclass
class ShellInfo:
    name: str = ""
    executable: str = ""
    version: str = ""
    is_default: bool = False


@dataclass
class ToolInfo:
    name: str = ""
    executable: str = ""
    version: str = ""
    category: str = ""
    languages: list[str] = field(default_factory=list)
    working: bool = False
    probe_command: str = ""
    probe_output: str = ""
    source: str = ""
    requires_admin: bool = False


@dataclass
class RuntimeInfo:
    name: str = ""
    executable: str = ""
    version: str = ""
    endpoint: str = ""
    protocol: str = ""
    models: list[dict[str, Any]] = field(default_factory=list)
    status: str = "UNKNOWN"


@dataclass
class OSInfo:
    platform: str = ""
    release: str = ""
    version: str = ""
    build: str = ""
    architecture: str = ""


@dataclass
class MachineCapability:
    """Complete machine capability snapshot."""
    timestamp: float = field(default_factory=time.time)
    os: OSInfo = field(default_factory=OSInfo)
    cpu: CPUInfo = field(default_factory=CPUInfo)
    memory: MemoryInfo = field(default_factory=MemoryInfo)
    gpus: list[GPUInfo] = field(default_factory=list)
    storage: list[StorageInfo] = field(default_factory=list)
    virtualization: VirtualizationInfo = field(default_factory=VirtualizationInfo)
    shells: list[ShellInfo] = field(default_factory=list)
    tools: list[ToolInfo] = field(default_factory=list)
    runtimes: list[RuntimeInfo] = field(default_factory=list)
    environment_variables: dict[str, str] = field(default_factory=dict)


class MachineCapabilityRegistry:
    """Registry for discovering and caching machine capabilities."""

    def __init__(self, cache_ttl_seconds: float = 3600.0):
        self._cache: MachineCapability | None = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl = cache_ttl_seconds
        self._tool_probes: dict[str, tuple[str, list[str]]] = self._default_tool_probes()

    def _default_tool_probes(self) -> dict[str, tuple[str, list[str]]]:
        """Default tool probes: (category, [probe_command])"""
        return {
            # C/C++
            "clang": ("compiler", ["clang", "--version"]),
            "clang++": ("compiler", ["clang++", "--version"]),
            "gcc": ("compiler", ["gcc", "--version"]),
            "g++": ("compiler", ["g++", "--version"]),
            "cl.exe": ("compiler", ["cl.exe", "/?"]),
            "lld": ("linker", ["lld", "--version"]),
            "lldb": ("debugger", ["lldb", "--version"]),
            "gdb": ("debugger", ["gdb", "--version"]),
            # Build systems
            "cmake": ("build_system", ["cmake", "--version"]),
            "ninja": ("build_system", ["ninja", "--version"]),
            "make": ("build_system", ["make", "--version"]),
            "meson": ("build_system", ["meson", "--version"]),
            "msbuild": ("build_system", ["msbuild", "/version"]),
            # Python
            "python": ("interpreter", ["python", "--version"]),
            "py": ("interpreter", ["py", "--version"]),
            "pip": ("package_manager", ["pip", "--version"]),
            "uv": ("package_manager", ["uv", "--version"]),
            "conda": ("package_manager", ["conda", "--version"]),
            # JavaScript/TypeScript
            "node": ("runtime", ["node", "--version"]),
            "npm": ("package_manager", ["npm", "--version"]),
            "npx": ("package_manager", ["npx", "--version"]),
            "pnpm": ("package_manager", ["pnpm", "--version"]),
            "yarn": ("package_manager", ["yarn", "--version"]),
            "bun": ("runtime", ["bun", "--version"]),
            "deno": ("runtime", ["deno", "--version"]),
            # Rust
            "rustc": ("compiler", ["rustc", "--version"]),
            "cargo": ("package_manager", ["cargo", "--version"]),
            # .NET
            "dotnet": ("runtime", ["dotnet", "--info"]),
            # Java
            "java": ("runtime", ["java", "--version"]),
            "javac": ("compiler", ["javac", "--version"]),
            "mvn": ("build_system", ["mvn", "--version"]),
            "gradle": ("build_system", ["gradle", "--version"]),
            # Go
            "go": ("runtime", ["go", "version"]),
            # Dart/Flutter
            "dart": ("runtime", ["dart", "--version"]),
            "flutter": ("sdk", ["flutter", "--version"]),
            # Kotlin
            "kotlin": ("compiler", ["kotlin", "--version"]),
            # System tools
            "git": ("vcs", ["git", "--version"]),
            "git-lfs": ("vcs", ["git-lfs", "--version"]),
            "docker": ("container", ["docker", "--version"]),
            "docker-compose": ("container", ["docker-compose", "--version"]),
            "podman": ("container", ["podman", "--version"]),
            # Embedded
            "arduino-cli": ("firmware", ["arduino-cli", "version"]),
            "pio": ("firmware", ["pio", "--version"]),
            # Shader
            "glslangValidator": ("shader_compiler", ["glslangValidator", "--version"]),
            "spirv-val": ("shader_compiler", ["spirv-val", "--version"]),
            # Database
            "psql": ("database_cli", ["psql", "--version"]),
            "mysql": ("database_cli", ["mysql", "--version"]),
            "sqlite3": ("database_cli", ["sqlite3", "--version"]),
            # WSL
            "wsl": ("wsl", ["wsl", "--status"]),
        }

    def _run_probe(self, cmd: list[str], timeout: float = 10.0) -> tuple[bool, str]:
        """Run a probe command safely with timeout."""
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, shell=False
            )
            output = (result.stdout or result.stderr or "").strip()
            return result.returncode == 0, output
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, str(e)

    def _discover_os(self) -> OSInfo:
        """Discover OS information."""
        info = OSInfo()
        info.platform = platform.system()
        info.release = platform.release()
        info.version = platform.version()
        info.architecture = platform.machine()

        if sys.platform == "win32":
            try:
                import ctypes
                info.build = str(ctypes.windll.kernel32.GetVersion() & 0xFFFF)
            except Exception:
                info.build = ""
        return info

    def _discover_cpu(self) -> CPUInfo:
        """Discover CPU information."""
        info = CPUInfo()
        info.architecture = platform.machine()

        if sys.platform == "win32":
            try:
                import wmi
                c = wmi.WMI()
                for cpu in c.Win32_Processor():
                    info.vendor = cpu.Manufacturer or ""
                    info.model = cpu.Name or ""
                    info.physical_cores = cpu.NumberOfCores or 0
                    info.logical_processors = cpu.NumberOfLogicalProcessors or 0
                    info.frequency_mhz = cpu.MaxClockSpeed or 0.0
                    break
            except Exception:
                pass

            # CPU features from platform
            info.features = self._get_cpu_features_windows()

        else:
            # Linux/macOS
            try:
                with open("/proc/cpuinfo", "r") as f:
                    content = f.read()
                for line in content.splitlines():
                    if line.startswith("vendor_id"):
                        info.vendor = line.split(":")[1].strip()
                    elif line.startswith("model name"):
                        info.model = line.split(":")[1].strip()
                    elif line.startswith("cpu cores"):
                        info.physical_cores = int(line.split(":")[1].strip())
                    elif line.startswith("siblings"):
                        info.logical_processors = int(line.split(":")[1].strip())
                    elif line.startswith("flags") or line.startswith("Features"):
                        info.features = line.split(":")[1].strip().split()
                        break
            except Exception:
                pass

        # Fallback to os.cpu_count
        if info.logical_processors == 0:
            info.logical_processors = os.cpu_count() or 0
        if info.physical_cores == 0 and info.logical_processors > 0:
            info.physical_cores = max(1, info.logical_processors // 2)

        return info

    def _get_cpu_features_windows(self) -> list[str]:
        """Get CPU features on Windows."""
        features = []
        try:
            import ctypes
            class CpuidResult(ctypes.Structure):
                _fields_ = [("eax", ctypes.c_uint),
                           ("ebx", ctypes.c_uint),
                           ("ecx", ctypes.c_uint),
                           ("edx", ctypes.c_uint)]

            def cpuid(eax: int, ecx: int = 0) -> CpuidResult:
                result = CpuidResult()
                ctypes.windll.kernel32.GetNativeSystemInfo(ctypes.byref(result))
                return result

            # This is simplified - actual CPUID would need inline assembly or specific APIs
            # For now, return common features
            features = ["SSE", "SSE2", "SSE3", "SSSE3", "SSE4.1", "SSE4.2", "AVX", "AVX2", "FMA"]
        except Exception:
            pass
        return features

    def _discover_memory(self) -> MemoryInfo:
        """Discover memory information."""
        info = MemoryInfo()

        if sys.platform == "win32":
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                ms = MEMORYSTATUSEX()
                ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms)):
                    info.total_mb = int(ms.ullTotalPhys // (1024 * 1024))
                    info.available_mb = int(ms.ullAvailPhys // (1024 * 1024))
                    info.swap_total_mb = int(ms.ullTotalPageFile // (1024 * 1024))
                    info.swap_available_mb = int(ms.ullAvailPageFile // (1024 * 1024))
            except Exception:
                pass
        else:
            try:
                with open("/proc/meminfo", "r") as f:
                    content = f.read()
                for line in content.splitlines():
                    if line.startswith("MemTotal:"):
                        info.total_mb = int(line.split()[1]) // 1024
                    elif line.startswith("MemAvailable:"):
                        info.available_mb = int(line.split()[1]) // 1024
                    elif line.startswith("SwapTotal:"):
                        info.swap_total_mb = int(line.split()[1]) // 1024
                    elif line.startswith("SwapFree:"):
                        info.swap_available_mb = int(line.split()[1]) // 1024
            except Exception:
                pass

        return info

    def _discover_gpus(self) -> list[GPUInfo]:
        """Discover GPU information."""
        gpus = []

        if sys.platform == "win32":
            try:
                import wmi
                c = wmi.WMI()
                for gpu in c.Win32_VideoController():
                    g = GPUInfo()
                    g.vendor = gpu.AdapterCompatibility or ""
                    g.model = gpu.Name or ""
                    if gpu.AdapterRAM:
                        g.vram_mb = int(gpu.AdapterRAM // (1024 * 1024))
                    g.driver_version = gpu.DriverVersion or ""
                    gpus.append(g)
            except Exception:
                pass

            # Try nvidia-smi for NVIDIA GPUs
            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            g = GPUInfo()
                            g.vendor = "NVIDIA"
                            g.model = parts[0]
                            g.vram_mb = int(parts[1])
                            g.driver_version = parts[2]
                            g.apis = ["CUDA", "OpenCL", "Vulkan"]
                            gpus.append(g)
            except Exception:
                pass

        else:
            # Linux - try lspci and nvidia-smi
            try:
                result = subprocess.run(
                    ["lspci", "-nn"], capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.splitlines():
                    if "VGA" in line or "3D" in line or "Display" in line:
                        g = GPUInfo()
                        g.model = line.split(":")[-1].strip()
                        gpus.append(g)
            except Exception:
                pass

            try:
                result = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().splitlines():
                        parts = [p.strip() for p in line.split(",")]
                        if len(parts) >= 3:
                            g = GPUInfo()
                            g.vendor = "NVIDIA"
                            g.model = parts[0]
                            g.vram_mb = int(parts[1])
                            g.driver_version = parts[2]
                            g.apis = ["CUDA", "OpenCL", "Vulkan"]
                            gpus.append(g)
            except Exception:
                pass

        return gpus

    @staticmethod
    def _decode_cli_bytes(data) -> str:
        """Decode CLI output, tolerating UTF-16LE (wsl.exe) and locale encodings."""
        if not data:
            return ""
        if isinstance(data, str):
            return data.replace("\x00", "")
        if b"\x00" in data:
            for enc in ("utf-16", "utf-16-le", "utf-8", "mbcs"):
                try:
                    return data.decode(enc)
                except Exception:
                    continue
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _discover_storage(self) -> list[StorageInfo]:
        """Discover storage devices."""
        storage = []

        if sys.platform == "win32":
            try:
                import wmi  # type: ignore
                c = wmi.WMI()
                for disk in c.Win32_LogicalDisk():
                    s = StorageInfo()
                    s.device = disk.DeviceID or ""
                    s.mount_point = disk.DeviceID or ""
                    s.filesystem = disk.FileSystem or ""
                    s.total_gb = round((disk.Size or 0) / (1024**3), 2)
                    s.free_gb = round((disk.FreeSpace or 0) / (1024**3), 2)
                    s.is_removable = disk.DriveType == 2
                    storage.append(s)
            except Exception:
                pass
            if not storage:
                # Fallback without wmi: disk_usage per existing drive letter.
                import string
                for letter in string.ascii_uppercase:
                    mount = f"{letter}:\\"
                    try:
                        if not os.path.exists(mount):
                            continue
                        usage = shutil.disk_usage(mount)
                    except OSError:
                        continue
                    s = StorageInfo()
                    s.device = f"{letter}:"
                    s.mount_point = mount
                    s.filesystem = ""
                    s.total_gb = round(usage.total / (1024**3), 2)
                    s.free_gb = round(usage.free / (1024**3), 2)
                    s.is_removable = False
                    storage.append(s)
        else:
            try:
                result = subprocess.run(
                    ["df", "-h", "-T"], capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 7:
                        s = StorageInfo()
                        s.filesystem = parts[1]
                        s.total_gb = self._parse_size(parts[2])
                        s.free_gb = self._parse_size(parts[4])
                        s.mount_point = parts[6]
                        s.device = parts[0]
                        storage.append(s)
            except Exception:
                pass

        return storage

    def _parse_size(self, size_str: str) -> float:
        """Parse size string like '100G' or '50M' to GB."""
        try:
            if size_str.endswith("G"):
                return float(size_str[:-1])
            elif size_str.endswith("M"):
                return float(size_str[:-1]) / 1024
            elif size_str.endswith("K"):
                return float(size_str[:-1]) / (1024 * 1024)
            elif size_str.endswith("T"):
                return float(size_str[:-1]) * 1024
        except Exception:
            pass
        return 0.0

    def _discover_virtualization(self) -> VirtualizationInfo:
        """Discover virtualization and WSL information."""
        info = VirtualizationInfo()

        # Check for virtualization
        if sys.platform == "win32":
            try:
                import wmi
                c = wmi.WMI()
                for sys_info in c.Win32_ComputerSystem():
                    if sys_info.Manufacturer and ("vmware" in sys_info.Manufacturer.lower()
                                                  or "virtual" in sys_info.Manufacturer.lower()):
                        info.enabled = True
                        info.hypervisor = sys_info.Manufacturer
                    break
            except Exception:
                pass

            # WSL detection (wsl.exe emits UTF-16LE; decode tolerantly)
            try:
                result = subprocess.run(
                    ["wsl", "--status"], capture_output=True, timeout=10
                )
                out = self._decode_cli_bytes(result.stdout) if result.returncode == 0 else ""
                if result.returncode == 0 and out:
                    info.enabled = True
                    info.hypervisor = "WSL2"
                    for line in out.replace("\x00", "").splitlines():
                        if "WSL version" in line:
                            info.wsl_version = line.split(":")[-1].strip()
                        elif "Default Version" in line and not info.wsl_version:
                            info.wsl_version = line.split(":")[-1].strip()
                        if "Default Distribution" in line:
                            info.wsl_distros.append({"name": line.split(":")[-1].strip(), "default": True})
            except Exception:
                pass

            # List WSL distributions
            try:
                result = subprocess.run(
                    ["wsl", "-l", "-v"], capture_output=True, timeout=10
                )
                out = self._decode_cli_bytes(result.stdout) if result.returncode == 0 else ""
                if result.returncode == 0 and out:
                    for line in out.replace("\x00", "").splitlines()[1:]:
                        parts = line.split()
                        if not parts:
                            continue
                        is_default = "*" in line
                        # wsl.exe emits '*' as a separate token: ['*', 'Ubuntu', 'Stopped', '2']
                        if parts[0] == "*" and len(parts) >= 4:
                            name, state, version = parts[1], parts[2], parts[3]
                        elif len(parts) >= 3:
                            name, state, version = (parts[0].replace("*", "").strip(),
                                                    parts[1], parts[2])
                        else:
                            continue
                        if not name:
                            continue
                        info.wsl_distros.append({
                            "name": name, "state": state,
                            "version": version, "default": is_default,
                        })
            except Exception:
                pass

            # Docker
            ok, _ = self._run_probe(["docker", "--version"])
            info.docker_available = ok

            # Podman
            ok, _ = self._run_probe(["podman", "--version"])
            info.podman_available = ok

        else:
            # Linux - check for containers
            try:
                with open("/proc/1/cgroup", "r") as f:
                    content = f.read()
                    if "docker" in content:
                        info.docker_available = True
                        info.enabled = True
                        info.hypervisor = "Docker"
                    elif "lxc" in content:
                        info.enabled = True
                        info.hypervisor = "LXC"
            except Exception:
                pass

            ok, _ = self._run_probe(["docker", "--version"])
            info.docker_available = ok

            ok, _ = self._run_probe(["podman", "--version"])
            info.podman_available = ok

        return info

    def _discover_shells(self) -> list[ShellInfo]:
        """Discover available shells."""
        shells = []
        shell_candidates = {
            "powershell": ["powershell", "-Command", "$PSVersionTable.PSVersion"],
            "pwsh": ["pwsh", "-Command", "$PSVersionTable.PSVersion"],
            "cmd": ["cmd", "/c", "ver"],
            "bash": ["bash", "--version"],
            "zsh": ["zsh", "--version"],
            "fish": ["fish", "--version"],
            "git-bash": ["bash", "--version"],  # Git Bash uses bash
        }

        for name, cmd in shell_candidates.items():
            exe = shutil.which(cmd[0])
            if exe:
                ok, output = self._run_probe(cmd)
                if ok:
                    s = ShellInfo()
                    s.name = name
                    s.executable = exe
                    s.version = output.splitlines()[0] if output else ""
                    shells.append(s)

        # Determine default shell
        if sys.platform == "win32":
            for s in shells:
                if s.name in ("powershell", "pwsh"):
                    s.is_default = True
                    break
        else:
            for s in shells:
                if s.name == "bash":
                    s.is_default = True
                    break

        return shells

    def _discover_tools(self) -> list[ToolInfo]:
        """Discover development tools.

        Records every binary found on PATH. working=True only when the
        safe version probe succeeds; otherwise working=False with the
        probe output retained (AVAILABLE_BUT_BROKEN visibility).
        """
        tools = []
        for name, (category, probe_cmd) in self._tool_probes.items():
            exe = shutil.which(name.split()[0])
            if not exe:
                continue

            # Probe via resolved executable so Windows .CMD shims resolve.
            cmd = [exe] + list(probe_cmd[1:])
            ok, output = self._run_probe(cmd)
            if not ok and sys.platform == "win32" and \
                    exe.lower().endswith((".cmd", ".bat", ".ps1")):
                try:
                    import subprocess as _sp
                    r = _sp.run(" ".join(cmd), capture_output=True, text=True,
                                timeout=10, shell=True)
                    out = (r.stdout or r.stderr or "").strip()
                    if r.returncode == 0 and out:
                        ok, output = True, out
                except Exception:
                    pass
            t = ToolInfo()
            t.name = name
            t.executable = exe
            t.category = category
            t.version = (output.splitlines()[0] if output else "")[:200]
            t.working = bool(ok)
            t.probe_command = " ".join(probe_cmd)
            t.probe_output = (output or "")[:500]
            t.languages = self._infer_languages(name, category)
            tools.append(t)

        return tools

    def _infer_languages(self, tool_name: str, category: str) -> list[str]:
        """Infer supported languages from tool name and category."""
        lang_map = {
            "clang": ["c", "cpp", "objective-c", "objective-cpp"],
            "clang++": ["cpp", "c++"],
            "gcc": ["c", "cpp", "fortran", "ada"],
            "g++": ["cpp", "c++"],
            "cl.exe": ["c", "cpp"],
            "cmake": ["c", "cpp", "cuda", "fortran"],
            "ninja": ["c", "cpp", "rust", "go"],
            "meson": ["c", "cpp", "rust", "vala"],
            "msbuild": ["csharp", "vb", "fsharp", "cpp"],
            "python": ["python"],
            "py": ["python"],
            "pip": ["python"],
            "uv": ["python"],
            "conda": ["python", "r"],
            "node": ["javascript", "typescript"],
            "npm": ["javascript", "typescript"],
            "pnpm": ["javascript", "typescript"],
            "yarn": ["javascript", "typescript"],
            "bun": ["javascript", "typescript"],
            "deno": ["javascript", "typescript"],
            "rustc": ["rust"],
            "cargo": ["rust"],
            "dotnet": ["csharp", "fsharp", "vb"],
            "java": ["java"],
            "javac": ["java"],
            "mvn": ["java", "kotlin", "scala"],
            "gradle": ["java", "kotlin", "groovy", "scala"],
            "go": ["go"],
            "dart": ["dart"],
            "flutter": ["dart"],
            "kotlin": ["kotlin"],
            "git": [],
            "git-lfs": [],
            "docker": [],
            "docker-compose": [],
            "podman": [],
            "arduino-cli": ["c", "cpp"],
            "pio": ["c", "cpp"],
            "glslangValidator": ["glsl", "spirv"],
            "spirv-val": ["spirv"],
            "psql": ["sql"],
            "mysql": ["sql"],
            "sqlite3": ["sql"],
        }
        return lang_map.get(tool_name, [])

    def _discover_runtimes(self) -> list[RuntimeInfo]:
        """Discover AI runtimes (Ollama, etc.)."""
        runtimes = []

        # Try to import and use the existing runtime discovery
        try:
            from runtimes.discovery import LocalRuntimeDiscovery
            discovery = LocalRuntimeDiscovery()
            for desc in discovery.discover():
                r = RuntimeInfo()
                r.name = desc.runtime_id
                r.executable = desc.executable
                r.version = desc.version
                r.endpoint = desc.endpoint
                r.protocol = desc.protocol
                r.models = desc.models
                r.status = desc.status
                runtimes.append(r)
        except Exception:
            # Fallback: check for Ollama directly
            exe = shutil.which("ollama")
            if exe:
                ok, output = self._run_probe(["ollama", "list"])
                if ok:
                    r = RuntimeInfo()
                    r.name = "ollama"
                    r.executable = exe
                    r.status = "HEALTHY"
                    r.protocol = "OLLAMA_COMPATIBLE"
                    r.endpoint = "http://127.0.0.1:11434"
                    # Parse ollama list output
                    for line in output.splitlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 2:
                            r.models.append({"name": parts[0], "size": parts[1]})
                    runtimes.append(r)

        return runtimes

    def _discover_environment_variables(self) -> dict[str, str]:
        """Get safe environment variables (no secrets)."""
        safe_vars = {}
        skip_patterns = ("key", "secret", "token", "password", "auth", "credential")
        for k, v in os.environ.items():
            if not any(p in k.lower() for p in skip_patterns):
                safe_vars[k] = v
        return safe_vars

    def scan(self, force: bool = False) -> MachineCapability:
        """Perform a full machine capability scan."""
        now = time.time()
        if not force and self._cache and (now - self._cache_timestamp) < self._cache_ttl:
            return self._cache

        cap = MachineCapability()
        cap.os = self._discover_os()
        cap.cpu = self._discover_cpu()
        cap.memory = self._discover_memory()
        cap.gpus = self._discover_gpus()
        cap.storage = self._discover_storage()
        cap.virtualization = self._discover_virtualization()
        cap.shells = self._discover_shells()
        cap.tools = self._discover_tools()
        cap.runtimes = self._discover_runtimes()
        cap.environment_variables = self._discover_environment_variables()

        self._cache = cap
        self._cache_timestamp = now
        return cap

    def invalidate_cache(self) -> None:
        """Invalidate the cached capability scan."""
        self._cache = None
        self._cache_timestamp = 0.0

    def get_cached(self) -> MachineCapability | None:
        """Get cached capability if available and not expired."""
        if self._cache and (time.time() - self._cache_timestamp) < self._cache_ttl:
            return self._cache
        return None

    def to_dict(self, cap: MachineCapability | None = None) -> dict[str, Any]:
        """Convert capability to dictionary."""
        if cap is None:
            cap = self.get_cached()
            if cap is None:
                cap = self.scan()
        return asdict(cap)


def discover_machine_capability(force: bool = False) -> MachineCapability:
    """Convenience function for one-shot discovery."""
    registry = MachineCapabilityRegistry()
    return registry.scan(force=force)


if __name__ == "__main__":
    import json
    registry = MachineCapabilityRegistry()
    cap = registry.scan(force=True)
    print(json.dumps(registry.to_dict(cap), indent=2, default=str))