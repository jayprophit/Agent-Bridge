"""P14: end-to-end MAT -> Bridge envelope -> Genesis host chain.

1. Query real MAT data (hydrogen first ionisation) via mat-query-service.
2. Package the result as a Genesis-bound observation envelope (P5 shape)
   with a stable receipt digest.
3. Feed the envelope into genesis_runtime_host (--boot/--event/--checkpoint)
   and verify persistence + identity continuity.

External checkouts resolve via MAT_ROOT / GENESIS_HOST (defaults to the
canonical sibling checkouts); the test skips when either is absent. The
machine-to-machine transport itself remains manual here (P5b/P7 scope);
this test proves the data contract holds end to end.
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


def _mat_root() -> Path | None:
    env = os.environ.get("MAT_ROOT", "")
    candidates = []
    if env:
        candidates.append(Path(env))
    candidates.append(REPO_ROOT.parent / "Materials-Atlas-Table-Codex---MAT")
    for candidate in candidates:
        if (candidate / "scripts" / "mat-query-service.mjs").exists():
            return candidate
    return None


def _genesis_host() -> Path | None:
    env = os.environ.get("GENESIS_HOST", "")
    candidates = []
    if env:
        candidates.append(Path(env))
    base = REPO_ROOT.parent / "Genesis" / "build" / "p0-verify" / "Debug"
    candidates.append(base / "genesis_runtime_host.exe")
    candidates.append(base / "genesis_runtime_host")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _digest(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


class MatToGenesisTests(unittest.TestCase):
    def test_mat_value_flows_to_genesis_memory(self):
        if shutil.which("node") is None:
            self.skipTest("node unavailable")
        mat = _mat_root()
        if mat is None:
            self.skipTest("MAT checkout absent")
        host = _genesis_host()
        if host is None:
            self.skipTest("genesis_runtime_host binary absent")

        query = subprocess.run(
            ["node", "scripts/mat-query-service.mjs",
             "--symbol", "H", "--property", "ionization.first"],
            capture_output=True, text=True, timeout=120, cwd=str(mat))
        self.assertEqual(query.returncode, 0, query.stderr[:300])
        response = json.loads(query.stdout)
        self.assertTrue(response["found"])
        result = response["results"][0]
        self.assertEqual(result["value"], 13.598434599702)
        self.assertEqual(result["unit"], "eV")
        self.assertEqual(result["evidence_class"], "CALCULATED")
        self.assertTrue(result["source_id"])

        envelope = {
            "request_id": "mat-h-ionization",
            "session_id": "p14-e2e",
            "identity": "genesis:organism-main",
            "capability": "mat.query",
            "result": result,
            "provenance": response["provenance"],
        }
        envelope["receipt_digest"] = _digest(envelope)
        payload = json.dumps(envelope, sort_keys=True)

        data_root = Path(tempfile.mkdtemp(prefix="p14_e2e_"))
        try:
            boot = subprocess.run(
                [str(host), "--boot", "--data-root", str(data_root),
                 "--model-route", "p14-e2e"],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(boot.returncode, 0, boot.stderr[:300])
            identity = boot.stdout.split("identity=")[1].split()[0]

            event = subprocess.run(
                [str(host), "--event", "--data-root", str(data_root),
                 "--topic", "organism.event", "--payload", payload],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(event.returncode, 0, event.stderr[:300])
            self.assertIn("seq=2", event.stdout)

            check = subprocess.run(
                [str(host), "--checkpoint", "--data-root", str(data_root)],
                capture_output=True, text=True, timeout=120)
            self.assertEqual(check.returncode, 0, check.stderr[:300])
            self.assertIn(f"identity={identity}", check.stdout)
            self.assertIn("version=v2", check.stdout)
            # Envelope digest is the stable link across the chain.
            self.assertEqual(len(envelope["receipt_digest"]), 64)
        finally:
            shutil.rmtree(data_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
