"""Resource Governor (§10-§14, §31-§35 of the workstation directive).

MAXIMUM USEFUL THROUGHPUT — not maximum heavy processes. The governor samples
live resource pressure and answers ONE question for the hive scheduler:

    may I start a task of class X on this machine right now?

LOGICAL WORKERS != HEAVY PROCESSES (§11): 15-30 registered workers while only
a handful consume substantial CPU/RAM/GPU at once. Subagents share
models/providers; the governor keeps spare capacity for Hermes itself and
interactive desktop control.

Extends, never duplicates (§49): hardware facts come from
machine_capability.MachineCapabilityRegistry (static discovery); this module
adds LIVE sampling, the pressure model, and the schedule/no-schedule decision.

Pressure model: normalised 0..1 per axis (cpu, ram, gpu, vram, disk), then an
overall state HEALTHY / ELEVATED / PRESSURE / CRITICAL with an honest
confidence (VERIFIED when a real sample was taken, UNKNOWN when a probe
failed — never a fabricated 0%).
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

# --- task resource classes (§12) ---------------------------------------------
LIGHT = "LIGHT"
MEDIUM = "MEDIUM"
HEAVY = "HEAVY"
GPU_HEAVY = "GPU_HEAVY"
IO_HEAVY = "IO_HEAVY"
NETWORK_HEAVY = "NETWORK_HEAVY"
TASK_CLASSES = frozenset({LIGHT, MEDIUM, HEAVY, GPU_HEAVY, IO_HEAVY,
                          NETWORK_HEAVY})

# --- pressure states (§33) ----------------------------------------------------
HEALTHY = "HEALTHY"
ELEVATED = "ELEVATED"
PRESSURE = "PRESSURE"
CRITICAL = "CRITICAL"
PRESSURE_STATES = frozenset({HEALTHY, ELEVATED, PRESSURE, CRITICAL})

# per-class resource demand, 0..1 (§12): what a task of this class typically
# consumes. Used to decide admission under current headroom.
TASK_DEMAND: dict[str, dict[str, float]] = {
    LIGHT:          {"cpu": 0.05, "ram": 0.05, "gpu": 0.0,  "vram": 0.0},
    MEDIUM:         {"cpu": 0.15, "ram": 0.15, "gpu": 0.10, "vram": 0.05},
    HEAVY:          {"cpu": 0.45, "ram": 0.35, "gpu": 0.10, "vram": 0.0},
    GPU_HEAVY:      {"cpu": 0.20, "ram": 0.20, "gpu": 0.70, "vram": 0.60},
    IO_HEAVY:       {"cpu": 0.10, "ram": 0.10, "gpu": 0.0,  "vram": 0.0},
    NETWORK_HEAVY:  {"cpu": 0.05, "ram": 0.05, "gpu": 0.0,  "vram": 0.0},
}

# admission thresholds: a task is admitted only if, after adding its demand,
# the axis stays below the gate (§10 maintain operating headroom).
AXIS_GATES = {"cpu": 0.85, "ram": 0.85, "gpu": 0.90, "vram": 0.90}

# governor's own reserve so Hermes + desktop control always have room (§10).
# The reserve SCALES with task class: a LIGHT task (a subagent call, a git
# read) must never be vetoed by the full reserve or the governor becomes a
# programme-stopper (§25 BLOCKED TASK != BLOCKED PROGRAMME) — only genuinely
# heavy local work is held back under pressure.
GOVERNOR_RESERVE = 0.15
CLASS_RESERVE_SCALE = {
    LIGHT: 0.2,          # 0.15 * 0.2 = 3% reserve
    IO_HEAVY: 0.3,
    NETWORK_HEAVY: 0.3,
    MEDIUM: 0.6,
    HEAVY: 1.0,
    GPU_HEAVY: 1.0,
}


def class_reserve(task_class: str) -> float:
    """The governor reserve for a task class (scaled, never a blanket veto)."""
    return GOVERNOR_RESERVE * CLASS_RESERVE_SCALE.get(task_class, 1.0)


def _now() -> float:
    return time.time()


@dataclass
class ResourceSample:
    """One live resource sample with honest per-axis confidence (§38)."""
    cpu: Optional[float] = None            # 0..1 utilisation
    ram: Optional[float] = None            # 0..1 utilisation
    gpu: Optional[float] = None            # 0..1 utilisation (or None)
    vram: Optional[float] = None           # 0..1 utilisation (or None)
    disk_free_gb: Optional[float] = None   # system drive
    confidence: str = "UNKNOWN"
    sampled_at: float = field(default_factory=_now)

    def axes(self) -> dict[str, Optional[float]]:
        return {"cpu": self.cpu, "ram": self.ram,
                "gpu": self.gpu, "vram": self.vram}


@dataclass
class AdmissionVerdict:
    """The governor's answer (§31) — explainable (§37)."""
    admitted: bool
    task_class: str
    pressure_state: str
    reason: str
    headroom_after: dict[str, Optional[float]] = field(default_factory=dict)
    offload_hint: str = ""     # e.g. "free cloud worker" (§13)

    def to_dict(self) -> dict:
        return {
            "admitted": self.admitted,
            "task_class": self.task_class,
            "pressure_state": self.pressure_state,
            "reason": self.reason,
            "headroom_after": self.headroom_after,
            "offload_hint": self.offload_hint,
        }


class ResourceGovernor:
    """Live resource sampling + admission control for the hive scheduler."""

    def __init__(self, capability: Any = None,
                 disk_min_free_gb: float = 20.0) -> None:
        self._lock = threading.RLock()
        self._capability = capability     # MachineCapabilityRegistry (static)
        self._disk_min_free_gb = disk_min_free_gb
        self._sample: Optional[ResourceSample] = None
        self._history: list[ResourceSample] = []

    # -- live sampling (§2, §33) ----------------------------------------------
    def sample(self) -> ResourceSample:
        """Take a fresh sample. Every axis that cannot be measured stays None
        with overall confidence UNKNOWN — never a fabricated utilisation."""
        cpu = self._sample_cpu()
        ram = self._sample_ram()
        gpu, vram = self._sample_gpu()
        disk_free = self._sample_disk()
        measured = [x for x in (cpu, ram, gpu, vram, disk_free)
                    if x is not None]
        s = ResourceSample(
            cpu=cpu, ram=ram, gpu=gpu, vram=vram, disk_free_gb=disk_free,
            confidence="VERIFIED" if measured else "UNKNOWN")
        with self._lock:
            self._sample = s
            self._history.append(s)
            self._history = self._history[-120:]   # ~2 min at 1s
        return s

    def _run(self, cmd: list[str], timeout: float = 8.0) -> tuple[bool, str]:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout, shell=False)
            return r.returncode == 0, (r.stdout or r.stderr or "").strip()
        except FileNotFoundError:
            try:
                r = subprocess.run(subprocess.list2cmdline(cmd),
                                   capture_output=True, text=True,
                                   timeout=timeout, shell=True)
                return r.returncode == 0, (r.stdout or r.stderr or "").strip()
            except (subprocess.TimeoutExpired, OSError):
                return False, ""
        except (subprocess.TimeoutExpired, OSError):
            return False, ""

    def _sample_cpu(self) -> Optional[float]:
        """CPU busy% from the Windows performance counter."""
        ok, out = self._run(["powershell", "-NoProfile", "-Command",
                             "(Get-Counter '\\Processor(_Total)\\% Processor "
                             "Time' -SampleInterval 1 -MaxSamples 1)"
                             ".CounterSamples.CookedValue"])
        if not ok or not out:
            return None
        try:
            return max(0.0, min(1.0, float(out.strip().splitlines()[-1]) / 100.0))
        except (ValueError, IndexError):
            return None

    def _sample_ram(self) -> Optional[float]:
        ok, out = self._run(["powershell", "-NoProfile", "-Command",
                             "$os=Get-CimInstance Win32_OperatingSystem; "
                             "[math]::Round((1-($os.FreePhysicalMemory/"
                             "$os.TotalVisibleMemorySize))*100,1)"])
        if not ok or not out:
            return None
        try:
            return max(0.0, min(1.0, float(out.strip().splitlines()[-1]) / 100.0))
        except (ValueError, IndexError):
            return None

    def _sample_gpu(self) -> tuple[Optional[float], Optional[float]]:
        """GPU utilisation + VRAM use via nvidia-smi when present; the GTX
        1050 Ti path. Absent smi -> (None, None), honest UNKNOWN."""
        if not shutil.which("nvidia-smi"):
            return None, None
        ok, out = self._run(["nvidia-smi",
                             "--query-gpu=utilization.gpu,memory.used,"
                             "memory.total",
                             "--format=csv,noheader,nounits"])
        if not ok or not out:
            return None, None
        try:
            util, used, total = (float(x) for x in
                                 out.strip().splitlines()[0].split(","))
            gpu = max(0.0, min(1.0, util / 100.0))
            vram = max(0.0, min(1.0, used / total)) if total > 0 else None
            return gpu, vram
        except (ValueError, IndexError):
            return None, None

    def _sample_disk(self) -> Optional[float]:
        try:
            usage = shutil.disk_usage("C:/")
            return round(usage.free / (1024 ** 3), 1)
        except OSError:
            return None

    # -- pressure model (§10, §33) ----------------------------------------------
    def pressure(self, sample: Optional[ResourceSample] = None) -> str:
        s = sample or self._sample
        if s is None:
            return CRITICAL  # unknown resources: never admit blindly
        values = [v for v in (s.cpu, s.ram, s.gpu, s.vram) if v is not None]
        if not values:
            return PRESSURE  # measured nothing: assume pressure, be safe
        peak = max(values)
        if peak >= 0.95 or (s.disk_free_gb is not None
                            and s.disk_free_gb < self._disk_min_free_gb):
            return CRITICAL
        if peak >= 0.80:
            return PRESSURE
        if peak >= 0.60:
            return ELEVATED
        return HEALTHY

    # -- admission control (§31) ------------------------------------------------
    def may_start(self, task_class: str,
                  sample: Optional[ResourceSample] = None) -> AdmissionVerdict:
        """THE scheduling question. Honest and explainable (§37)."""
        if task_class not in TASK_CLASSES:
            raise ValueError(f"unknown task class {task_class!r}")
        s = sample or self._sample
        if s is None:
            s = self.sample()
        state = self.pressure(s)
        demand = TASK_DEMAND[task_class]
        reserve = class_reserve(task_class)

        if state == CRITICAL:
            return AdmissionVerdict(
                admitted=False, task_class=task_class, pressure_state=state,
                reason="resources critical — pause/queue low-priority work",
                offload_hint="move privacy-safe work to free cloud agent")

        headroom_after: dict[str, Optional[float]] = {}
        blocked_axis = ""
        for axis, gate in AXIS_GATES.items():
            current = getattr(s, axis)
            if current is None:
                headroom_after[axis] = None
                continue
            after = current + demand[axis] + reserve
            headroom_after[axis] = round(after, 3)
            if after > gate:
                blocked_axis = axis

        if blocked_axis:
            return AdmissionVerdict(
                admitted=False, task_class=task_class, pressure_state=state,
                reason=f"{blocked_axis} headroom insufficient after task + "
                       f"governor reserve",
                headroom_after=headroom_after,
                offload_hint=_offload_hint(blocked_axis, task_class))
        return AdmissionVerdict(
            admitted=True, task_class=task_class, pressure_state=state,
            reason=f"{state}: all axes within gates after task",
            headroom_after=headroom_after)

    # -- adaptive throttling (§34) -----------------------------------------------
    def throttle_actions(self) -> list[str]:
        """What Hermes should DO at the current pressure (§34)."""
        state = self.pressure()
        if state == HEALTHY:
            return []
        if state == ELEVATED:
            return ["prefer LIGHT tasks locally; queue HEAVY/GPU_HEAVY"]
        if state == PRESSURE:
            return ["pause low-priority local workers",
                    "release unused resident models",
                    "route privacy-safe work to free cloud agents"]
        return ["pause ALL non-essential local workers",
                "release all unused resident models",
                "keep only Hermes + interactive control",
                "resume when resources recover"]

    # -- overview (§33 dashboard) -----------------------------------------------
    def overview(self) -> dict[str, Any]:
        s = self._sample
        return {
            "pressure_state": self.pressure(s),
            "sample": (None if s is None else {
                "cpu": s.cpu, "ram": s.ram, "gpu": s.gpu, "vram": s.vram,
                "disk_free_gb": s.disk_free_gb,
                "confidence": s.confidence,
                "sampled_at": s.sampled_at}),
            "throttle_actions": self.throttle_actions(),
            "gates": dict(AXIS_GATES),
            "governor_reserve": GOVERNOR_RESERVE,
        }


def _offload_hint(blocked_axis: str, task_class: str) -> str:
    """§13 cloud offload guidance — honest: only for privacy-safe work."""
    if blocked_axis in ("gpu", "vram") and task_class == GPU_HEAVY:
        return ("GPU/VRAM saturated — local model needs offload or a resident-"
                "model release; cloud reasoning acceptable for PUBLIC data")
    if blocked_axis in ("cpu", "ram"):
        return ("CPU/RAM saturated — local heavy model deferred; queue or use "
                "a lighter local model; PUBLIC research may go cloud")
    return "axis saturated — defer or offload privacy-safe work"
