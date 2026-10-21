"""The Bridge's client for the Genesis runtime host.

Genesis is the organism: identity, memory, state and the causal runtime.
It is a C++ kernel. The Bridge is the execution runtime. Until now the
two shared a name and nothing else. The Bridge's "Genesis runtime" was
a Python store of session and identity references over JSON, and the C++
kernel that actually carries the organism was built, tested and never
run by anything.

This is the seam, and it is the thing the inheritance document's third
step asks for: Genesis proven through the IDE and the Bridge.

The kernel's runtime host is a one-shot command. It boots an organism,
applies one event to it, checkpoints it, and reports its state; the
durable state lives on disk between calls, and the organism's identity
is derived from its namespace and key rather than from the model route,
so replacing the model does not replace the organism.

The seam is optional, and the Bridge says so. A Bridge with no kernel
attached still runs every task, and reports that the organism is not
attached rather than pretending that it is. A kernel that is attached
and fails is a fault that is recorded, not one that is swallowed.

Ownership is not merged. The Bridge owns execution, the policy, the
tools and the environments. The kernel owns identity, memory and the
runtime's own state. The Bridge asks the kernel to observe and to
remember; it does not ask it to decide what is allowed to run.
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# The host prints key=value pairs. The first word is the kind of line.
_FIELD = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]+)")

# The topics the kernel's state machine accepts. The rules are strict:
# boot takes genesis.boot, and a ready organism takes organism.event,
# organism.checkpoint or organism.rollback. Anything else is rejected,
# and a rejection is a fact worth recording rather than a retry.
TOPIC_EVENT = "organism.event"
TOPIC_CHECKPOINT = "organism.checkpoint"
TOPIC_ROLLBACK = "organism.rollback"


def parse_fields(line: str) -> dict[str, str]:
    """The key=value pairs in one line of the host's output."""
    return {m.group(1): m.group(2) for m in _FIELD.finditer(line)}


@dataclass
class KernelResult:
    """What one call to the host returned.

    `ok` is false when the host refused or failed. The error is the
    host's own words, because a paraphrase would hide what the kernel
    actually said.
    """

    verb: str = ""
    ok: bool = False
    fields: dict[str, str] = field(default_factory=dict)
    error: str = ""
    duration_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "verb": self.verb,
            "ok": self.ok,
            "fields": dict(self.fields),
            "error": self.error,
            "duration_s": round(self.duration_s, 4),
        }

    @property
    def identity(self) -> str:
        return self.fields.get("identity", "")

    @property
    def version(self) -> str:
        return self.fields.get("version", "")

    @property
    def state(self) -> str:
        return self.fields.get("state", "")


class GenesisKernel:
    """The Bridge's view of the Genesis runtime host.

    The host is a one-shot command, so each call is a durable step: it
    loads the organism's state from disk, applies the one thing it was
    asked to do, and writes the state back.

    The host is given as a command rather than only as a path, so a host
    that needs an interpreter, or any other launcher, can be used
    without changing the client.
    """

    def __init__(self, host: str | Path | list[str], data_root: str | Path,
                 timeout_s: float = 30.0):
        if isinstance(host, (str, Path)):
            self.command = [str(host)]
        else:
            self.command = [str(part) for part in host]
        # The host itself is the last part of the command. When the
        # command is a single path that is the path; when it is an
        # interpreter and a script, the script is the host.
        self.host_path = Path(self.command[-1]) if self.command else Path("")
        self.data_root = Path(data_root)
        self.timeout_s = timeout_s
        self.calls = 0
        self.failures = 0
        self.last_error = ""
        self.last_ok = False
        self.identity = ""
        self.version = ""
        self.state = ""
        self.attached = False

    # -- the host ---------------------------------------------------------

    def available(self) -> bool:
        """Is the host there and is it runnable?

        The host is asked to prove itself: its own self-test boots an
        organism, records an event, checkpoints it, restarts and rolls
        back. A host that cannot do that is not a host this Bridge
        should attach to.
        """
        try:
            proc = subprocess.run(
                self.command + ["--self-test"],
                capture_output=True, text=True, timeout=self.timeout_s)
        except (OSError, subprocess.SubprocessError):
            return False
        return proc.returncode == 0 and "self-test ok" in proc.stdout

    def _run(self, verb: str, *args: str) -> KernelResult:
        """One call to the host, and what it said."""
        started = time.time()
        result = KernelResult(verb=verb)
        # The host writes into the data root, so it has to exist. A
        # missing root is the one thing that would otherwise look like a
        # kernel fault.
        try:
            self.data_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result.error = (f"the kernel's data root could not be created: "
                            f"{exc}")
            result.duration_s = time.time() - started
            self._note(result)
            return result
        command = self.command + [verb, "--data-root", str(self.data_root)]
        command.extend(args)
        try:
            proc = subprocess.run(command, capture_output=True, text=True,
                                  timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            result.error = (f"the kernel host did not answer within "
                            f"{self.timeout_s:g} seconds")
            result.duration_s = time.time() - started
            self._note(result)
            return result
        except OSError as exc:
            result.error = f"the kernel host could not be run: {exc}"
            result.duration_s = time.time() - started
            self._note(result)
            return result

        result.duration_s = time.time() - started
        self.calls += 1
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        if lines:
            result.fields = parse_fields(lines[-1])
        if proc.returncode == 0:
            result.ok = True
            # The host prints a different leading word per verb: "booted",
            # "already booted", "checkpoint ok", "event=evt-2". The word is
            # kept whole, because it is the host's own description of what
            # it did.
            if lines:
                result.fields.setdefault("line", lines[-1].strip())
        else:
            result.error = (stderr.splitlines()[-1] if stderr
                             else (lines[-1] if lines else
                                   f"the kernel host exited with "
                                   f"{proc.returncode}"))
        self._note(result)
        return result

    def _note(self, result: KernelResult) -> None:
        """Keep the last known truth about the organism."""
        self.last_ok = result.ok
        if not result.ok:
            self.failures += 1
            self.last_error = result.error
            return
        if result.identity:
            self.identity = result.identity
        if result.version:
            self.version = result.version
        if result.state:
            self.state = result.state
        self.attached = True

    # -- the verbs --------------------------------------------------------

    def boot(self, model_route: str = "") -> KernelResult:
        """Boot the organism, or confirm it is already booted."""
        args = ["--model-route", model_route] if model_route else []
        return self._run("--boot", *args)

    def event(self, topic: str, payload: str) -> KernelResult:
        """Record one event against the organism."""
        return self._run("--event", "--topic", topic, "--payload", payload)

    def checkpoint(self) -> KernelResult:
        """Write the organism's durable state and report it."""
        return self._run("--checkpoint")

    def status(self) -> KernelResult:
        """The organism's current state."""
        return self._run("--status")

    def rollback(self, version: str) -> KernelResult:
        """Return the organism to an earlier version, as a new version."""
        return self._run("--rollback", "--to-version", version)

    # -- the view ---------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        """What a person or another service can read about the organism.

        This is what the Bridge publishes, and it is deliberately explicit
        about absence: an unattached kernel says so, rather than
        reporting an organism that does not exist.
        """
        if not self.attached:
            return {
                "attached": False,
                "healthy": False,
                "identity": "",
                "version": "",
                "state": "",
                "host": str(self.host_path),
                "data_root": str(self.data_root),
                "calls": self.calls,
                "failures": self.failures,
                "error": (self.last_error
                          or "the Genesis kernel is not attached to this Bridge"),
            }
        return {
            "attached": True,
            "healthy": self.last_ok,
            "identity": self.identity,
            "version": self.version,
            "state": self.state,
            "host": str(self.host_path),
            "data_root": str(self.data_root),
            "calls": self.calls,
            "failures": self.failures,
            "error": self.last_error,
        }


__all__ = [
    "GenesisKernel",
    "KernelResult",
    "parse_fields",
    "TOPIC_EVENT",
    "TOPIC_CHECKPOINT",
    "TOPIC_ROLLBACK",
]
