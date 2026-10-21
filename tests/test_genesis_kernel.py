"""The Bridge's seam to the Genesis runtime host.

Genesis is the organism: identity, memory, state and the causal runtime.
Until now the C++ kernel that carries it was built, tested and never run
by anything, while the Bridge's "Genesis runtime" was a Python store of
references. These tests cover the seam.

Two layers, because there are two different things to prove:

  - The client's contract, against a stub host that behaves the way the
    real one does. This always runs.
  - The seam against the real kernel, when it has been built. This is
    skipped when the binary is not there, and it is skipped loudly, not
    silently passed.
"""
import os
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from genesis_kernel import (GenesisKernel, KernelResult,  # noqa: E402
                            parse_fields, TOPIC_EVENT)

# The real kernel, when this machine has built it.
_REAL_HOST = None
for _candidate in (
    ROOT.parent / "Aetherius-OS" / "kernel" / "Genesis" / "build"
    / "genesis_runtime_host.exe",
    ROOT / "build" / "genesis_runtime_host.exe",
):
    if _candidate.is_file():
        _REAL_HOST = _candidate
        break
if _REAL_HOST is None:
    for _candidate in (ROOT.parent / "Aetherius-OS" / "kernel" / "Genesis"
                       / "build").glob("genesis_runtime_host*"):
        if _candidate.is_file():
            _REAL_HOST = _candidate
            break


STUB_HOST = textwrap.dedent("""\
    #!/usr/bin/env python3
    \"\"\"A stand-in for the Genesis runtime host.\"\"\"
    import json
    import os
    import sys

    args = sys.argv[1:]
    verb = ""
    root = ".genesis-kernel"
    topic = "organism.event"
    payload = ""
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--boot", "--event", "--checkpoint", "--status", "--rollback",
                 "--self-test"):
            verb = a
        elif a == "--data-root" and i + 1 < len(args):
            i += 1
            root = args[i]
        elif a == "--topic" and i + 1 < len(args):
            i += 1
            topic = args[i]
        elif a == "--payload" and i + 1 < len(args):
            i += 1
            payload = args[i]
        i += 1

    marker = os.path.join(root, "stub-state.json")
    state = {"identity": "", "version": "v0", "seq": 1, "state": "boot"}
    if os.path.isfile(marker):
        state.update(json.load(open(marker)))

    def save():
        os.makedirs(root, exist_ok=True)
        json.dump(state, open(marker, "w"))

    if verb == "--self-test":
        print("self-test ok identity=genesis.entity.v1.organism.stub")
    elif verb == "--boot":
        if state["identity"]:
            print("already booted identity=%s state=%s" % (
                state["identity"], state["state"]))
        else:
            state["identity"] = "genesis.entity.v1.organism.stub"
            state["version"] = "v1"
            state["state"] = "ready"
            save()
            print("booted identity=%s version=%s" % (
                state["identity"], state["version"]))
    elif verb == "--event":
        if topic != "organism.event":
            print("genesis_runtime_host: transition rejected: no transition "
                  "rule matches the current state and event topic",
                  file=sys.stderr)
            sys.exit(1)
        state["seq"] += 1
        state["version"] = "v%d" % state["seq"]
        save()
        print("event=evt-%d seq=%d state=ready observed=1 "
              "contained_failures=0 version=%s" % (
                  state["seq"], state["seq"], state["version"]))
    elif verb in ("--checkpoint", "--status"):
        print("checkpoint ok identity=%s version=%s state=%s "
              "next_sequence=%d registry=abc123 memory=def456" % (
                  state["identity"], state["version"], state["state"],
                  state["seq"] + 1))
    elif verb == "--rollback":
        print("rolled back to v1 as v2 identity=%s audit=evt-2" % (
            state["identity"]))
    sys.exit(0)
""")


def make_stub_host(directory: Path) -> list[str]:
    """Write the stub host and the command that runs it.

    The command is a list, because a host that needs an interpreter is
    a host, and the client should not care which.
    """
    path = directory / "stub_host.py"
    path.write_text(STUB_HOST, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
    return [sys.executable, str(path)]


class TestFieldParsing(unittest.TestCase):
    def test_the_pairs_are_read(self):
        fields = parse_fields(
            "event=evt-2 seq=2 state=ready observed=1 version=v2")
        self.assertEqual(fields["event"], "evt-2")
        self.assertEqual(fields["seq"], "2")
        self.assertEqual(fields["state"], "ready")

    def test_a_line_without_pairs_gives_nothing(self):
        self.assertEqual(parse_fields("genesis_runtime_host: failed"), {})


class TestClientAgainstTheStub(unittest.TestCase):
    """The client's contract, against a host that behaves like the real one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kernel_stub_"))
        self.host = make_stub_host(self.tmp)
        self.kernel = GenesisKernel(self.host, self.tmp / "state")

    def test_the_host_is_found(self):
        self.assertTrue(self.kernel.available())

    def test_boot_reads_the_identity(self):
        result = self.kernel.boot("some/route")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.identity, "genesis.entity.v1.organism.stub")
        self.assertEqual(result.version, "v1")

    def test_an_event_advances_the_organism(self):
        self.kernel.boot()
        result = self.kernel.event(TOPIC_EVENT, "a task completed")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.fields["seq"], "2")
        self.assertEqual(result.version, "v2")

    def test_a_refused_topic_is_reported_not_swallowed(self):
        """The state machine is strict, and a refusal is a fact."""
        self.kernel.boot()
        result = self.kernel.event("organism.not-a-topic", "x")
        self.assertFalse(result.ok)
        self.assertIn("transition rejected", result.error)
        self.assertEqual(self.kernel.failures, 1)

    def test_a_refusal_does_not_hide_the_organism(self):
        """One refused event does not make the organism unreadable."""
        self.kernel.boot()
        self.kernel.event("organism.not-a-topic", "x")
        summary = self.kernel.summary()
        self.assertTrue(summary["attached"])
        self.assertFalse(summary["healthy"])
        self.assertEqual(summary["identity"], "genesis.entity.v1.organism.stub")
        self.assertIn("transition rejected", summary["error"])

    def test_status_reads_the_state(self):
        self.kernel.boot()
        result = self.kernel.status()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.state, "ready")
        self.assertEqual(result.fields["next_sequence"], "2")

    def test_the_identity_survives_a_model_route_change(self):
        """Identity comes from the organism, never from the model route."""
        self.kernel.boot("route-a")
        first = self.kernel.identity
        self.kernel.boot("route-b")
        self.assertEqual(self.kernel.identity, first)

    def test_the_data_root_is_created(self):
        kernel = GenesisKernel(self.host, self.tmp / "made" / "up")
        result = kernel.boot()
        self.assertTrue(result.ok, result.error)
        self.assertTrue((self.tmp / "made" / "up").is_dir())


class TestClientWithoutAKernel(unittest.TestCase):
    """A Bridge with no kernel must still work, and must say so."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kernel_absent_"))

    def test_a_missing_host_is_not_available(self):
        kernel = GenesisKernel(self.tmp / "not-here.exe", self.tmp / "state")
        self.assertFalse(kernel.available())

    def test_a_missing_host_is_reported_honestly(self):
        kernel = GenesisKernel(self.tmp / "not-here.exe", self.tmp / "state")
        result = kernel.status()
        self.assertFalse(result.ok)
        self.assertIn("could not be run", result.error)

    def test_the_summary_says_it_is_not_attached(self):
        kernel = GenesisKernel(self.tmp / "not-here.exe", self.tmp / "state")
        summary = kernel.summary()
        self.assertFalse(summary["attached"])
        self.assertFalse(summary["healthy"])
        self.assertEqual(summary["identity"], "")
        self.assertTrue(summary["error"])


@unittest.skipIf(_REAL_HOST is None,
                 "the Genesis runtime host has not been built on this machine")
class TestTheRealKernel(unittest.TestCase):
    """The seam against the kernel itself, when it has been built."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="kernel_real_"))
        self.kernel = GenesisKernel(_REAL_HOST, self.tmp / "state")

    def test_the_kernel_passes_its_own_self_test(self):
        self.assertTrue(self.kernel.available())

    def test_the_organism_boots_with_an_identity(self):
        result = self.kernel.boot("some/model/route")
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.identity.startswith("genesis.entity.v1.organism."))

    def test_the_identity_does_not_depend_on_the_model_route(self):
        first = self.kernel.boot("route-a")
        self.assertTrue(first.ok, first.error)
        identity = first.identity
        second = self.kernel.boot("route-b")
        self.assertTrue(second.ok, second.error)
        self.assertEqual(second.identity, identity)

    def test_an_event_is_remembered_and_the_version_advances(self):
        self.kernel.boot()
        before = self.kernel.version
        result = self.kernel.event(TOPIC_EVENT, "a task completed")
        self.assertTrue(result.ok, result.error)
        self.assertNotEqual(self.kernel.version, before)
        self.assertEqual(result.fields["state"], "ready")

    def test_the_state_survives_a_restart(self):
        """The organism is durable, which is the whole point of it."""
        self.kernel.boot()
        self.kernel.event(TOPIC_EVENT, "a task completed")
        version = self.kernel.version
        # A fresh client, the same data root: the same organism.
        again = GenesisKernel(_REAL_HOST, self.tmp / "state")
        result = again.status()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.version, version)
        self.assertEqual(again.identity, self.kernel.identity)

    def test_a_topic_the_state_machine_refuses_is_refused(self):
        self.kernel.boot()
        result = self.kernel.event("organism.not-a-topic", "x")
        self.assertFalse(result.ok)
        self.assertTrue(result.error)

    def test_checkpoint_reports_the_digests(self):
        self.kernel.boot()
        result = self.kernel.checkpoint()
        self.assertTrue(result.ok, result.error)
        self.assertIn("registry", result.fields)
        self.assertIn("memory", result.fields)


class TestRuntimeBridgeMethods(unittest.TestCase):
    """The runtime's side of the seam."""

    def setUp(self):
        from runtime import AgentRuntime, RuntimeConfig
        self.tmp = Path(tempfile.mkdtemp(prefix="kernel_rt_"))
        self.rt = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=[str(self.tmp)]))

    def test_without_a_kernel_the_runtime_says_so(self):
        summary = self.rt.genesis_summary()
        self.assertFalse(summary["attached"])
        self.assertIn("not attached", summary["error"])

    def test_without_a_kernel_observation_is_refused_honestly(self):
        result = self.rt.genesis_observe("organism.event", "x")
        self.assertFalse(result["attached"])
        self.assertFalse(result["recorded"])
        self.assertIn("not attached", result["error"])

    def test_with_a_kernel_observation_is_recorded(self):
        self.rt.genesis_kernel = GenesisKernel(
            make_stub_host(self.tmp), self.tmp / "state")
        self.rt.genesis_kernel.boot()
        result = self.rt.genesis_observe("organism.event", "a task ran")
        self.assertTrue(result["attached"])
        self.assertTrue(result["recorded"])
        self.assertTrue(self.rt.genesis_summary()["attached"])


if __name__ == "__main__":
    unittest.main()
