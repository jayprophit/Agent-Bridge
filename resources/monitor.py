"""PressureMonitor (v0.8). Live pressure sampling + responsiveness reserve.

Wraps psutil sampling already proven in benchmarks/ into a continuous,
lane-aware pressure signal. Short samples only; no stress workloads.
"""
from __future__ import annotations

from typing import Any

from resources.descriptors import (
    LANE_BACKGROUND, LANE_BALANCED, LANE_BATCH_MAXIMUM, LANE_INTERACTIVE,
    PressureState,
)

# Reserve targets: fraction of each resource kept free per lane.
LANE_RESERVE = {
    LANE_INTERACTIVE: {"cpu": 0.35, "ram": 0.30, "vram": 0.30, "gpu": 0.30},
    LANE_BALANCED: {"cpu": 0.20, "ram": 0.20, "vram": 0.20, "gpu": 0.20},
    LANE_BACKGROUND: {"cpu": 0.10, "ram": 0.10, "vram": 0.10, "gpu": 0.10},
    LANE_BATCH_MAXIMUM: {"cpu": 0.02, "ram": 0.05, "vram": 0.05, "gpu": 0.02},
}


class PressureMonitor:
    """Samples live pressure; answers headroom questions per lane."""

    def __init__(self, lane: str = LANE_BALANCED):
        self.lane = lane if lane in LANE_RESERVE else LANE_BALANCED

    def sample(self) -> PressureState:
        """Take one quick pressure sample (no stress)."""
        state = PressureState()
        try:
            import psutil
            state.cpu = float(psutil.cpu_percent(interval=0.2)) / 100.0
            vm = psutil.virtual_memory()
            state.ram = float(vm.percent) / 100.0
            try:
                import shutil  # noqa: F401 (disk activity proxy lives here later)
            except Exception:
                pass
            try:
                battery = psutil.sensors_battery()
                state.battery_low = bool(
                    battery and not battery.power_plugged and battery.percent < 20)
            except Exception:
                pass
        except ImportError:
            pass
        vram_used, vram_total = self._vram()
        if vram_total:
            state.vram = vram_used / vram_total
        state.gpu = self._gpu_util()
        return state

    def _vram(self) -> tuple[int, int]:
        try:
            import subprocess
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                used, total = r.stdout.strip().splitlines()[0].split(",")
                return int(used.strip()), int(total.strip())
        except Exception:
            pass
        return 0, 0

    def _gpu_util(self) -> float:
        try:
            import subprocess
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return float(r.stdout.strip().splitlines()[0].strip()) / 100.0
        except Exception:
            pass
        return 0.0

    def headroom_ok(self, state: PressureState, lane: str = "") -> bool:
        """True if every axis keeps its lane reserve."""
        reserve = LANE_RESERVE.get(lane or self.lane, LANE_RESERVE[LANE_BALANCED])
        return (state.cpu <= 1.0 - reserve["cpu"]
                and state.ram <= 1.0 - reserve["ram"]
                and state.vram <= 1.0 - reserve["vram"]
                and state.gpu <= 1.0 - reserve["gpu"])

    def pressure_response(self, state: PressureState) -> dict[str, Any]:
        """Recommended response actions for current pressure (no side effects)."""
        actions: list[str] = []
        if state.cpu >= 0.9:
            actions += ["reduce_cpu_workers", "prefer_gpu_npu_lanes",
                        "delay_background_jobs", "serialize_expensive_tasks"]
        if state.vram >= 0.85:
            actions += ["reduce_offload_or_model_size", "unload_inactive_model",
                        "move_compatible_work_to_cpu"]
        if state.ram >= 0.85:
            actions += ["shrink_cache", "reduce_concurrency", "unload_models",
                        "use_artifact_references"]
        if state.gpu <= 0.15 and state.cpu >= 0.7:
            actions += ["increase_gpu_placement_where_backend_supports"]
        if state.battery_low:
            actions += ["lower_concurrency", "prefer_efficient_execution"]
        if state.thermal:
            actions += ["lower_concurrency", "prefer_efficient_execution"]
        return {"hottest": state.hottest(), "actions": actions,
                "headroom_ok": self.headroom_ok(state)}

    def describe(self) -> dict[str, Any]:
        state = self.sample()
        return {"lane": self.lane, "pressure": state.to_dict(),
                "response": self.pressure_response(state)}
