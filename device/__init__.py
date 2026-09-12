"""Device profiling and hardware detection (v0.7).

This module provides automatic device and hardware profiling:
- DeviceProfiler: Detect device type, OS, and capabilities
- HardwareProfiler: Detect CPU, GPU, RAM, accelerators
- RuntimeTuner: Automatic performance configuration
- DeviceCapabilityProfile: Normalized device representation

The runtime adapts its behavior based on the detected device capabilities.
"""
from __future__ import annotations

from device.device_profiler import DeviceProfiler
from device.hardware_profiler import HardwareProfiler
from device.runtime_tuner import RuntimeTuner
from device.device_profile import DeviceCapabilityProfile

__all__ = [
    "DeviceProfiler",
    "HardwareProfiler",
    "RuntimeTuner",
    "DeviceCapabilityProfile",
]