"""P8: Agent Bridge <-> Universal-Bridge capability proof.

Invokes the Universal-Bridge CLI's read-only `devices` inventory as a
subprocess capability with workspace scoping, then packages the result as
a Genesis-bound observation (same envelope shape as P5). Mutating UB
commands (midi-send-*, audio-capture) are never invoked here.

The ubridge binary resolves via UBRIDGE_EXE, defaulting to the canonical
Universal-Bridge checkout build output; the test skips when absent.
"""
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _ubridge_exe() -> Path | None:
    env = os.environ.get("UBRIDGE_EXE", "")
    candidates = []
    if env:
        candidates.append(Path(env))
    projects = REPO_ROOT.parent
    candidates.append(
        projects / "Universal-Bridge" / "build" / "p0-verify" / "bin" / "Debug" / "ubridge.exe"
    )
    candidates.append(
        projects / "Universal-Bridge" / "build" / "release" / "bin" / "Release" / "ubridge.exe"
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class UBridgeCapabilityTests(unittest.TestCase):
    def test_devices_inventory_receipt_and_observation(self):
        exe = _ubridge_exe()
        if exe is None:
            self.skipTest("ubridge binary absent (build Universal-Bridge first)")
        tmp = Path(tempfile.mkdtemp(prefix="p8_ubridge_"))
        try:
            proc = subprocess.run(
                [str(exe), "devices"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(tmp),
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("read-only device inventory", proc.stdout.lower())

            receipt = {
                "request_id": "ubridge-devices",
                "capability": "ubridge.devices",
                "transport": "subprocess",
                "executable": exe.name,
                "returncode": proc.returncode,
                "output_head": proc.stdout[:500],
            }
            receipt["receipt_digest"] = hashlib.sha256(
                json.dumps(receipt, sort_keys=True).encode("utf-8")
            ).hexdigest()
            observation = {
                "source": "universal-bridge",
                "identity": "genesis:organism-main",
                "observation": receipt,
            }
            self.assertEqual(len(observation["observation"]["receipt_digest"]), 64)
            # No mutation: only stdout captured, workspace untouched.
            self.assertEqual(
                [p.name for p in tmp.iterdir()],
                [],
                "devices inventory must not write into the workspace",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
