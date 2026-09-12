"""Resource orchestration tests (v0.8, synthetic fixtures only)."""
import unittest

from resources import (
    BACKEND_CONTROL_UNAVAILABLE, CODE_ANALYSIS, CPU_COMPUTE, GPU_COMPUTE,
    LANE_BACKGROUND, LANE_INTERACTIVE, MODEL_INFERENCE, TESTING,
    AdaptiveBalancer, PlacementDecision, PressureMonitor, PressureState,
    ResourceDescriptor, ResourcePool, ResourceScheduler, WorkloadClassifier,
    WorkloadDescriptor, pool_from_device_profile, remote_node_resource,
)


def _pool():
    return ResourcePool([
        ResourceDescriptor("cpu", CPU_COMPUTE, capacity=8, available=8,
                           backend="psutil", controls=["worker_count"],
                           serves=[MODEL_INFERENCE, CODE_ANALYSIS, TESTING]),
        ResourceDescriptor("gpu", GPU_COMPUTE, capacity=100, available=100,
                           backend="ollama", controls=["num_gpu"],
                           serves=[MODEL_INFERENCE]),
        ResourceDescriptor("npu", "NPU_COMPUTE", capacity=100, available=100,
                           backend="unknown",
                           controls=[BACKEND_CONTROL_UNAVAILABLE],
                           serves=[MODEL_INFERENCE]),
    ])


class PoolTests(unittest.TestCase):
    def test_compatible_never_offers_wrong_kind(self):
        pool = _pool()
        w = WorkloadDescriptor("w1", TESTING)
        ids = {r.resource_id for r in pool.compatible(w)}
        self.assertEqual(ids, {"cpu"})

    def test_backend_filter(self):
        pool = _pool()
        w = WorkloadDescriptor("w1", MODEL_INFERENCE, backend="ollama")
        ids = {r.resource_id for r in pool.compatible(w)}
        self.assertEqual(ids, {"gpu"})

    def test_pool_from_device_profile(self):
        profile = {
            "cpu": {"logical_cores": 8, "model": "Test CPU"},
            "gpu": {"vendor": "NVIDIA", "model": "Test GPU", "vram_mb": 4096},
            "memory": {"total_mb": 16384, "available_mb": 8000},
            "network": {"connected": True, "interface_type": "ethernet"},
            "accelerators": [],
            "storage": {"total_mb": 100000},
            "media": {"camera_present": False, "microphone_present": False},
        }
        pool = ResourcePool(pool_from_device_profile(profile))
        kinds = {r.kind for r in pool.compatible(WorkloadDescriptor("w", MODEL_INFERENCE))}
        self.assertIn(CPU_COMPUTE, kinds)
        self.assertIn(GPU_COMPUTE, kinds)
        gpu = pool.get("local:gpu")
        self.assertIn("num_gpu", gpu.controls)

    def test_remote_node_resource(self):
        r = remote_node_resource("desk-1")
        self.assertEqual(r.kind, "REMOTE_NODE_COMPUTE")
        self.assertIn("delegate", r.controls)


class ClassifierTests(unittest.TestCase):
    def test_classifies_coding_task(self):
        kinds = {w.kind for w in WorkloadClassifier().classify("refactor this function")}
        self.assertIn(CODE_ANALYSIS, kinds)

    def test_background_lane(self):
        ws = WorkloadClassifier().classify("reindex docs in background")
        self.assertTrue(all(w.lane == LANE_BACKGROUND for w in ws))

    def test_unknown_defaults_to_inference(self):
        ws = WorkloadClassifier().classify("zxqyblorp")
        self.assertEqual([w.kind for w in ws], [MODEL_INFERENCE])


class SchedulerTests(unittest.TestCase):
    def test_independent_workloads_parallel(self):
        ws = [WorkloadDescriptor(f"w{i}", TESTING) for i in range(3)]
        sched = ResourceScheduler()
        self.assertTrue(sched.parallelizable(ws))
        self.assertEqual(len(sched.order(ws)), 1)

    def test_write_collision_serializes(self):
        a = WorkloadDescriptor("a", TESTING, writes_files=["out.txt"])
        b = WorkloadDescriptor("b", TESTING, writes_files=["out.txt"])
        waves = ResourceScheduler().order([a, b])
        self.assertEqual(len(waves), 2)

    def test_dependencies_order(self):
        a = WorkloadDescriptor("a", TESTING)
        b = WorkloadDescriptor("b", TESTING, depends_on=["a"])
        waves = ResourceScheduler().order([b, a])
        self.assertEqual([[w.workload_id for w in wave] for wave in waves],
                         [["a"], ["b"]])


class BalancerTests(unittest.TestCase):
    def test_reliability_beats_speed(self):
        class Summary:
            def for_workload(self, kind, resource_id):
                if resource_id == "gpu":
                    return {"reliability": 0.1, "tokens_per_second": 200.0}
                return {"reliability": 1.0, "tokens_per_second": 5.0}
        bal = AdaptiveBalancer(_pool(), benchmark_summary=Summary())
        d = bal.place(WorkloadDescriptor("w", MODEL_INFERENCE))
        self.assertEqual(d.resource_id, "cpu")
        self.assertTrue(d.benchmark_evidence_used)

    def test_no_compatible_resource_defers(self):
        bal = AdaptiveBalancer(_pool())
        d = bal.place(WorkloadDescriptor("w", "VIDEO_ENCODE"))
        self.assertTrue(d.deferred)
        self.assertEqual(d.resource_id, "")

    def test_pressure_avoids_hot_resource(self):
        bal = AdaptiveBalancer(_pool())
        cool = bal.place(WorkloadDescriptor("w", MODEL_INFERENCE),
                         PressureState(cpu=0.1, gpu=0.1))
        hot_gpu = bal.place(WorkloadDescriptor("w", MODEL_INFERENCE),
                            PressureState(cpu=0.1, gpu=0.98))
        self.assertEqual(cool.resource_id, "gpu")
        self.assertNotEqual(hot_gpu.resource_id, "gpu")

    def test_owner_preference_respected(self):
        bal = AdaptiveBalancer(_pool(), owner_preferences={"preferred_resource": "cpu"})
        d = bal.place(WorkloadDescriptor("w", MODEL_INFERENCE))
        self.assertIn("owner_preferred", d.reasons)

    def test_weights_configurable(self):
        bal = AdaptiveBalancer(_pool(), weights={"compatibility": 0.0})
        self.assertEqual(bal.weights["compatibility"], 0.0)


class MonitorTests(unittest.TestCase):
    def test_pressure_response_actions(self):
        mon = PressureMonitor()
        resp = mon.pressure_response(PressureState(cpu=0.95, vram=0.9, ram=0.9))
        self.assertIn("reduce_cpu_workers", resp["actions"])
        self.assertIn("reduce_offload_or_model_size", resp["actions"])
        self.assertIn("shrink_cache", resp["actions"])

    def test_lane_reserve(self):
        mon = PressureMonitor(lane=LANE_INTERACTIVE)
        self.assertFalse(mon.headroom_ok(PressureState(cpu=0.8)))
        self.assertTrue(mon.headroom_ok(PressureState(cpu=0.1)))


if __name__ == "__main__":
    unittest.main()
