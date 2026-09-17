"""v0.9.0 model lifecycle tests (mocked providers; no downloads)."""
import unittest

from model_lifecycle import (
    BenchmarkResult,
    CapabilityProfile,
    FilesystemDiscovery,
    HotModelPool,
    ModelBenchmarkManager,
    ModelCapabilityProfiler,
    ModelLifecycleManager,
    ModelPlacementEngine,
    ModelRecord,
    ModelRegistry,
    ModelRouter,
    ModelState,
    ModelStatus,
    OllamaDiscovery,
    SizeClass,
    size_class_for_params,
)


def _rec(mid, params=3.0, caps=None, status=ModelStatus.EXPERIMENTAL):
    r = ModelRecord(model_id=mid, provider="ollama", family=mid.split(":")[0],
                    parameters_b=params, status=status)
    for k, v in (caps or {}).items():
        r.capabilities.scores[k] = v
    return r


class FakeOllama:
    def __init__(self, tags, shows=None):
        self._tags = tags
        self._shows = shows or {}

    def __call__(self, url, payload=None, timeout=15.0):
        if url.endswith("/api/tags"):
            return {"models": self._tags}
        if url.endswith("/api/show"):
            return self._shows.get((payload or {}).get("model"), {})
        raise AssertionError(url)


class TestRegistrySizes(unittest.TestCase):
    def test_size_classes(self):
        self.assertEqual(size_class_for_params(0.3), SizeClass.NANO)
        self.assertEqual(size_class_for_params(0.8), SizeClass.MICRO)
        self.assertEqual(size_class_for_params(1.7), SizeClass.MINI)
        self.assertEqual(size_class_for_params(3.0), SizeClass.SMALL)
        self.assertEqual(size_class_for_params(8.0), SizeClass.MEDIUM)
        self.assertEqual(size_class_for_params(32.0), SizeClass.LARGE)
        self.assertEqual(size_class_for_params(70.0), SizeClass.XL)
        self.assertEqual(size_class_for_params(400.0), SizeClass.VERY_LARGE)

    def test_registry_list_sorted(self):
        reg = ModelRegistry()
        reg.register(_rec("b:1"))
        reg.register(_rec("a:1"))
        self.assertEqual([m.model_id for m in reg.list()], ["a:1", "b:1"])


class TestDiscovery(unittest.TestCase):
    def test_ollama_list_show(self):
        disc = OllamaDiscovery(fetcher=FakeOllama(
            [{"name": "qwen:3b"}], {"qwen:3b": {"details": {"family": "qwen"}}}))
        self.assertEqual(disc.list_models()[0]["name"], "qwen:3b")
        self.assertEqual(disc.show("qwen:3b")["details"]["family"], "qwen")

    def test_ollama_down_returns_empty(self):
        def boom(url, payload=None, timeout=15.0):
            raise ConnectionError("down")
        self.assertEqual(OllamaDiscovery(fetcher=boom).list_models(), [])
        self.assertEqual(OllamaDiscovery(fetcher=boom).show("x"), {})

    def test_filesystem_scan_tmp(self):
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp(prefix="v090_mod_"))
        (tmp / "m.gguf").write_bytes(b"0" * 100)
        (tmp / "notes.txt").write_text("hi")
        found = FilesystemDiscovery.scan(tmp)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["path"].endswith("m.gguf"))
        self.assertFalse(FilesystemDiscovery.scan(tmp / "nope"))


class TestProfilerBenchmark(unittest.TestCase):
    def fake_gen(self, model, prompt, options=None, timeout=120.0):
        if "JSON" in prompt:
            return {"ok": True, "text": '{"a":1}', "eval_count": 6,
                    "eval_duration_ns": 3_000_000_000}
        return {"ok": True, "text": "OK", "eval_count": 2,
                "eval_duration_ns": 1_000_000_000}

    def test_ping_and_json(self):
        prof = ModelCapabilityProfiler(generate=self.fake_gen)
        ping = prof.quick_ping("m")
        self.assertTrue(ping.ok)
        self.assertEqual(ping.tokens_per_sec, 2.0)
        js = prof.json_probe("m")
        self.assertTrue(js.ok)

    def test_json_failure_recorded(self):
        prof = ModelCapabilityProfiler(
            generate=lambda *a, **k: {"ok": True, "text": "not json"})
        self.assertFalse(prof.json_probe("m").ok)

    def test_benchmark_manager_appends(self):
        mgr = ModelBenchmarkManager(ModelCapabilityProfiler(generate=self.fake_gen))
        rec = _rec("m")
        mgr.benchmark(rec)
        self.assertEqual(len(rec.benchmarks), 2)
        self.assertGreater(rec.last_benchmark, 0)


class TestPlacementRouterPool(unittest.TestCase):
    def test_router_prefers_capable_small(self):
        reg = ModelRegistry()
        reg.register(_rec("big:8b", 8.0, {"coding": True}))
        reg.register(_rec("small:3b", 3.0, {"coding": True}))
        out = ModelRouter(reg).route({"capabilities": ["coding"]},
                                     {"ram_free_gb": 6})
        self.assertEqual(out["model"], "small:3b")

    def test_router_skips_broken(self):
        reg = ModelRegistry()
        reg.register(_rec("bad:3b", 3.0, {"coding": True}, ModelStatus.BROKEN))
        reg.register(_rec("good:3b", 3.0, {"coding": True}))
        out = ModelRouter(reg).route({"capabilities": ["coding"]},
                                     {"ram_free_gb": 6})
        self.assertEqual(out["model"], "good:3b")

    def test_router_override(self):
        reg = ModelRegistry()
        reg.register(_rec("a:1b", 1.0))
        out = ModelRouter(reg).route({}, {"ram_free_gb": 6}, override="a:1b")
        self.assertTrue(out["override"])
        bad = ModelRouter(reg).route({}, {}, override="nope")
        self.assertIn("error", bad)

    def test_remote_when_insufficient(self):
        eng = ModelPlacementEngine()
        rec = _rec("huge:70b", 70.0)
        self.assertEqual(eng.place(rec, {}, {"ram_free_gb": 6,
                                             "remote_available": True}),
                         "REMOTE_SERVER")

    def test_hot_pool_budget(self):
        pool = HotModelPool(ram_budget_gb=4.0)
        pool.touch(_rec("a", 3.0))
        pool.touch(_rec("b", 3.0))
        # budget exceeded -> LRU evicted, only newest resident
        self.assertEqual(pool.resident(), ["b"])


class TestLifecycle(unittest.TestCase):
    def test_duplicates_and_retirement(self):
        reg = ModelRegistry()
        r1 = _rec("qwen:3b", 3.0)
        r1.family = "qwen"
        r2 = _rec("qwen:8b", 8.0)
        r2.family = "qwen"
        bad = _rec("old:1b", 1.0, status=ModelStatus.BROKEN)
        for r in (r1, r2, bad):
            reg.register(r)
        mgr = ModelLifecycleManager()
        dups = mgr.classify_duplicates(reg)
        self.assertIn(["qwen:3b", "qwen:8b"], dups)
        plan = mgr.retirement_plan(reg)
        self.assertEqual(len(plan), 1)
        # With MODEL_RETIREMENT_AUTO_APPROVED = TRUE, BROKEN models are auto-removed
        self.assertEqual(plan[0]["action"], "AUTO_REMOVED")

    def test_default_set_evidence_first(self):
        reg = ModelRegistry()
        reg.register(_rec("uncapped:3b", 3.0))  # untested coding
        reg.register(_rec("proven:3b", 3.0, {"coding": True}))
        picks = ModelLifecycleManager.default_set(reg)
        self.assertEqual(picks.get("coding"), "proven:3b")


if __name__ == "__main__":
    unittest.main()
