"""Full v0.7 local acceptance aggregator (run once at convergence).

Runs run_windows_v07_acceptance.py, then the complete unittest suite via
`python -m unittest discover -s tests -p "test_*.py"`, and writes a combined
summary. Slow (several minutes); run once.

Usage:
    python run_v07_full_local_acceptance.py [--json-out PATH]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_windows_acceptance() -> dict:
    import run_windows_v07_acceptance as acc
    results = []
    for name, fn in acc.CHECKS:
        t0 = time.monotonic()
        try:
            detail = fn() or {}
            status = detail.pop("_status", acc.PASS)
            results.append({"category": name, "status": status,
                            "duration_s": round(time.monotonic() - t0, 2),
                            "detail": detail})
        except Exception as e:  # noqa: BLE001
            results.append({"category": name, "status": acc.FAIL,
                            "duration_s": round(time.monotonic() - t0, 2),
                            "detail": {"error": f"{type(e).__name__}: {e}"}})
    return {"results": results,
            "summary": {s: sum(1 for r in results if r["status"] == s)
                        for s in {r["status"] for r in results}}}


def run_full_suite() -> dict:
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover",
         "-s", "tests", "-p", "test_*.py"],
        cwd=HERE, capture_output=True, text=True, timeout=3600)
    out = proc.stderr + proc.stdout
    m = re.search(r"Ran (\d+) tests? in ([\d.]+)s", out)
    lines = out.strip().splitlines()
    tail = lines[-3:] if lines else []
    return {"returncode": proc.returncode,
            "discovered": int(m.group(1)) if m else -1,
            "duration_s": float(m.group(2)) if m else round(time.monotonic() - t0, 2),
            "ok": proc.returncode == 0 and "OK" in out,
            "tail": tail}


def count_test_files() -> int:
    import glob
    return len(glob.glob(os.path.join(HERE, "tests", "test_*.py")))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-out", default=os.path.join("reports", "v0.8", "V07_FULL_ACCEPTANCE.json"))
    ns = ap.parse_args(argv)
    print("=== windows acceptance ===", flush=True)
    windows = run_windows_acceptance()
    print("=== full unittest suite ===", flush=True)
    suite = run_full_suite()
    report = {"windows_acceptance": windows, "full_suite": suite,
              "test_files": count_test_files()}
    with open(ns.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    fails = [r for r in windows["results"] if r["status"] == "FAIL"]
    print(f"windows: {len(windows['results'])} categories, {len(fails)} failures")
    print(f"suite: discovered={suite['discovered']} ok={suite['ok']} "
          f"duration={suite['duration_s']}s files={report['test_files']}")
    return 1 if (fails or not suite["ok"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
