import unittest
from unittest.mock import patch

from device import DeviceProfiler, HardwareProfiler
from device.device_profile import DEVICE_CLASS_ANDROID, CPUInfo
from runtimes import LocalRuntimeDiscovery, RuntimeDescriptor


class DeviceRuntimeTests(unittest.TestCase):
    def test_device_profile_imports_and_aggregates_hardware(self):
        profile = DeviceProfiler().profile_with_hardware(HardwareProfiler(), True)
        self.assertTrue(profile.device_id)
        self.assertIn(profile.device_class, (
            "desktop", "laptop", "workstation", "server", "unknown",
        ))
        self.assertIsNotNone(profile.memory)
        self.assertEqual(DEVICE_CLASS_ANDROID, "android")

    def test_runtime_discovery_uses_configured_endpoint_only(self):
        discovery = LocalRuntimeDiscovery({"future-runtime": "http://127.0.0.1:1"})
        with patch.object(discovery, "_probe_openai_compatible") as probe:
            result = discovery.discover()
        self.assertEqual(result[0].runtime_id, "future-runtime")
        probe.assert_called_once()

    def test_runtime_metadata_is_retained_when_endpoint_goes_offline(self):
        """Test that a previously HEALTHY runtime becomes OFFLINE with retained metadata when it goes offline."""
        discovery = LocalRuntimeDiscovery({"ollama": "http://127.0.0.1:1"})
        
        # First discovery: simulate successful Ollama probe
        def mock_successful_ollama(descriptor):
            descriptor.models = [{"name": "test-model", "size": 1000}]
            descriptor.status = "HEALTHY"
        
        with patch.object(discovery, "_probe_ollama", side_effect=mock_successful_ollama):
            first = discovery.discover()[0]
        
        self.assertEqual(first.status, "HEALTHY")
        self.assertEqual(first.protocol, "OLLAMA_COMPATIBLE")
        self.assertEqual(len(first.models), 1)
        
        # Second discovery: simulate endpoint gone offline
        with patch.object(discovery, "_probe_ollama", side_effect=Exception("Connection refused")):
            with patch.object(discovery, "_probe_openai_compatible", side_effect=Exception("Connection refused")):
                with patch.object(discovery, "_probe_agent_bridge_native", side_effect=Exception("Connection refused")):
                    second = discovery.discover()[0]
        
        # Should be OFFLINE with retained metadata
        self.assertEqual(second.status, "OFFLINE")
        self.assertEqual(second.protocol, "UNKNOWN")
        self.assertEqual(second.runtime_id, "ollama")
        self.assertEqual(len(second.models), 1)  # Metadata retained

    def test_ollama_protocol_detection(self):
        """Test that Ollama-compatible endpoints are correctly detected."""
        discovery = LocalRuntimeDiscovery({"ollama": "http://127.0.0.1:11434"})
        result = discovery.discover()[0]
        self.assertEqual(result.protocol, "OLLAMA_COMPATIBLE")
        self.assertEqual(result.status, "HEALTHY")

    def test_unknown_runtime_gets_adapter_required(self):
        """Test that unknown runtimes with no working protocol get ADAPTER_REQUIRED."""
        discovery = LocalRuntimeDiscovery({"mystery-runtime": "http://127.0.0.1:9999"})
        result = discovery.discover()[0]
        self.assertEqual(result.status, "ADAPTER_REQUIRED")
        self.assertEqual(result.protocol, "UNKNOWN")
        self.assertTrue(len(result.limitations) > 0)

    def test_new_unknown_runtime_starts_as_unavailable(self):
        """Test that a runtime with no previous state and no probe response gets ADAPTER_REQUIRED."""
        discovery = LocalRuntimeDiscovery({"brand-new-runtime": "http://127.0.0.1:9999"})
        with patch.object(discovery, "_probe_ollama", side_effect=Exception("Connection refused")):
            with patch.object(discovery, "_probe_openai_compatible", side_effect=Exception("Connection refused")):
                with patch.object(discovery, "_probe_agent_bridge_native", side_effect=Exception("Connection refused")):
                    result = discovery.discover()[0]
        self.assertEqual(result.status, "ADAPTER_REQUIRED")

    def test_device_profile_idempotence(self):
        """Test that repeated profiling produces consistent results without duplicate capabilities."""
        profiler = DeviceProfiler()
        hw = HardwareProfiler()
        
        profile1 = profiler.profile_with_hardware(hw, force_refresh=True)
        profile2 = profiler.profile_with_hardware(hw, force_refresh=True)
        
        # Core fields should be identical
        self.assertEqual(profile1.device_id, profile2.device_id)
        self.assertEqual(profile1.device_class, profile2.device_class)
        self.assertEqual(profile1.os, profile2.os)
        self.assertEqual(profile1.runtime_role, profile2.runtime_role)
        
        # Capabilities should not be duplicated
        self.assertEqual(len(profile1.capabilities), len(set(profile1.capabilities)))
        self.assertEqual(len(profile2.capabilities), len(set(profile2.capabilities)))
        self.assertEqual(profile1.capabilities, profile2.capabilities)
        
        # Hardware fields should match
        self.assertEqual(profile1.cpu.physical_cores, profile2.cpu.physical_cores)
        self.assertEqual(profile1.cpu.logical_cores, profile2.cpu.logical_cores)
        self.assertEqual(profile1.memory.total_mb, profile2.memory.total_mb)
        self.assertEqual(profile1.gpu.vram_mb, profile2.gpu.vram_mb)

    def test_cpu_field_correctness(self):
        """Test that CPU field uses 'model' not 'processor' and has correct types."""
        profiler = DeviceProfiler()
        hw = HardwareProfiler()
        profile = profiler.profile_with_hardware(hw, force_refresh=True)
        
        cpu = profile.cpu
        self.assertIsInstance(cpu, CPUInfo)
        self.assertIsInstance(cpu.vendor, str)
        self.assertIsInstance(cpu.model, str)
        self.assertIsInstance(cpu.architecture, str)
        self.assertIsInstance(cpu.physical_cores, int)
        self.assertIsInstance(cpu.logical_cores, int)
        self.assertIsInstance(cpu.frequency_mhz, int)
        
        # Should have meaningful values on this machine
        self.assertGreater(cpu.physical_cores, 0)
        self.assertGreater(cpu.logical_cores, 0)
        self.assertGreaterEqual(cpu.logical_cores, cpu.physical_cores)
        self.assertIn(cpu.vendor, ("Intel", "AMD", "ARM", "Apple", ""))

    def test_device_class_and_runtime_role(self):
        """Test that device_class and runtime_role are determined from evidence."""
        profiler = DeviceProfiler()
        hw = HardwareProfiler()
        profile = profiler.profile_with_hardware(hw, force_refresh=True)
        
        self.assertIn(profile.device_class, (
            "desktop", "laptop", "workstation", "server", "unknown",
            "phone", "tablet", "ipad", "android", "embedded", "iot",
            "smartwatch", "smart_ring", "smart_glasses", "smart_tv"
        ))
        self.assertIn(profile.runtime_role, (
            "FULL_RUNTIME", "CONSTRAINED_RUNTIME", "CLIENT_NODE",
            "DELEGATION_NODE", "SENSOR_NODE", "DISPLAY_NODE"
        ))
        
        # On this machine: desktop with 16GB RAM -> role FULL_RUNTIME,
        # resource class CONSTRAINED_RUNTIME (separate axes).
        self.assertEqual(profile.device_class, "desktop")
        self.assertEqual(profile.runtime_role, "FULL_RUNTIME")
        self.assertEqual(profile.resource_class, "CONSTRAINED_RUNTIME")


if __name__ == "__main__":
    unittest.main()
