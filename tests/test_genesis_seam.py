"""The Bridge's service side of the Genesis seam.

The kernel client is covered in test_genesis_kernel. This covers the
Bridge's own half: that the organism is reachable, that a session and a
task become the organism's events, that the runtime snapshot carries the
organism so the interface can see it, and that a Bridge with no kernel
attached still runs every task and says the organism is not attached.
"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from genesis_kernel import GenesisKernel  # noqa: E402
from test_genesis_kernel import make_stub_host  # noqa: E402


def get(url: str, timeout: float = 20.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return None, {"error": f"{type(exc).__name__}: {exc}"}


def post(url: str, payload: dict, timeout: float = 30.0):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8", "replace"))
        except Exception:
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return None, {"error": f"{type(exc).__name__}: {exc}"}


class SeamTestCase(unittest.TestCase):
    """A Bridge on an ephemeral port, with or without the kernel."""

    with_kernel = False

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="seam_"))
        from runtime import AgentRuntime, RuntimeConfig
        from service import serve
        self.runtime = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(self.tmp)]))
        if self.with_kernel:
            self.kernel = GenesisKernel(
                make_stub_host(self.tmp), self.tmp / "state")
            self.kernel.boot()
            self.runtime.genesis_kernel = self.kernel
        self.server = serve(self.runtime, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _events(self):
        """The events the stub host recorded."""
        marker = self.tmp / "state" / "stub-state.json"
        if not marker.is_file():
            return []
        return json.loads(marker.read_text(encoding="utf-8"))


class TestTheOrganismIsReachable(SeamTestCase):
    with_kernel = True

    def test_the_genesis_route_reports_the_organism(self):
        status, body = get(f"{self.base}/v1/genesis")
        self.assertEqual(status, 200)
        self.assertTrue(body["attached"])
        self.assertTrue(body["healthy"])
        self.assertEqual(body["identity"], "genesis.entity.v1.organism.stub")

    def test_the_runtime_snapshot_carries_the_organism(self):
        """The interface reads the snapshot, so the organism has to be in it."""
        status, body = get(f"{self.base}/v1/runtime")
        self.assertEqual(status, 200)
        self.assertIn("genesis", body)
        self.assertTrue(body["genesis"]["attached"])
        self.assertEqual(body["genesis"]["identity"],
                         "genesis.entity.v1.organism.stub")

    def test_an_event_can_be_recorded_through_the_route(self):
        status, body = post(f"{self.base}/v1/genesis", {
            "action": "event", "topic": "organism.event",
            "payload": "something happened"})
        self.assertEqual(status, 200)
        self.assertTrue(body["recorded"])

    def test_a_checkpoint_can_be_asked_for(self):
        status, body = post(f"{self.base}/v1/genesis", {"action": "checkpoint"})
        self.assertEqual(status, 200)
        self.assertTrue(body["checkpointed"])

    def test_an_unknown_action_is_refused(self):
        status, _ = post(f"{self.base}/v1/genesis", {"action": "nonsense"})
        self.assertEqual(status, 400)


class TestTheOrganismObservesTheWork(SeamTestCase):
    with_kernel = True

    def test_a_session_becomes_the_organisms_event(self):
        status, body = post(f"{self.base}/v1/sessions", {
            "workspace": str(self.tmp), "mode": "build",
            "approval": "AUTO_SAFE"})
        self.assertEqual(status, 201)
        self.assertTrue(body["session_id"])
        # The organism's sequence advanced, which means it was told.
        self.assertGreater(self.kernel.summary()["calls"], 1)

    def test_a_task_becomes_the_organisms_event(self):
        _, body = post(f"{self.base}/v1/sessions", {
            "workspace": str(self.tmp), "mode": "build",
            "approval": "AUTO_SAFE"})
        session_id = body["session_id"]
        before = self.kernel.version
        status, task = post(f"{self.base}/v1/sessions/{session_id}/tasks",
                            {"text": "write a haiku to haiku.txt"})
        self.assertEqual(status, 202)
        self.assertTrue(task["task_id"])
        # The organism's version advanced, which is how it records that
        # something was observed.
        self.assertNotEqual(self.kernel.version, before)


class TestWithoutTheOrganism(SeamTestCase):
    """A Bridge with no kernel still runs everything, and says so."""

    with_kernel = False

    def test_the_genesis_route_says_it_is_not_attached(self):
        status, body = get(f"{self.base}/v1/genesis")
        self.assertEqual(status, 200)
        self.assertFalse(body["attached"])
        self.assertEqual(body["identity"], "")
        self.assertIn("not attached", body["error"])

    def test_the_runtime_snapshot_says_it_is_not_attached(self):
        status, body = get(f"{self.base}/v1/runtime")
        self.assertEqual(status, 200)
        self.assertIn("genesis", body)
        self.assertFalse(body["genesis"]["attached"])

    def test_a_session_still_works(self):
        status, body = post(f"{self.base}/v1/sessions", {
            "workspace": str(self.tmp), "mode": "build",
            "approval": "AUTO_SAFE"})
        self.assertEqual(status, 201)
        self.assertTrue(body["session_id"])

    def test_a_task_still_works(self):
        _, body = post(f"{self.base}/v1/sessions", {
            "workspace": str(self.tmp), "mode": "build",
            "approval": "AUTO_SAFE"})
        session_id = body["session_id"]
        status, task = post(f"{self.base}/v1/sessions/{session_id}/tasks",
                            {"text": "write a haiku to haiku.txt"})
        self.assertEqual(status, 202)
        self.assertTrue(task["task_id"])


if __name__ == "__main__":
    unittest.main()
