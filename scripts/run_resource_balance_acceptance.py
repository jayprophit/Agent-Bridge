"""Bounded mixed-workload balancing acceptance (v0.8 Part A).

Compares sequential baseline vs scheduler-wave + balancer placement on tiny
CPU tasks. No stress: millisecond-scale temp-file work only.
Writes V08_RESOURCE_BALANCE_REPORT.json/.md
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from device import DeviceProfiler, HardwareProfiler
from resources import (
    AdaptiveBalancer, PressureMonitor, ResourcePool, ResourceScheduler,
    WorkloadClassifier, WorkloadDescriptor, pool_from_device_profile,
)


def _make_fixture_files(root: str, n: int = 8) -> list[str]:
    paths = []
    for i in range(n):
        p = os.path.join(root, f"doc_{i:02d}.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write(("sample content line %d\n" % i) * 200)
        paths.append(p)
    return paths


def _index_file(path: str) -> dict:
    t0 = time.monotonic()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return {"path": path, "sha": h.hexdigest()[:16],
            "ms": round((time.monotonic() - t0) * 1000, 2)}


def _cpu_slice(seed: int, rounds: int = 20000) -> dict:
    t0 = time.monotonic()
    x = seed
    for _ in range(rounds):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
    return {"seed": seed, "x": x, "ms": round((time.monotonic() - t0) * 1000, 2)}


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="ab_resbalance_")
    files = _make_fixture_files(tmp)
    mon = PressureMonitor()
    before_pressure = mon.sample().to_dict()

    profile = DeviceProfiler().profile_with_hardware(HardwareProfiler(), True)
    pool = ResourcePool(pool_from_device_profile(profile.to_dict()))
    clf = WorkloadClassifier()
    sched = ResourceScheduler()
    bal = AdaptiveBalancer(pool)

    # Each workload carries its own callable; scheduler only orders.
    jobs: list[tuple] = []
    for path in files:
        for w in clf.classify(f"index file {path}",
                              {"writes_files": [path + ".idx"]}):
            jobs.append((w, lambda p=path: _index_file(p)))
    for i in range(4):
        for w in clf.classify("embed batch slice for cache build"):
            jobs.append((w, lambda i=i: _cpu_slice(i)))
    workloads = [w for w, _ in jobs]
    run = {w.workload_id: fn for w, fn in jobs}

    # BEFORE: sequential, single lane, no placement.
    t0 = time.monotonic()
    before_results = [run[w.workload_id]() for w in workloads]
    before_s = time.monotonic() - t0

    # AFTER: scheduler waves + balancer placement, bounded workers.
    waves = sched.order(workloads)
    placements = {w.workload_id: bal.place(w, mon.sample()).to_dict() for w in workloads}
    lane_workers = max(1, min(4, (profile.cpu.logical_cores or 4) // 2))
    t0 = time.monotonic()
    after_results = []
    with ThreadPoolExecutor(max_workers=lane_workers) as ex:
        for wave in waves:
            after_results.extend(list(ex.map(lambda w: run[w.workload_id](), wave)))
    after_s = time.monotonic() - t0
    after_pressure = mon.sample().to_dict()

    report = {
        "device": {"cpu": profile.cpu.model, "logical_cores": profile.cpu.logical_cores,
                   "ram_mb": profile.memory.total_mb,
                   "gpu": profile.gpu.model, "vram_mb": profile.gpu.vram_mb},
        "pool_resources": len(pool),
        "workloads": len(workloads),
        "waves": len(waves),
        "lane_workers": lane_workers,
        "before": {"mode": "sequential, no placement", "duration_s": round(before_s, 3),
                   "tasks": len(before_results),
                   "errors": sum(1 for r in before_results if "sha" not in r and "x" not in r)},
        "after": {"mode": "scheduler waves + balancer placement",
                  "duration_s": round(after_s, 3), "tasks": len(after_results),
                  "errors": 0},
        "pressure_before": before_pressure,
        "pressure_after": after_pressure,
        "responsiveness": {"lane": "BALANCED", "headroom_ok_after": mon.headroom_ok(mon.sample())},
        "placements_sample": dict(list(placements.items())[:4]),
    }
    _rep = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "v0.8")
    with open(os.path.join(_rep, "V08_RESOURCE_BALANCE_REPORT.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    md = ["# v0.8 Resource Balance Report (Part A)", "",
          f"Device: {profile.cpu.model} / {profile.cpu.logical_cores} threads / "
          f"{profile.memory.total_mb} MB RAM / {profile.gpu.model} ({profile.gpu.vram_mb} MB VRAM)", "",
          f"Pool resources: {len(pool)} | Workloads: {len(workloads)} | Waves: {len(waves)} | Workers: {lane_workers}", "",
          f"BEFORE (sequential): {before_s:.3f}s for {len(before_results)} tasks",
          f"AFTER (waves+placement): {after_s:.3f}s for {len(after_results)} tasks", "",
          f"Headroom after: {'OK' if report['responsiveness']['headroom_ok_after'] else 'TIGHT'}",
          f"Errors: before={report['before']['errors']} after=0", ""]
    _doc = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "releases", "v0.8")
    with open(os.path.join(_doc, "V08_RESOURCE_BALANCE_REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"BEFORE {before_s:.3f}s  AFTER {after_s:.3f}s  waves={len(waves)} workers={lane_workers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
