"""Live avatar data path: Genesis identity -> binding -> snapshot -> service.

Uses the real LocalGenesisRuntime (temp store) and real AvatarBinding.
No mocks for the projection path itself.
"""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from genesis_avatar import (AvatarBinding, AvatarUIMode, _BINDINGS,
                            binding_for, project_genesis_runtime)
from genesis_runtime import LocalGenesisRuntime
from ide_bridge import build_runtime_snapshot


def fresh_runtime(tmpdir):
    rt = LocalGenesisRuntime(Path(tmpdir) / "genesis.json")
    return rt


class TestLiveProjection(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gen_live_"))
        _BINDINGS.clear()

    def tearDown(self):
        _BINDINGS.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_genesis_id_creation_projects(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-live-1", "Genesis")
        b = AvatarBinding(genesis_id="")
        rec = project_genesis_runtime(b, g)
        self.assertTrue(rec["projected"])
        self.assertEqual(rec["genesis_id"], "g-live-1")
        self.assertEqual(b.genesis_id, "g-live-1")

    def test_identity_survives_store_reload(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-persist-1")
        g2 = LocalGenesisRuntime(self.tmp / "genesis.json")
        self.assertEqual(g2.identity.genesis_id, "g-persist-1")
        rec = project_genesis_runtime(AvatarBinding(genesis_id=""), g2)
        self.assertTrue(rec["projected"])
        self.assertEqual(rec["genesis_id"], "g-persist-1")

    def test_idle_with_no_sessions(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-idle-1")
        rec = project_genesis_runtime(AvatarBinding(genesis_id=""), g)
        self.assertEqual(rec["avatar_state"], "idle")

    def test_working_with_open_session(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-work-1")
        g.start_session("prove live wiring")
        rec = project_genesis_runtime(AvatarBinding(genesis_id=""), g)
        self.assertEqual(rec["avatar_state"], "executing")

    def test_mismatched_binding_never_overwritten(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-real-1")
        b = AvatarBinding(genesis_id="g-other-9")
        rec = project_genesis_runtime(b, g)
        self.assertFalse(rec["projected"])
        self.assertEqual(rec["reason"], "identity_mismatch")
        self.assertEqual(b.genesis_id, "g-other-9")

    def test_empty_identity_leaves_binding_untouched(self):
        g = fresh_runtime(self.tmp)  # never identified
        b = AvatarBinding(genesis_id="")
        rec = project_genesis_runtime(b, g)
        self.assertFalse(rec["projected"])
        self.assertEqual(b.genesis_id, "")

    def test_no_duplicate_bindings_per_identity(self):
        self.assertIs(binding_for("g-dup-1"), binding_for("g-dup-1"))

    def test_mode_survives_across_snapshot_calls(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-mode-1")
        snap1 = build_runtime_snapshot(None, None, g)
        self.assertEqual(snap1["avatar"]["genesis_id"], "g-mode-1")
        binding_for("g-mode-1").set_mode(AvatarUIMode.SMALL)
        snap2 = build_runtime_snapshot(None, None, g)
        self.assertEqual(snap2["avatar"]["mode"], "small")
        self.assertEqual(snap2["avatar"]["genesis_id"], "g-mode-1")

    def test_snapshot_merge_shape(self):
        g = fresh_runtime(self.tmp)
        g.identify("g-shape-1")
        snap = build_runtime_snapshot(None, None, g)
        av = snap["avatar"]
        for k in ("genesis_id", "avatar_state", "mode", "projected"):
            self.assertIn(k, av)
        self.assertTrue(av["projected"])

    def test_no_identity_keeps_task_avatar(self):
        snap = build_runtime_snapshot(None, None, None)
        self.assertNotIn("genesis_id", snap.get("avatar") or {})


class TestLiveServiceAvatar(unittest.TestCase):
    def test_runtime_route_carries_genesis_id(self):
        import socket
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        tmp = Path(tempfile.mkdtemp(prefix="gen_svc_"))
        try:
            g = LocalGenesisRuntime(tmp / "genesis.json")
            g.identify("g-svc-1")
            rt = AgentRuntime(RuntimeConfig(
                allowed_workspace_roots=[str(tmp)]))
            rt.genesis_runtime = g
            # Explicit free port: serve() maps port 0 onto cfg.port,
            # which could collide with a stale listener.
            probe = socket.socket()
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
            probe.close()
            srv = serve(rt, "127.0.0.1", port)
            self.assertEqual(srv.server_address[1], port)
            th = threading.Thread(target=srv.serve_forever, daemon=True)
            th.start()
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/v1/runtime" % port,
                        timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(body["avatar"]["genesis_id"], "g-svc-1")
                self.assertTrue(body["avatar"]["projected"])
            finally:
                srv.shutdown()
                srv.server_close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
