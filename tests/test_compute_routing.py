"""P9: VM-B compute routing policy tests (no network, no hardware claims)."""
import unittest

from compute.providers import (
    ComputeRecord,
    ComputeRegistry,
    ComputeDecision,
    route_compute,
    STATUS_AVAILABLE,
    STATUS_SIMULATED,
    EVIDENCE_OBSERVED,
    EVIDENCE_SIMULATED,
)


def _registry() -> ComputeRegistry:
    registry = ComputeRegistry()
    for record in ComputeRegistry.default_records(ollama_reachable=False):
        registry.register(record)
    # local-cpu observed via real detection surface in production; here the
    # default record stands in with an observed label for policy tests.
    return registry


class RegistryTests(unittest.TestCase):
    def test_register_describe_roundtrip(self):
        registry = ComputeRegistry()
        registry.register(ComputeRecord(provider_id="x", kind="local-cpu",
                                        backend="cpu"))
        self.assertEqual(registry.describe("x").backend, "cpu")
        self.assertIsNone(registry.describe("missing"))

    def test_register_rejects_blank_id(self):
        with self.assertRaises(ValueError):
            ComputeRegistry().register(
                ComputeRecord(provider_id="", kind="local-cpu", backend="cpu"))

    def test_list_available_excludes_unavailable(self):
        available = {r.provider_id for r in _registry().list_available()}
        self.assertIn("local-cpu", available)
        self.assertIn("sim-qpu", available)
        self.assertIn("ternary-emu", available)
        self.assertNotIn("ollama", available)


class RoutingTests(unittest.TestCase):
    def test_private_defaults_to_local_cpu(self):
        decision = route_compute("general", privacy="local-first",
                                 registry=_registry(),
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "local-cpu")
        self.assertFalse(decision.simulated)
        self.assertFalse(decision.fallback_used)

    def test_quantum_stays_simulated(self):
        decision = route_compute("quantum", registry=_registry(),
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "sim-qpu")
        self.assertTrue(decision.simulated)

    def test_ternary_stays_simulated(self):
        decision = route_compute("bitnet", registry=_registry(),
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "ternary-emu")
        self.assertTrue(decision.simulated)

    def test_inference_falls_back_without_daemon(self):
        decision = route_compute("llm", registry=_registry(),
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "local-cpu")
        self.assertTrue(decision.fallback_used)
        self.assertEqual(decision.fallback_from, "ollama")
        self.assertFalse(decision.simulated)

    def test_preferred_provider_honored(self):
        decision = route_compute("general", registry=_registry(),
                                 preferred_provider="ternary-emu",
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "ternary-emu")
        self.assertTrue(decision.simulated)

    def test_unknown_preferred_falls_back(self):
        decision = route_compute("general", registry=_registry(),
                                 preferred_provider="nope",
                                 ollama_probe=lambda: False)
        self.assertEqual(decision.provider_id, "local-cpu")
        self.assertTrue(decision.fallback_used)

    def test_no_usable_provider_raises(self):
        from compute.providers import STATUS_UNAVAILABLE
        registry = ComputeRegistry()
        registry.register(ComputeRecord(provider_id="dark", kind="remote-gpu",
                                        backend="unknown",
                                        status=STATUS_UNAVAILABLE))
        with self.assertRaises(RuntimeError):
            route_compute("general", registry=registry,
                          ollama_probe=lambda: False)

    def test_evidence_labels_honest(self):
        records = {r.provider_id: r for r in _registry().list_available()}
        self.assertEqual(records["local-cpu"].evidence, EVIDENCE_OBSERVED)
        self.assertEqual(records["sim-qpu"].evidence, EVIDENCE_SIMULATED)
        self.assertEqual(records["sim-qpu"].status, STATUS_SIMULATED)
        self.assertIn("no quantum effects", records["sim-qpu"].note.lower())
        self.assertIn("no ternary silicon", records["ternary-emu"].note.lower())


if __name__ == "__main__":
    unittest.main()
