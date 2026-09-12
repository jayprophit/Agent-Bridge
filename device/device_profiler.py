"""DeviceProfiler (v0.7). Device type, OS, and capability detection.

Detects high-level device characteristics:
- Device class (desktop, mobile, etc.)
- Operating system and version
- Platform capabilities
- Form factor characteristics
"""
from __future__ import annotations

import os
import platform
import time
from typing import Any

from device.device_profile import (
    DEVICE_CLASS_ANDROID, DEVICE_CLASS_DESKTOP, DEVICE_CLASS_EMBEDDED,
    DEVICE_CLASS_IPAD, DEVICE_CLASS_IOT, DEVICE_CLASS_LAPTOP,
    DEVICE_CLASS_PHONE, DEVICE_CLASS_SERVER, DEVICE_CLASS_SMART_GLASSES,
    DEVICE_CLASS_SMART_RING, DEVICE_CLASS_SMART_TV, DEVICE_CLASS_SMARTWATCH,
    DEVICE_CLASS_TABLET, DEVICE_CLASS_UNKNOWN, DEVICE_CLASS_WORKSTATION,
    OS_ANDROID, OS_CHROMEOS, OS_IOS, OS_IPADOS, OS_LINUX, OS_MACOS,
    OS_TVOS, OS_UNKNOWN, OS_WATCHOS, OS_WINDOWS, DeviceCapabilityProfile,
    RESOURCE_CLASS_CONSTRAINED_RUNTIME, RESOURCE_CLASS_FULL_RUNTIME,
    RUNTIME_ROLE_FULL_RUNTIME, RUNTIME_ROLE_CONSTRAINED_RUNTIME,
    RUNTIME_ROLE_CLIENT_NODE, RUNTIME_ROLE_DELEGATION_NODE,
    RUNTIME_ROLE_SENSOR_NODE, RUNTIME_ROLE_DISPLAY_NODE
)


class DeviceProfiler:
    """High-level device profiling."""
    
    def __init__(self):
        self._cached_profile: DeviceCapabilityProfile | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 300.0  # 5 minutes cache
    
    def profile(self, force_refresh: bool = False) -> DeviceCapabilityProfile:
        """Generate device capability profile.
        
        Args:
            force_refresh: Force re-profiling even if cached.
            
        Returns:
            DeviceCapabilityProfile with detected capabilities.
        """
        now = time.monotonic()
        
        if not force_refresh and self._cached_profile:
            if now - self._cache_time < self._cache_ttl:
                return self._cached_profile
        
        # Generate new profile
        profile = DeviceCapabilityProfile()
        profile.device_id = self._generate_device_id()
        profile.os = self._detect_os()
        profile.os_version = self._detect_os_version()
        profile.architecture = self._detect_architecture()
        profile.device_class = self._detect_device_class()
        profile.timestamp = now
        
        # Detect capabilities
        profile.local_inference = self._detect_local_inference_capability()
        profile.browser_available = self._detect_browser()
        profile.filesystem_write = self._detect_filesystem_write()
        profile.background_agent = self._detect_background_agent()
        profile.admin_possible = self._detect_admin_possible()
        
        # Cache the profile
        self._cached_profile = profile
        self._cache_time = now
        
        return profile

    def profile_with_hardware(self, hardware_profiler, force_refresh: bool = False):
        """Return one normalized profile populated with detailed hardware data."""
        from device.device_profile import (
            RUNTIME_ROLE_FULL_RUNTIME, RUNTIME_ROLE_CONSTRAINED_RUNTIME,
            RUNTIME_ROLE_CLIENT_NODE, RUNTIME_ROLE_DELEGATION_NODE,
            RUNTIME_ROLE_SENSOR_NODE, RUNTIME_ROLE_DISPLAY_NODE
        )
        profile = self.profile(force_refresh)
        profile.cpu = hardware_profiler.profile_cpu(force_refresh)
        profile.gpu = hardware_profiler.profile_gpu(force_refresh)
        profile.memory = hardware_profiler.profile_memory(force_refresh)
        profile.storage = hardware_profiler.profile_storage()
        profile.battery = hardware_profiler.profile_battery()
        profile.network = hardware_profiler.profile_network()
        profile.display = hardware_profiler.profile_display()
        profile.accelerators = hardware_profiler.profile_accelerators()
        profile.media = hardware_profiler.profile_media()
        profile.package_managers = hardware_profiler.profile_package_managers()
        profile.local_inference = (
            profile.local_inference or profile.memory.total_mb >= 4096
        )
        self._add_capability(profile, "battery", profile.battery.present)
        self._add_capability(profile, "gpu", bool(profile.gpu.vendor))
        self._add_capability(profile, "network", profile.network.connected)
        self._add_capability(profile, "camera", profile.media.camera_present)
        self._add_capability(profile, "microphone", profile.media.microphone_present)
        self._add_capability(profile, "speaker", profile.media.speaker_present)
        
        # Determine runtime role (node-function axis) and resource class
        # (hardware-capacity axis) from hardware evidence. The two axes are
        # independent: e.g. CONSTRAINED_RUNTIME hardware can serve a
        # DELEGATION_NODE/FULL_RUNTIME role.
        profile.runtime_role = self._determine_runtime_role(profile)
        profile.resource_class = self._determine_resource_class(profile)

        return profile
    
    @staticmethod
    def _add_capability(profile, capability: str, present: bool) -> None:
        """Idempotent capability append (safe across repeated refreshes)."""
        if present and capability not in profile.capabilities:
            profile.capabilities.append(capability)
        if not present and capability in profile.capabilities:
            profile.capabilities.remove(capability)

    def _determine_runtime_role(self, profile) -> str:
        """Determine runtime role from hardware evidence."""
        # Sensor node: very low resource, no GPU, minimal RAM
        if (profile.memory.total_mb < 2048 and  # < 2GB RAM
            not profile.gpu.vendor and
            profile.device_class in (DEVICE_CLASS_EMBEDDED, DEVICE_CLASS_IOT, DEVICE_CLASS_SMARTWATCH, DEVICE_CLASS_SMART_RING)):
            return RUNTIME_ROLE_SENSOR_NODE
        
        # Display node: has display but limited compute
        if (profile.device_class in (DEVICE_CLASS_SMART_TV, DEVICE_CLASS_SMART_GLASSES) and
            profile.memory.total_mb < 8192):
            return RUNTIME_ROLE_DISPLAY_NODE
        
        # Client node: mobile/low resource, relies on delegation
        if (profile.device_class in (DEVICE_CLASS_PHONE, DEVICE_CLASS_TABLET, DEVICE_CLASS_IPAD, DEVICE_CLASS_ANDROID) and
            profile.memory.total_mb < 8192):
            return RUNTIME_ROLE_CLIENT_NODE
        
        # Delegation node: server/workstation with high resources for offloading
        if (profile.device_class in (DEVICE_CLASS_SERVER, DEVICE_CLASS_WORKSTATION) and
            profile.memory.total_mb >= 32768 and
            profile.gpu.vendor and profile.gpu.vram_mb >= 8192):
            return RUNTIME_ROLE_DELEGATION_NODE
        
        # Desktop-class devices serve the full runtime role; hardware
        # limits live on the orthogonal resource_class axis.
        if profile.device_class in (DEVICE_CLASS_LAPTOP, DEVICE_CLASS_DESKTOP,
                                    DEVICE_CLASS_SERVER, DEVICE_CLASS_WORKSTATION):
            return RUNTIME_ROLE_FULL_RUNTIME

        # Full runtime: capable desktop/workstation/server with sufficient resources
        return RUNTIME_ROLE_FULL_RUNTIME

    @staticmethod
    def _determine_resource_class(profile) -> str:
        """Determine resource class from hardware capacity evidence."""
        total_ram = profile.memory.total_mb or 0
        vram = profile.gpu.vram_mb or 0
        if total_ram < 16384 or not profile.gpu.vendor or vram < 4096:
            return RESOURCE_CLASS_CONSTRAINED_RUNTIME
        return RESOURCE_CLASS_FULL_RUNTIME
    
    def _generate_device_id(self) -> str:
        """Generate a unique device identifier."""
        import uuid
        # Use platform-specific identifiers
        system = platform.system()
        node = platform.node()
        machine = platform.machine()
        
        # Create a hash of system info
        identifier = f"{system}-{node}-{machine}"
        import hashlib
        hash_obj = hashlib.sha256(identifier.encode())
        return f"device-{hash_obj.hexdigest()[:12]}"
    
    def _detect_os(self) -> str:
        """Detect operating system family."""
        system = platform.system().lower()
        
        if system == "windows":
            return OS_WINDOWS
        elif system == "darwin":
            # Distinguish macOS vs iOS/iPadOS based on platform
            if platform.machine().startswith("iPad"):
                return OS_IPADOS
            elif platform.machine().startswith("iPhone"):
                return OS_IOS
            else:
                return OS_MACOS
        elif system == "linux":
            # Check for ChromeOS, Android, etc.
            try:
                with open("/etc/os-release") as f:
                    content = f.read().lower()
                    if "chrome os" in content or "chromium os" in content:
                        return OS_CHROMEOS
                    elif "android" in content:
                        return OS_ANDROID
            except Exception:
                pass
            return OS_LINUX
        else:
            return OS_UNKNOWN
    
    def _detect_os_version(self) -> str:
        """Detect operating system version."""
        try:
            return platform.version()
        except Exception:
            return ""
    
    def _detect_architecture(self) -> str:
        """Detect system architecture."""
        try:
            return platform.machine().lower()
        except Exception:
            return ""
    
    def _detect_device_class(self) -> str:
        """Detect device class based on platform characteristics and hardware evidence."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        # Mobile detection
        if system == "darwin":
            if machine.startswith("iphone"):
                return DEVICE_CLASS_PHONE
            elif machine.startswith("ipad"):
                return DEVICE_CLASS_IPAD
            elif machine.startswith("watch"):
                return DEVICE_CLASS_SMARTWATCH
        
        if system == "linux":
            # Check for Android
            try:
                with open("/etc/os-release") as f:
                    content = f.read().lower()
                    if "android" in content:
                        return DEVICE_CLASS_ANDROID
            except Exception:
                pass
        
        # Windows/Linux desktop classification based on hardware evidence
        if system in ("windows", "linux"):
            # Check for battery to distinguish laptop vs desktop
            has_battery = False
            try:
                import psutil
                battery = psutil.sensors_battery()
                has_battery = battery is not None
            except Exception:
                pass
            
            # Get memory for workstation/server classification
            total_ram_mb = 0
            try:
                import psutil
                total_ram_mb = psutil.virtual_memory().total // (1024 * 1024)
            except Exception:
                pass
            
            # Get CPU info for server-class detection
            cpu_cores = 0
            try:
                import psutil
                cpu_cores = psutil.cpu_count(logical=True) or 0
            except Exception:
                pass
            
            # Check for server indicators
            is_server = False
            if system == "windows":
                # Check Windows edition
                try:
                    import subprocess
                    result = subprocess.run(
                        ["wmic", "os", "get", "Caption"],
                        capture_output=True, text=True, timeout=5
                    )
                    caption = result.stdout.lower()
                    if "server" in caption:
                        is_server = True
                except Exception:
                    pass
            elif system == "linux":
                # Check for server indicators
                try:
                    with open("/etc/os-release") as f:
                        content = f.read().lower()
                        if "server" in content:
                            is_server = True
                except Exception:
                    pass
            
            if is_server or (cpu_cores >= 16 and total_ram_mb >= 65536):  # 64GB+ RAM, 16+ cores
                return DEVICE_CLASS_SERVER
            
            # Workstation: high-end desktop with lots of RAM/cores
            if total_ram_mb >= 32768 and cpu_cores >= 8:  # 32GB+ RAM, 8+ cores
                return DEVICE_CLASS_WORKSTATION
            
            # Laptop: has battery
            if has_battery:
                return DEVICE_CLASS_LAPTOP
            
            # Default to desktop
            return DEVICE_CLASS_DESKTOP
        
        if system == "linux":
            # Check for embedded indicators
            try:
                with open("/proc/cmdline") as f:
                    cmdline = f.read().lower()
                    if "embedded" in cmdline or "rpi" in cmdline:
                        return DEVICE_CLASS_EMBEDDED
            except Exception:
                pass
            return DEVICE_CLASS_DESKTOP
        
        # Default to unknown
        return DEVICE_CLASS_UNKNOWN
    
    def _detect_local_inference_capability(self) -> bool:
        """Detect if device can run local AI inference."""
        # Basic check: sufficient RAM and compatible architecture
        try:
            import psutil
            mem_mb = psutil.virtual_memory().total // (1024 * 1024)
            return mem_mb >= 4000  # Minimum 4GB RAM
        except Exception:
            # Conservative default: assume no local inference
            return False
    
    def _detect_browser(self) -> bool:
        """Detect if browser is available."""
        # Check for common browser executables in PATH
        import shutil
        
        browsers = [
            "chrome", "chromium", "firefox", "edge", "safari",
            "google-chrome", "microsoft-edge", "msedge"
        ]
        
        for browser in browsers:
            if shutil.which(browser):
                return True
        
        # Check common Windows installation paths
        if platform.system() == "Windows":
            windows_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            ]
            # Also check user-local AppData
            local_appdata = os.environ.get("LOCALAPPDATA", "")
            if local_appdata:
                windows_paths.extend([
                    os.path.join(local_appdata, r"Google\Chrome\Application\chrome.exe"),
                    os.path.join(local_appdata, r"Microsoft\Edge\Application\msedge.exe"),
                ])
            
            for path in windows_paths:
                if os.path.exists(path):
                    return True
        
        return False
    
    def _detect_filesystem_write(self) -> bool:
        """Detect if filesystem write is available."""
        # Try to write a temp file
        import tempfile
        import os
        
        try:
            with tempfile.NamedTemporaryFile(delete=True) as f:
                f.write(b"test")
                return True
        except Exception:
            return False
    
    def _detect_background_agent(self) -> bool:
        """Detect if background agent execution is possible."""
        # Desktop systems typically support background execution
        system = platform.system().lower()
        
        if system in ("windows", "darwin", "linux"):
            return True
        
        # Mobile systems have restrictions
        if system in ("android", "ios"):
            return False
        
        return False
    
    def _detect_admin_possible(self) -> bool:
        """Detect if administrator/elevation is possible."""
        system = platform.system().lower()
        
        if system == "windows":
            # Check if running as admin
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                return False
        
        if system == "darwin" or system == "linux":
            # Check if running as root
            try:
                return os.geteuid() == 0
            except Exception:
                return False
        
        return False
    
    def get_cached_profile(self) -> DeviceCapabilityProfile | None:
        """Get cached profile if available."""
        if self._cached_profile and time.monotonic() - self._cache_time < self._cache_ttl:
            return self._cached_profile
        return None
    
    def clear_cache(self) -> None:
        """Clear cached profile."""
        self._cached_profile = None
        self._cache_time = 0.0