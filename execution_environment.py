"""Execution Environment Registry (v0.9.0 Phase 1).

Represents execution environments independently from individual tools.
Supports Windows native, WSL, Docker, Podman, and future remote environments.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from machine_capability import MachineCapabilityRegistry, MachineCapability, ToolInfo


@dataclass
class ExecutionEnvironment:
    """Represents a single execution environment."""
    identifier: str = ""  # e.g., "WINDOWS_NATIVE", "WSL:Ubuntu-22.04", "DOCKER"
    platform: str = ""  # windows, linux, darwin
    architecture: str = ""
    shell: str = ""
    shell_executable: str = ""
    available_tools: list[str] = field(default_factory=list)
    path_semantics: str = "windows"  # windows, posix
    environment_variables: dict[str, str] = field(default_factory=dict)
    working_directory_behavior: str = "native"  # native, wsl_mapped, container_mapped
    health: str = "UNKNOWN"  # HEALTHY, DEGRADED, UNAVAILABLE
    limitations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionEnvironmentRegistry:
    """Registry for discovering and managing execution environments."""

    def __init__(self):
        self._environments: dict[str, ExecutionEnvironment] = {}
        self._machine_registry = MachineCapabilityRegistry()

    def _create_windows_native(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create Windows native environment."""
        env = ExecutionEnvironment()
        env.identifier = "WINDOWS_NATIVE"
        env.platform = "windows"
        env.architecture = machine.cpu.architecture or platform.machine()
        
        # Find default shell
        default_shell = "powershell"
        for s in machine.shells:
            if s.is_default:
                default_shell = s.name
                env.shell_executable = s.executable
                break
        env.shell = default_shell
        
        # Available tools
        env.available_tools = [t.name for t in machine.tools]
        
        # Path semantics
        env.path_semantics = "windows"
        
        # Environment variables (safe subset)
        env.environment_variables = dict(machine.environment_variables)
        
        # Working directory behavior
        env.working_directory_behavior = "native"
        
        # Health
        env.health = "HEALTHY"
        
        # Metadata
        env.metadata = {
            "os_version": f"{machine.os.platform} {machine.os.release}",
            "ram_mb": machine.memory.total_mb,
            "gpu_count": len(machine.gpus),
        }
        
        return env

    def _create_powershell_env(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create PowerShell-specific environment."""
        env = ExecutionEnvironment()
        env.identifier = "POWERSHELL"
        env.platform = "windows"
        env.architecture = machine.cpu.architecture or platform.machine()
        env.shell = "powershell"
        
        for s in machine.shells:
            if s.name == "powershell":
                env.shell_executable = s.executable
                break
        
        env.available_tools = [t.name for t in machine.tools]
        env.path_semantics = "windows"
        env.working_directory_behavior = "native"
        env.health = "HEALTHY" if env.shell_executable else "UNAVAILABLE"
        env.metadata = {"shell_type": "powershell", "version": next((s.version for s in machine.shells if s.name == "powershell"), "")}
        
        return env

    def _create_cmd_env(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create CMD environment."""
        env = ExecutionEnvironment()
        env.identifier = "CMD"
        env.platform = "windows"
        env.architecture = machine.cpu.architecture or platform.machine()
        env.shell = "cmd"
        env.shell_executable = "cmd.exe"
        env.available_tools = [t.name for t in machine.tools]
        env.path_semantics = "windows"
        env.working_directory_behavior = "native"
        env.health = "HEALTHY"
        env.metadata = {"shell_type": "cmd"}
        
        return env

    def _create_wsl_env(self, machine: MachineCapability, distro: dict[str, Any]) -> ExecutionEnvironment:
        """Create WSL distribution environment."""
        name = distro.get("name", "Unknown")
        env = ExecutionEnvironment()
        env.identifier = f"WSL:{name}"
        env.platform = "linux"
        env.architecture = "x86_64"  # WSL2 is typically x64
        env.shell = "bash"
        
        # WSL bash executable
        env.shell_executable = "wsl.exe"
        
        # Available tools - start with Windows tools that work via wsl
        env.available_tools = [t.name for t in machine.tools if t.category in ("vcs", "container")]
        
        # Path semantics - WSL uses POSIX paths internally
        env.path_semantics = "posix"
        
        # Environment variables
        env.environment_variables = {
            "WSL_DISTRO_NAME": name,
            "WSL_INTEROP": "1",
        }
        
        # Working directory behavior - paths are mapped
        env.working_directory_behavior = "wsl_mapped"
        
        # Health
        state = distro.get("state", "Unknown")
        env.health = "HEALTHY" if state == "Running" else "DEGRADED"
        
        # Limitations
        if state != "Running":
            env.limitations.append(f"WSL distribution '{name}' is not running (state: {state})")
        env.limitations.append("GUI applications require X server")
        env.limitations.append("Windows path access via /mnt/<drive>")
        
        # Metadata
        env.metadata = {
            "distro_name": name,
            "distro_state": state,
            "distro_version": distro.get("version", ""),
            "is_default": distro.get("default", False),
            "wsl_version": machine.virtualization.wsl_version,
        }
        
        return env

    def _create_git_bash_env(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create Git Bash environment."""
        env = ExecutionEnvironment()
        env.identifier = "GIT_BASH"
        env.platform = "windows"
        env.architecture = machine.cpu.architecture or platform.machine()
        env.shell = "bash"
        
        # Git Bash typically at C:\Program Files\Git\bin\bash.exe
        git_bash_paths = [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
        for path in git_bash_paths:
            if Path(path).exists():
                env.shell_executable = path
                break
        
        env.available_tools = ["git", "bash", "ssh", "curl", "tar", "find", "grep"]
        env.path_semantics = "posix"  # Git Bash uses POSIX paths
        env.working_directory_behavior = "posix_mapped"
        env.health = "HEALTHY" if env.shell_executable else "UNAVAILABLE"
        env.limitations.append("Limited to Git for Windows toolchain")
        env.metadata = {"source": "Git for Windows"}
        
        return env

    def _create_docker_env(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create Docker environment."""
        env = ExecutionEnvironment()
        env.identifier = "DOCKER"
        env.platform = "linux"  # Containers run Linux
        env.architecture = machine.cpu.architecture or platform.machine()
        env.shell = "sh"
        env.shell_executable = "docker"
        
        env.available_tools = ["docker", "docker-compose"] + [
            t.name for t in machine.tools if t.category == "container"
        ]
        env.path_semantics = "posix"
        env.working_directory_behavior = "container_mapped"
        env.health = "HEALTHY" if machine.virtualization.docker_available else "UNAVAILABLE"
        env.limitations.append("Requires Docker daemon running")
        env.limitations.append("File system access via volume mounts")
        env.limitations.append("Network isolation by default")
        env.metadata = {
            "docker_version": next((t.version for t in machine.tools if t.name == "docker"), ""),
        }
        
        return env

    def _create_podman_env(self, machine: MachineCapability) -> ExecutionEnvironment:
        """Create Podman environment."""
        env = ExecutionEnvironment()
        env.identifier = "PODMAN"
        env.platform = "linux"
        env.architecture = machine.cpu.architecture or platform.machine()
        env.shell = "sh"
        env.shell_executable = "podman"
        
        env.available_tools = ["podman"] + [
            t.name for t in machine.tools if t.category == "container"
        ]
        env.path_semantics = "posix"
        env.working_directory_behavior = "container_mapped"
        env.health = "HEALTHY" if machine.virtualization.podman_available else "UNAVAILABLE"
        env.limitations.append("Rootless by default")
        env.limitations.append("No daemon required")
        env.metadata = {
            "podman_version": next((t.version for t in machine.tools if t.name == "podman"), ""),
        }
        
        return env

    def discover(self, machine: MachineCapability | None = None) -> dict[str, ExecutionEnvironment]:
        """Discover all available execution environments."""
        if machine is None:
            machine = self._machine_registry.scan()
        
        environments = {}
        
        # Windows native environments
        if sys.platform == "win32" or machine.os.platform == "Windows":
            environments["WINDOWS_NATIVE"] = self._create_windows_native(machine)
            environments["POWERSHELL"] = self._create_powershell_env(machine)
            environments["CMD"] = self._create_cmd_env(machine)
            
            # Git Bash if available
            if any("git-bash" in s.name.lower() or "bash" in s.name.lower() 
                   for s in machine.shells if "git" in s.executable.lower()):
                environments["GIT_BASH"] = self._create_git_bash_env(machine)
            
            # WSL distributions
            for distro in machine.virtualization.wsl_distros:
                env = self._create_wsl_env(machine, distro)
                environments[env.identifier] = env
            
            # Docker
            if machine.virtualization.docker_available:
                environments["DOCKER"] = self._create_docker_env(machine)
            
            # Podman
            if machine.virtualization.podman_available:
                environments["PODMAN"] = self._create_podman_env(machine)
        
        else:
            # Linux/macOS native
            env = ExecutionEnvironment()
            env.identifier = "LINUX_NATIVE" if sys.platform == "linux" else "DARWIN_NATIVE"
            env.platform = "linux" if sys.platform == "linux" else "darwin"
            env.architecture = machine.cpu.architecture or platform.machine()
            env.shell = "bash"
            env.shell_executable = shutil.which("bash") or "/bin/bash"
            env.available_tools = [t.name for t in machine.tools]
            env.path_semantics = "posix"
            env.working_directory_behavior = "native"
            env.health = "HEALTHY"
            env.metadata = {"os_version": f"{machine.os.platform} {machine.os.release}"}
            environments[env.identifier] = env
            
            # Docker on Linux
            if machine.virtualization.docker_available:
                environments["DOCKER"] = self._create_docker_env(machine)
            
            # Podman on Linux
            if machine.virtualization.podman_available:
                environments["PODMAN"] = self._create_podman_env(machine)
        
        self._environments = environments
        return environments

    def get(self, identifier: str) -> ExecutionEnvironment | None:
        """Get an environment by identifier."""
        return self._environments.get(identifier)

    def list(self) -> list[ExecutionEnvironment]:
        """List all discovered environments."""
        return list(self._environments.values())

    def list_healthy(self) -> list[ExecutionEnvironment]:
        """List only healthy environments."""
        return [e for e in self._environments.values() if e.health == "HEALTHY"]

    def find_for_tool(self, tool_name: str) -> list[ExecutionEnvironment]:
        """Find environments that have a specific tool available."""
        return [e for e in self._environments.values() 
                if tool_name in e.available_tools and e.health == "HEALTHY"]

    def find_for_language(self, language: str, machine: MachineCapability | None = None) -> list[ExecutionEnvironment]:
        """Find environments that support a specific language."""
        if machine is None:
            machine = self._machine_registry.scan()
        
        # Find tools that support this language
        supporting_tools = [t.name for t in machine.tools if language in t.languages]
        
        # Find environments with those tools
        envs = []
        for e in self._environments.values():
            if any(t in e.available_tools for t in supporting_tools):
                envs.append(e)
        return envs

    def convert_path(self, path: str, from_env: str, to_env: str) -> str:
        """Convert a path between execution environments."""
        if from_env == to_env:
            return path
        
        from_env_obj = self.get(from_env)
        to_env_obj = self.get(to_env)
        
        if not from_env_obj or not to_env_obj:
            return path
        
        # Windows -> WSL
        if from_env_obj.path_semantics == "windows" and to_env_obj.path_semantics == "posix":
            if from_env_obj.identifier == "WINDOWS_NATIVE" and to_env_obj.identifier.startswith("WSL:"):
                # C:\Users\... -> /mnt/c/Users/...
                path = path.replace("\\", "/")
                if len(path) >= 2 and path[1] == ":":
                    drive = path[0].lower()
                    path = f"/mnt/{drive}{path[2:]}"
                return path
        
        # WSL -> Windows
        if from_env_obj.path_semantics == "posix" and to_env_obj.path_semantics == "windows":
            if from_env_obj.identifier.startswith("WSL:") and to_env_obj.identifier == "WINDOWS_NATIVE":
                if path.startswith("/mnt/"):
                    parts = path.split("/")
                    if len(parts) >= 3:
                        drive = parts[2].upper()
                        rest = "/".join(parts[3:])
                        return f"{drive}:\\{rest.replace('/', '\\')}"
        
        # Container paths (simplified - actual conversion depends on volume mounts)
        if to_env_obj.working_directory_behavior == "container_mapped":
            return path  # Container paths are relative to mount points
        
        return path

    def to_dict(self) -> dict[str, Any]:
        """Convert all environments to dictionary."""
        return {k: asdict(v) for k, v in self._environments.items()}


def discover_execution_environments(machine: MachineCapability | None = None) -> dict[str, ExecutionEnvironment]:
    """Convenience function for one-shot discovery."""
    registry = ExecutionEnvironmentRegistry()
    return registry.discover(machine)


if __name__ == "__main__":
    import json
    from machine_capability import discover_machine_capability
    
    machine = discover_machine_capability(force=True)
    registry = ExecutionEnvironmentRegistry()
    envs = registry.discover(machine)
    print(json.dumps(registry.to_dict(), indent=2, default=str))