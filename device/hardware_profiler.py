"""HardwareProfiler (v0.7). Detailed hardware detection.

Detects detailed hardware characteristics:
- CPU (vendor, model, cores, frequency)
- GPU (vendor, model, VRAM, compute capabilities)
- RAM (total, available, swap)
- Storage (total, free, type)
- AI accelerators (NPU, TPU, etc.)
- Battery status
- Network status
- Display information
"""
from __future__ import annotations

import os
import platform
import time
from typing import Any

from device.device_profile import (
    AcceleratorInfo, BatteryInfo, CPUInfo, DisplayInfo, GPUInfo,
    MEDIA_HARDWARE_PRESENT, MEDIA_NOT_PRESENT, MEDIA_PERMISSION_UNKNOWN,
    MediaInfo, MemoryInfo, NetworkInfo, PackageManagerInfo, StorageInfo
)


class HardwareProfiler:
    """Detailed hardware profiling."""
    
    def __init__(self):
        self._cached_cpu: CPUInfo | None = None
        self._cached_gpu: GPUInfo | None = None
        self._cached_memory: MemoryInfo | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes cache
    
    def profile_cpu(self, force_refresh: bool = False) -> CPUInfo:
        """Profile CPU information."""
        if not force_refresh and self._cached_cpu:
            if time.monotonic() - self._cache_time < self._cache_ttl:
                return self._cached_cpu
        
        cpu_info = CPUInfo()
        
        # Basic CPU info from platform module
        try:
            cpu_info.model = platform.processor()
            cpu_info.architecture = platform.machine().lower()
        except Exception:
            pass
        
        # Try to get more detailed info
        try:
            import psutil
            
            # CPU count
            cpu_info.physical_cores = psutil.cpu_count(logical=False) or 0
            cpu_info.logical_cores = psutil.cpu_count(logical=True) or 0
            
            # CPU frequency
            freq_info = psutil.cpu_freq()
            if freq_info:
                cpu_info.frequency_mhz = int(freq_info.max)
            
            # CPU info (vendor/model)
            try:
                cpu_info.vendor = self._detect_cpu_vendor()
                cpu_info.model = self._detect_cpu_model()
            except Exception:
                pass
                
        except ImportError:
            # psutil not available, use basic platform info
            cpu_info.logical_cores = os.cpu_count() or 0
            cpu_info.physical_cores = cpu_info.logical_cores  # Assume same
        
        # Windows-specific: try to get better model name via wmic
        if platform.system() == "Windows" and (not cpu_info.model or "Family" in cpu_info.model):
            self._enhance_cpu_info_windows(cpu_info)
        
        self._cached_cpu = cpu_info
        self._cache_time = time.monotonic()
        return cpu_info
    
    def profile_gpu(self, force_refresh: bool = False) -> GPUInfo:
        """Profile GPU information."""
        if not force_refresh and self._cached_gpu:
            if time.monotonic() - self._cache_time < self._cache_ttl:
                return self._cached_gpu
        
        gpu_info = GPUInfo()
        
        # Try different GPU detection methods
        try:
            # Try NVIDIA
            gpu_info = self._detect_nvidia_gpu()
        except Exception:
            pass
        
        try:
            # Try AMD/ATI
            if not gpu_info.vendor:
                gpu_info = self._detect_amd_gpu()
        except Exception:
            pass
        
        try:
            # Try Intel
            if not gpu_info.vendor:
                gpu_info = self._detect_intel_gpu()
        except Exception:
            pass
        
        try:
            # Try Apple Silicon (Metal)
            if not gpu_info.vendor and platform.system() == "Darwin":
                gpu_info = self._detect_apple_gpu()
        except Exception:
            pass
        
        # Check compute capabilities
        gpu_info.cuda_available = self._check_cuda()
        gpu_info.metal_available = self._check_metal()
        gpu_info.vulkan_available = self._check_vulkan()
        gpu_info.directml_available = self._check_directml()
        
        self._cached_gpu = gpu_info
        self._cache_time = time.monotonic()
        return gpu_info
    
    def profile_memory(self, force_refresh: bool = False) -> MemoryInfo:
        """Profile memory information."""
        if not force_refresh and self._cached_memory:
            if time.monotonic() - self._cache_time < self._cache_ttl:
                return self._cached_memory
        
        memory_info = MemoryInfo()
        
        try:
            import psutil
            
            # RAM
            vm = psutil.virtual_memory()
            memory_info.total_mb = vm.total // (1024 * 1024)
            memory_info.available_mb = vm.available // (1024 * 1024)
            
            # Swap
            swap = psutil.swap_memory()
            memory_info.swap_total_mb = swap.total // (1024 * 1024)
            memory_info.swap_available_mb = swap.free // (1024 * 1024)
            
        except ImportError:
            # Fallback to basic memory info
            try:
                import os
                memory_info.total_mb = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") // (1024 * 1024)
            except Exception:
                pass
        
        self._cached_memory = memory_info
        self._cache_time = time.monotonic()
        return memory_info
    
    def profile_storage(self) -> StorageInfo:
        """Profile storage information."""
        storage_info = StorageInfo()
        
        try:
            import psutil
            disk = psutil.disk_usage("/")
            storage_info.total_mb = disk.total // (1024 * 1024)
            storage_info.free_mb = disk.free // (1024 * 1024)
            
            # Try to detect drive type
            storage_info.drive_type = self._detect_drive_type()
            
        except Exception:
            pass
        
        return storage_info
    
    def profile_battery(self) -> BatteryInfo:
        """Profile battery information."""
        battery_info = BatteryInfo()
        
        try:
            import psutil
            battery = psutil.sensors_battery()
            
            if battery:
                battery_info.present = True
                battery_info.level_percent = int(battery.percent)
                battery_info.charging = battery.power_plugged
                
                if battery.secsleft not in (-1, -2):
                    battery_info.time_remaining_minutes = battery.secsleft // 60
            
        except Exception:
            pass
        
        return battery_info
    
    def profile_network(self) -> NetworkInfo:
        """Profile network information."""
        network_info = NetworkInfo()
        
        try:
            import psutil
            
            # Check if any network interface is up
            stats = psutil.net_if_stats()
            for interface, stat in stats.items():
                if stat.isup:
                    network_info.connected = True
                    network_info.interface_type = self._detect_interface_type(interface)
                    break
            
        except Exception:
            pass
        
        return network_info
    
    def profile_display(self) -> DisplayInfo:
        """Profile display information."""
        display_info = DisplayInfo()
        
        try:
            # Try to get display info from platform-specific methods
            system = platform.system()
            
            if system == "Windows":
                display_info = self._get_windows_display()
            elif system == "Darwin":
                display_info = self._get_macos_display()
            elif system == "Linux":
                display_info = self._get_linux_display()
                
        except Exception:
            pass
        
        return display_info
    
    def profile_accelerators(self) -> list[AcceleratorInfo]:
        """Profile AI accelerators."""
        accelerators = []
        
        # Try to detect NPU
        try:
            npu = self._detect_npu()
            if npu:
                accelerators.append(npu)
        except Exception:
            pass
        
        # Try to detect TPU
        try:
            tpu = self._detect_tpu()
            if tpu:
                accelerators.append(tpu)
        except Exception:
            pass
        
        return accelerators
    
    def _detect_cpu_vendor(self) -> str:
        """Detect CPU vendor."""
        try:
            import platform
            processor = platform.processor().lower()
            
            if "intel" in processor or "genuineintel" in processor:
                return "Intel"
            elif "amd" in processor or "authenticamd" in processor:
                return "AMD"
            elif "arm" in processor or "aarch64" in processor:
                return "ARM"
            elif "apple" in processor:
                return "Apple"
            
        except Exception:
            pass
        
        return ""
    
    def _detect_cpu_model(self) -> str:
        """Detect CPU model."""
        try:
            import platform
            return platform.processor()
        except Exception:
            return ""
    
    def _enhance_cpu_info_windows(self, cpu_info: CPUInfo) -> None:
        """Enhance CPU info using Windows wmic."""
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                # Skip header line
                for line in lines[1:]:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 4:
                        # wmic output: MaxClockSpeed Name... NumberOfCores NumberOfLogicalProcessors
                        cpu_info.frequency_mhz = int(parts[0]) if parts[0].isdigit() else cpu_info.frequency_mhz
                        # Name might have spaces, so find the last 2 numbers
                        name_parts = parts[1:-2]
                        cpu_info.model = " ".join(name_parts)
                        cpu_info.physical_cores = int(parts[-2]) if parts[-2].isdigit() else cpu_info.physical_cores
                        cpu_info.logical_cores = int(parts[-1]) if parts[-1].isdigit() else cpu_info.logical_cores
                        break
        except Exception:
            pass
    
    def _detect_nvidia_gpu(self) -> GPUInfo:
        """Detect NVIDIA GPU."""
        gpu_info = GPUInfo()
        
        try:
            # Try to use nvidia-smi
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if lines:
                    parts = lines[0].split(",")
                    gpu_info.vendor = "NVIDIA"
                    gpu_info.model = parts[0].strip()
                    if len(parts) > 1:
                        mem_str = parts[1].strip()
                        # Parse memory like "8192 MiB"
                        gpu_info.vram_mb = int(mem_str.split()[0])
                    
        except Exception:
            pass
        
        return gpu_info
    
    def _detect_amd_gpu(self) -> GPUInfo:
        """Detect AMD GPU."""
        gpu_info = GPUInfo()
        
        try:
            # Try to use rocm-smi or similar
            import subprocess
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                gpu_info.vendor = "AMD"
                # Parse output for GPU model
                lines = result.stdout.split("\n")
                for line in lines:
                    if "GPU" in line or "Card" in line:
                        gpu_info.model = line.strip()
                        break
                    
        except Exception:
            pass
        
        return gpu_info
    
    def _detect_intel_gpu(self) -> GPUInfo:
        """Detect Intel GPU."""
        gpu_info = GPUInfo()
        
        try:
            # Try to detect Intel integrated graphics
            import subprocess
            result = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                for line in lines:
                    if "intel" in line.lower() and ("vga" in line.lower() or "display" in line.lower()):
                        gpu_info.vendor = "Intel"
                        gpu_info.model = line.strip()
                        break
                        
        except Exception:
            pass
        
        return gpu_info
    
    def _detect_apple_gpu(self) -> GPUInfo:
        """Detect Apple Silicon GPU."""
        gpu_info = GPUInfo()
        
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                gpu_info.vendor = "Apple"
                lines = result.stdout.split("\n")
                for line in lines:
                    if "chip" in line.lower() or "gpu" in line.lower():
                        gpu_info.model = line.strip()
                        break
                        
        except Exception:
            pass
        
        return gpu_info
    
    def _check_cuda(self) -> bool:
        """Check if CUDA is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvcc", "--version"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_metal(self) -> bool:
        """Check if Metal is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["xcode-select", "-p"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_vulkan(self) -> bool:
        """Check if Vulkan is available."""
        try:
            import subprocess
            result = subprocess.run(
                ["vulkaninfo"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_directml(self) -> bool:
        """Check if DirectML is available.

        dxdiag report goes to the system temp dir (never the repository
        root) to keep the product tree free of regenerable runtime data.
        """
        try:
            import subprocess
            import tempfile
            dest = os.path.join(tempfile.gettempdir(), "ab_dxdiag_output.txt")
            result = subprocess.run(
                ["dxdiag", "/t", dest],
                capture_output=True, text=True, timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def _detect_drive_type(self) -> str:
        """Detect drive type (SSD/HDD/NVMe)."""
        try:
            import subprocess
            import platform
            
            if platform.system() == "Windows":
                # Use PowerShell to get physical disk media types
                result = subprocess.run(
                    ["powershell", "-Command", "Get-PhysicalDisk | Select-Object -ExpandProperty MediaType"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        if "SSD" in line.upper():
                            return "ssd"
                        elif "HDD" in line.upper():
                            return "hdd"
                        elif "NVME" in line.upper() or "NVM" in line.upper():
                            return "nvme"
                return "unknown"
            else:
                # Linux: use lsblk
                result = subprocess.run(
                    ["lsblk", "-d", "-o", "rota"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.split("\n")
                    for line in lines:
                        if "0" in line:  # 0 means SSD/NVMe
                            return "ssd"
                        elif "1" in line:  # 1 means HDD
                            return "hdd"
                        
        except Exception:
            pass
        
        return "unknown"
    
    def _detect_interface_type(self, interface: str) -> str:
        """Detect network interface type."""
        interface_lower = interface.lower()
        
        if "wi" in interface_lower or "wlan" in interface_lower:
            return "wifi"
        elif "eth" in interface_lower or "en" in interface_lower:
            return "ethernet"
        elif "cellular" in interface_lower or "wwan" in interface_lower:
            return "cellular"
        
        return "unknown"
    
    def _get_windows_display(self) -> DisplayInfo:
        """Get Windows display information."""
        display_info = DisplayInfo()
        
        try:
            import ctypes
            user32 = ctypes.windll.user32
            screensize = (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))
            display_info.resolution = f"{screensize[0]}x{screensize[1]}"
            
        except Exception:
            pass
        
        return display_info
    
    def _get_macos_display(self) -> DisplayInfo:
        """Get macOS display information."""
        display_info = DisplayInfo()
        
        try:
            import subprocess
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                for line in lines:
                    if "resolution" in line.lower():
                        # Extract resolution like "1920 x 1080"
                        parts = line.split("x")
                        if len(parts) == 2:
                            width = parts[0].strip().split()[-1]
                            height = parts[1].strip().split()[0]
                            display_info.resolution = f"{width}x{height}"
                            break
                            
        except Exception:
            pass
        
        return display_info
    
    def _get_linux_display(self) -> DisplayInfo:
        """Get Linux display information."""
        display_info = DisplayInfo()
        
        try:
            import subprocess
            result = subprocess.run(
                ["xrandr"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.split("\n")
                for line in lines:
                    if "*" in line:  # Active display
                        parts = line.split()
                        if len(parts) >= 3:
                            display_info.resolution = parts[2]
                            break
                            
        except Exception:
            pass
        
        return display_info
    
    def _detect_npu(self) -> AcceleratorInfo:
        """Detect NPU (Neural Processing Unit)."""
        accelerator = AcceleratorInfo(type="npu")
        
        try:
            # Try to detect common NPU implementations
            import subprocess
            
            # Check for Intel NPU
            result = subprocess.run(
                ["lsmod"],
                capture_output=True, text=True, timeout=5
            )
            if "intel_npu" in result.stdout.lower():
                accelerator.vendor = "Intel"
                accelerator.available = True
                accelerator.model = "Intel NPU"
                
        except Exception:
            pass
        
        return accelerator
    
    def _detect_tpu(self) -> AcceleratorInfo:
        """Detect TPU (Tensor Processing Unit)."""
        accelerator = AcceleratorInfo(type="tpu")

        try:
            # Try to detect Google Coral TPU
            import subprocess
            result = subprocess.run(
                ["lsusb"],
                capture_output=True, text=True, timeout=5
            )
            if "coral" in result.stdout.lower():
                accelerator.vendor = "Google"
                accelerator.available = True
                accelerator.model = "Coral TPU"

        except Exception:
            pass

        return accelerator

    def profile_media(self) -> MediaInfo:
        """Presence-only media device detection (never activates devices)."""
        info = MediaInfo(detection_method="presence-only")
        try:
            if platform.system() == "Windows":
                return self._profile_media_windows(info)
        except Exception:
            pass
        info.limitations.append("media presence detection unavailable on this platform")
        return info

    def _profile_media_windows(self, info: MediaInfo) -> MediaInfo:
        """Windows presence detection via PnP enumeration (no activation)."""
        import subprocess

        def _ps(script: str) -> str:
            # NOTE: Get-PnpDevice may exit nonzero while still emitting
            # device names (e.g. unknown device class); callers must judge
            # by output content, not returncode.
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, timeout=15,
            )
            return result.stdout

        info.detection_method = "windows-pnp-presence-only"
        # Camera: PnP Camera/Image classes that are present (Status OK)
        try:
            out = _ps(
                "Get-PnpDevice -Class Camera,Image -ErrorAction SilentlyContinue | "
                "Where-Object {$_.Status -eq 'OK'} | "
                "Select-Object -ExpandProperty FriendlyName"
            )
            names = [line.strip() for line in out.splitlines() if line.strip()]
            info.camera_present = bool(names)
            info.video_input = bool(names)
            info.camera_state = MEDIA_HARDWARE_PRESENT if names else MEDIA_NOT_PRESENT
        except Exception:
            info.camera_state = MEDIA_PERMISSION_UNKNOWN
            info.limitations.append("camera presence query failed")
        # Audio endpoints: capture (microphone) vs render (speaker) registry keys
        try:
            out = _ps(
                "\"capture=$((Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\"
                "CurrentVersion\\MMDevices\\Audio\\Capture'));\" + "
                "\"render=$((Test-Path 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\"
                "CurrentVersion\\MMDevices\\Audio\\Render'))\""
            )
            text = out.strip().lower()
            capture = "capture=true" in text
            render = "render=true" in text
            info.microphone_present = capture
            info.audio_input = capture
            info.microphone_state = MEDIA_HARDWARE_PRESENT if capture else MEDIA_NOT_PRESENT
            info.speaker_present = render
            info.audio_output = render
            info.speaker_state = MEDIA_HARDWARE_PRESENT if render else MEDIA_NOT_PRESENT
        except Exception:
            info.limitations.append("audio endpoint presence query failed")
        return info

    def profile_package_managers(self) -> list[PackageManagerInfo]:
        """Safe package-manager detection (never installs/updates)."""
        import shutil
        managers = []
        for name, executables in (
            ("pip", ("pip", "pip3")),
            ("npm", ("npm",)),
            ("node", ("node",)),
            ("winget", ("winget",)),
            ("choco", ("choco",)),
            ("git", ("git",)),
        ):
            path = ""
            for exe in executables:
                found = shutil.which(exe)
                if found:
                    path = found
                    break
            managers.append(PackageManagerInfo(name=name, path=path, detected=bool(path)))
        return managers