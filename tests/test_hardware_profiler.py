"""Hardware profiler honesty: when a platform probe is unavailable, report
"unknown" rather than inventing a value.

The profiler feeds execution-target and placement decisions, so a fabricated
GPU or drive type would silently steer work onto the wrong hardware. In the
existing suite the profiler appears only as a MagicMock (test_benchmark.py),
so its failure behaviour is unpinned.

These tests pin the FAILURE path on whatever host they run on, and
deliberately assert nothing about the host's real hardware - a test that
depends on the machine is a test that will fail on someone else's. The
positive detection paths stay covered by the acceptance harnesses, which are
platform-specific by construction.
"""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from device.hardware_profiler import HardwareProfiler


def _no_tool(*args, **kwargs):
    raise FileNotFoundError("platform probe not present")


class HardwareProfilerHonestyTests(unittest.TestCase):
    def setUp(self):
        self.p = HardwareProfiler()

    def test_drive_type_is_unknown_when_the_probe_is_absent(self):
        with mock.patch.object(subprocess, "run", side_effect=_no_tool):
            self.assertEqual(self.p._detect_drive_type(), "unknown")

    def test_drive_type_is_unknown_when_the_probe_says_nothing_usable(self):
        """A successful call whose output contains no recognised line must not
        guess - absence of evidence is not evidence of a value."""
        empty = mock.Mock(returncode=0, stdout="")
        with mock.patch.object(subprocess, "run", return_value=empty):
            self.assertEqual(self.p._detect_drive_type(), "unknown")

    def test_drive_type_is_unknown_when_the_probe_reports_failure(self):
        failed = mock.Mock(returncode=1, stdout="", stderr="denied")
        with mock.patch.object(subprocess, "run", return_value=failed):
            self.assertEqual(self.p._detect_drive_type(), "unknown")

    def test_interface_type_is_unknown_for_an_unrecognised_name(self):
        self.assertEqual(self.p._detect_interface_type("zzz9"), "unknown")

    def test_probes_degrade_instead_of_raising(self):
        """A profiler that throws is worse than one that answers "unknown":
        a caller cannot tell those apart, and a throw during capability
        discovery takes down whatever was asking."""
        with mock.patch.object(subprocess, "run", side_effect=_no_tool):
            with mock.patch.object(subprocess, "check_output", side_effect=_no_tool):
                for name in ("profile_cpu", "profile_memory", "profile_storage",
                             "profile_network", "profile_accelerators", "profile_gpu"):
                    try:
                        getattr(self.p, name)()
                    except Exception as exc:  # pragma: no cover - diagnostic
                        self.fail(f"{name} raised {exc!r} instead of degrading")

    def test_repeated_probing_is_safe(self):
        """Detection is called from planning paths more than once; it must not
        cache a failed probe as a real answer or raise on the second call."""
        with mock.patch.object(subprocess, "run", side_effect=_no_tool):
            first = self.p._detect_drive_type()
            second = self.p._detect_drive_type()
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
