"""Persistent Supervisor Runtime (§1-§33 of the runtime directive).

THE CHAT MAY END. THE SUPERVISOR MUST NOT.

This module is the durable local process that owns the §33 supervision loop.
A Hermes chat turn is a CONTROL SURFACE (reports, owner instructions,
priorities); THIS is the scheduler. Worker continuity must never depend on
another chat message.

    while programme_not_complete:
        observe_workers()          # adapters (opencode db, codex rollout, ...)
        ingest_events()
        update_heartbeats()
        detect_idle / detect_stalled
        ingest_handoffs()
        review_completed_tasks()
        run_fast_gap_analysis()
        refresh_ready_queue()
        assign_available_workers()  # hive router + resource governor gate
        monitor_quotas / monitor_resources
        persist_checkpoint()
        sleep(adaptive)              # event-driven where possible (§5)

Reuses, never duplicates (§49):
- compute/supervision.Supervisor    — worker records, handoff queue, review
- compute.hive_scheduler.HiveScheduler — routing, quota pools, reservations
- compute.resource_governor.ResourceGovernor — live admission control
- compute.knowledge_index.KnowledgeIndex — task-scoped context retrieval

Honesty (§15): an adapter reports UNKNOWN when it cannot determine state;
a fabricated "worker is fine" is worse than an honest UNKNOWN. The runtime
never claims CONTINUOUS_SUPERVISION = LIVE_VERIFIED without the §30
acceptance evidence.

Run:  python compute/supervisor_runtime.py --once     (single cycle, testable)
      python compute/supervisor_runtime.py             (persistent daemon)
      python compute/supervisor_runtime.py --status    (print checkpoint)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

# runnable as a script from the repo root (§20 startup): ensure the package
# parent is importable regardless of the invocation cwd
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compute.hive_scheduler import (
    OWNED_PAID_ENTITLEMENT, POOL_SHORT_WINDOW, POOL_WEEKLY, QuotaLedgerEntry,
    UNKNOWN, HiveScheduler)
from compute.resource_governor import ResourceGovernor
from compute.supervision import (
    AWAITING_QA, AVAILABLE, Handoff, Supervisor)

# --- worker verdicts (§6) ------------------------------------------------------
RUNNING = "RUNNING"
IDLE = "IDLE"
OFFLINE = "OFFLINE"
STALLED = "STALLED"
UNKNOWN_VERDICT = "UNKNOWN"
WAITING_FOR_QUOTA = "WAITING_FOR_QUOTA"   # §4: usage-limit cooldown

# --- idle reasons (§12: an idle worker with NO idle_reason is a DEFECT) --------
NO_COMPATIBLE_READY_WORK = "NO_COMPATIBLE_READY_WORK"
WAITING_DEPENDENCY = "WAITING_DEPENDENCY"
WAITING_QUOTA = "WAITING_QUOTA"
RESOURCE_GOVERNOR = "RESOURCE_GOVERNOR"
MAINTENANCE = "MAINTENANCE"
OWNER_GATE = "OWNER_GATE"
INTENTIONAL_RESERVE = "INTENTIONAL_RESERVE"
SUPERVISOR_DEFECT = "SUPERVISOR_DEFECT"
VALID_IDLE_REASONS = frozenset({
    NO_COMPATIBLE_READY_WORK, WAITING_DEPENDENCY, WAITING_QUOTA,
    RESOURCE_GOVERNOR, MAINTENANCE, OWNER_GATE, INTENTIONAL_RESERVE})

# --- shift (§21-§22) -------------------------------------------------------------
DAY = "DAY"
NIGHT = "NIGHT"


def _now() -> float:
    return time.time()


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness check for the instance lock / watchdog."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        pass
    # Windows: os.kill(pid, 0) succeeds for any existing pid on some shells;
    # confirm via tasklist for a definitive answer.
    try:
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                           capture_output=True, text=True, timeout=15.0)
        return str(pid) in (r.stdout or "")
    except (subprocess.TimeoutExpired, OSError):
        return False


_COOLDOWN_TIME_RE = re.compile(
    r"try again at\s+(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
_USAGE_LIMIT_RE = re.compile(r"usage_limit_exceeded|usage limit|"
                             r"hit your usage", re.IGNORECASE)


def parse_codex_cooldown(rollout_path: Path) -> Optional[dict[str, Any]]:
    """§4: read the LIVE five-hour reset time from the newest rollout.
    Codex writes 'usage_limit_exceeded ... try again at 2:59 PM' into the
    task_complete error. Returns None when the session is not in cooldown.
    Honesty: only reports a reset the model itself actually printed."""
    try:
        lines = rollout_path.read_text(encoding="utf-8").splitlines()
        observed_at = rollout_path.stat().st_mtime
    except OSError:
        return None
    # Inspect lifecycle events, not quoted errors in prompts/tool output. A
    # resumed or successfully completed turn supersedes the earlier cooldown.
    event = None
    for line in reversed(lines):
        try:
            candidate = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(candidate, dict):
            continue
        payload = candidate.get("payload")
        if (candidate.get("type") not in (None, "event_msg") or
                not isinstance(payload, dict)):
            continue
        if payload.get("type") == "task_started":
            return None
        if payload.get("type") == "task_complete":
            event = candidate
            break
    if event is None:
        return None
    error = json.dumps(event["payload"].get("error"))
    if not _USAGE_LIMIT_RE.search(error):
        return None
    m = _COOLDOWN_TIME_RE.search(error)
    if not m:
        return {"reset_at": None, "resets_in_s": None}
    hh, mm, ampm = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if not 1 <= hh <= 12 or not 0 <= mm <= 59:
        return {"reset_at": None, "resets_in_s": None}
    if ampm == "PM" and hh != 12:
        hh += 12
    if ampm == "AM" and hh == 12:
        hh = 0
    try:
        observed_at = datetime.fromisoformat(
            event["timestamp"].replace("Z", "+00:00")).timestamp()
    except (KeyError, TypeError, ValueError, AttributeError):
        pass  # Legacy records have only the rollout's modification time.
    observed = datetime.fromtimestamp(observed_at)
    reset = observed.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if reset < observed:
        reset += timedelta(days=1)
    reset_ts = reset.timestamp()
    remaining = reset_ts - _now()
    if remaining <= 0:
        return None
    return {"reset_at": time.strftime("%H:%M", time.localtime(reset_ts)),
            "resets_in_s": remaining}


@dataclass
class WorkerAdapter:
    """§9 UNIVERSAL EXTERNAL WORKER ADAPTER — one protocol for every app.

    Capabilities are per-adapter and may be UNKNOWN/unsupported. NOTHING is
    fabricated: if an adapter cannot determine a fact, it returns UNKNOWN.
    """
    worker_id: str
    application: str
    role: str
    worker_type: str = "EXTERNAL_AI_AGENT"

    def status(self) -> dict[str, Any]:
        """-> {"verdict": RUNNING|IDLE|OFFLINE|STALLED|UNKNOWN, "evidence": [...]}"""
        raise NotImplementedError

    def send_instruction(self, instruction: str,
                         continue_task: bool = False) -> dict[str, Any]:
        """-> {"delivered": bool, "evidence": [...]}"""
        raise NotImplementedError

    def current_task(self) -> dict[str, Any]:
        return {"task": "", "evidence": []}

    def quota_state(self) -> list[QuotaLedgerEntry]:
        return []


# --- real adapters (verified channels, §9/§28) ------------------------------------
class OpenCodeAdapter(WorkerAdapter):
    """OpenCode telemetry via the sanctioned `opencode db` channel (the app
    owns the WAL; never raw sqlite3) and instruction delivery via the
    headless `opencode run` CLI channel (§control-channel priority: CLI
    before GUI). Falls back to GUI composer via the clipboard channel only
    when the CLI channel is unavailable (the caller decides)."""

    def __init__(self, worker_id: str = "opencode-primary",
                 liveness_window_s: float = 600.0,
                 opencode_bin: str = "opencode") -> None:
        super().__init__(worker_id=worker_id, application="opencode",
                         role="ide-worker")
        self.liveness_window_s = liveness_window_s
        self.bin = opencode_bin

    def _run(self, args: list[str], timeout: float = 30.0
             ) -> tuple[bool, str]:
        try:
            r = subprocess.run(args, capture_output=True, text=True,
                               timeout=timeout, shell=False)
            return r.returncode == 0, (r.stdout or r.stderr or "")
        except FileNotFoundError:
            try:
                r = subprocess.run(subprocess.list2cmdline(args),
                                   capture_output=True, text=True,
                                   timeout=timeout, shell=True)
                return r.returncode == 0, (r.stdout or r.stderr or "")
            except (subprocess.TimeoutExpired, OSError):
                return False, ""
        except (subprocess.TimeoutExpired, OSError):
            return False, ""

    def status(self) -> dict[str, Any]:
        ok, out = self._run([self.bin, "db",
                             "SELECT id,title,time_updated FROM session "
                             "ORDER BY time_updated DESC LIMIT 1",
                             "--format", "json"])
        if not ok or not out.strip():
            return {"verdict": OFFLINE,
                    "evidence": [f"opencode db failed: {out[:120]}"]}
        try:
            row = json.loads(out)[0]
        except (json.JSONDecodeError, IndexError, KeyError):
            return {"verdict": UNKNOWN_VERDICT,
                    "evidence": ["opencode db returned unparseable output"]}
        age_s = (_now() * 1000 - float(row["time_updated"])) / 1000.0
        verdict = RUNNING if age_s <= self.liveness_window_s else IDLE
        return {"verdict": verdict,
                "evidence": [f"session {row['id'][:24]} updated "
                             f"{age_s:.0f}s ago (window "
                             f"{self.liveness_window_s:.0f}s)"]}

    def send_instruction(self, instruction: str,
                         continue_task: bool = False) -> dict[str, Any]:
        """Headless CLI channel. NOTE: `opencode run` starts/uses a headless
        session — it does NOT resume the GUI composer session. The GUI
        clipboard channel remains the composer route; the caller (Hermes chat
        turn or the runtime's GUI fallback) owns that decision. Honest
        limitation recorded rather than hidden (§15)."""
        ok, out = self._run([self.bin, "run", instruction], timeout=1800.0)
        return {"delivered": ok,
                "channel": "opencode-run (headless)",
                "evidence": [out[:200] if out else "no output"],
                "limitation": "headless session; GUI composer session "
                              "requires the clipboard channel"}


class CodexAdapter(WorkerAdapter):
    """Codex telemetry via rollout-JSONL mtime (verified: sessions live at
    ~/.codex/sessions/*/*/*/rollout-*.jsonl, session_meta first line).
    Instruction delivery via `codex exec resume --last` — the session-
    preserving headless channel (§control-channel priority: CLI)."""

    def __init__(self, worker_id: str = "codex-primary",
                 codex_home: Optional[str] = None,
                 liveness_window_s: float = 900.0,
                 codex_bin: str = "codex") -> None:
        super().__init__(worker_id=worker_id, application="codex",
                         role="mat-worker")
        self.home = Path(codex_home or (Path.home() / ".codex"))
        self.liveness_window_s = liveness_window_s
        self.bin = codex_bin

    def status(self) -> dict[str, Any]:
        sessions = self.home / "sessions"
        if not sessions.is_dir():
            return {"verdict": OFFLINE,
                    "evidence": [f"no sessions dir at {sessions}"]}
        newest: Optional[Path] = None
        newest_m = 0.0
        for p in sessions.rglob("rollout-*.jsonl"):
            try:
                m = p.stat().st_mtime
            except OSError:
                continue
            if m > newest_m:
                newest_m, newest = m, p
        if newest is None:
            return {"verdict": OFFLINE, "evidence": ["no rollout files"]}
        age_s = _now() - newest_m
        # §4/§5: a usage-limit task_complete in the newest rollout means
        # Codex is in QUOTA COOLDOWN — read the LIVE reset time from the
        # error text ('try again at 2:59 PM'), never a remembered limit.
        cooldown = parse_codex_cooldown(newest)
        if cooldown:
            remaining = cooldown["resets_in_s"]
            reset_evidence = (f"{remaining:.0f}s" if remaining is not None
                              else "reset time unknown")
            return {"verdict": WAITING_FOR_QUOTA,
                    "evidence": [f"usage_limit_exceeded; resets "
                                 f"{cooldown['reset_at']} "
                                 f"({reset_evidence}) "
                                 f"[{newest.name}]"],
                    "quota": {"pool": "five_hour",
                              "reset_at": cooldown["reset_at"],
                              "resets_in_s": cooldown["resets_in_s"]}}
        verdict = RUNNING if age_s <= self.liveness_window_s else IDLE
        return {"verdict": verdict,
                "evidence": [f"newest rollout {newest.name} "
                             f"{age_s:.0f}s old (window "
                             f"{self.liveness_window_s:.0f}s)"]}

    def send_instruction(self, instruction: str,
                         continue_task: bool = False) -> dict[str, Any]:
        """`codex exec resume --last` continues the EXISTING session (§36:
        Codex may reach the end of a turn before MAT completion — Hermes is
        authorized to explicitly tell Codex to continue; no new external
        information required)."""
        cmd = [self.bin, "exec"]
        if continue_task:
            cmd += ["resume", "--last", instruction]
        else:
            cmd.append(instruction)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=3600.0, shell=False)
            ok = r.returncode == 0
            out = (r.stdout or r.stderr or "")
        except FileNotFoundError:
            try:
                r = subprocess.run(subprocess.list2cmdline(cmd),
                                   capture_output=True, text=True,
                                   timeout=3600.0, shell=True)
                ok = r.returncode == 0
                out = (r.stdout or r.stderr or "")
            except (subprocess.TimeoutExpired, OSError) as e:
                return {"delivered": False, "evidence": [str(e)]}
        except (subprocess.TimeoutExpired, OSError) as e:
            return {"delivered": False, "evidence": [str(e)]}
        return {"delivered": ok, "channel": "codex-exec-resume",
                "evidence": [out[:200] if out else "no output"]}


class OllamaAdapter(WorkerAdapter):
    """§6/§9: a LOCAL model worker (free-first tier). Executes bounded tasks
    via the Ollama HTTP API. Verdict comes from the /api/version probe; a
    model that cannot be reached is OFFLINE with evidence, never fabricated.
    Quota is the free local tier — no allowance window to exhaust."""

    def __init__(self, worker_id: str = "ollama-local",
                 model: str = "qwen2.5-coder:3b-instruct-q4_K_M",
                 base_url: str = "http://127.0.0.1:11434") -> None:
        super().__init__(worker_id=worker_id, application="ollama",
                         role="local-worker")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._last_task = ""

    def status(self) -> dict[str, Any]:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/version")
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                ver = json.loads(resp.read().decode("utf-8")).get("version")
            # local runtime is 'running' when its API answers; it has no
            # session activity, so RUNNING means available-to-serve (§15)
            return {"verdict": RUNNING,
                    "evidence": [f"ollama {ver} serving model "
                                 f"{self.model}"]}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"verdict": OFFLINE,
                    "evidence": [f"ollama unreachable: {e}"]}

    def send_instruction(self, instruction: str,
                         continue_task: bool = False) -> dict[str, Any]:
        """Execute the instruction as a bounded local generation (§11: pick
        real tasks). Returns delivered + the model's actual reply."""
        self._last_task = instruction
        payload = json.dumps({
            "model": self.model,
            "prompt": instruction,
            "stream": False,
        }).encode("utf-8")
        try:
            req = urllib.request.Request(
                f"{self.base_url}/api/generate", data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            reply = (body.get("response") or "").strip()
            return {"delivered": bool(reply), "channel": "ollama-api",
                    "evidence": [reply[:400] if reply else "empty reply"]}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"delivered": False, "evidence": [str(e)]}

    def current_task(self) -> dict[str, Any]:
        return {"task": self._last_task, "evidence": [f"model {self.model}"]}

    def quota_state(self) -> list[QuotaLedgerEntry]:
        # free local tier: no allowance window to exhaust; recorded honestly
        # with quota_remaining=None (UNKNOWN), never an invented number (§38)
        return [QuotaLedgerEntry(worker_id=self.worker_id,
                                 provider="ollama", tier="LOCAL_UNLIMITED",
                                 quota_remaining=None, quota_used=0.0,
                                 quota_unit="local_free", pool=UNKNOWN,
                                 source="ollama-local-runtime")]


# --- the runtime -------------------------------------------------------------------
class SupervisorRuntime:
    """The persistent supervisor (§1-§33). State machine + adapters + the
    durable checkpoint. `run_cycle()` is ONE §33 loop iteration — the chat
    turn may call it directly; the daemon calls it in a loop."""

    def __init__(self, state_dir: str | Path,
                 adapters: Optional[list[WorkerAdapter]] = None,
                 cycle_interval_s: float = 120.0) -> None:
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.cycle_interval_s = cycle_interval_s
        self.supervisor = Supervisor()
        self.hive = HiveScheduler()
        self.governor = ResourceGovernor()
        self.adapters: dict[str, WorkerAdapter] = {}
        self.idle_reasons: dict[str, str] = {}
        self.shift = DAY
        self.continuation_required = True
        self.cycles = 0
        self._stop = threading.Event()
        self._last_actions: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []       # bounded ring
        self._recovered_worker_ids: set[str] = set()
        # §45.8: workers we sent a continue-instruction to whose resumption
        # is NOT yet verified — continuation stays required until they are.
        self._pending_verification: set[str] = set()
        for a in (adapters or []):
            self.register_adapter(a)

    # -- registration (§2, §9) ---------------------------------------------------
    def register_adapter(self, adapter: WorkerAdapter) -> None:
        self.adapters[adapter.worker_id] = adapter
        self.supervisor.register_worker(
            adapter.worker_id, adapter.worker_type, adapter.application,
            adapter.role)
        self._emit("worker.registered", worker=adapter.worker_id,
                   application=adapter.application)

    def _emit(self, event: str, **payload: Any) -> None:
        rec = {"event": event, "timestamp": _now(), **payload}
        self.events.append(rec)
        self.events = self.events[-500:]

    def _supervised_worker_ids(self) -> list[str]:
        """All workers under supervision: registered adapters PLUS every
        worker in the Supervisor registry (including ones recovered from the
        durable checkpoint or whose adapter temporarily vanished — §32: a
        worker is never silently dropped from supervision)."""
        ids = set(self.adapters)
        ids.update(self._recovered_worker_ids)
        ids.update(self.supervisor._workers.keys())
        return sorted(ids)

    # -- one supervision cycle (§33) ----------------------------------------------
    def run_cycle(self) -> dict[str, Any]:
        """OBSERVE ALL WORKERS -> CHECK HEARTBEATS -> READ HANDOFFS ->
        CHECK GIT/TESTS -> CHECK QUOTAS/RESOURCES -> FAST GAP -> ASSIGN ->
        INTERVENE -> CORRECT -> CHECKPOINT. Returns everything that happened
        so the control surface (chat/dashboard) can display it."""
        self.cycles += 1
        actions: dict[str, Any] = {"cycle": self.cycles, "workers": {}}

        for wid, adapter in self.adapters.items():
            st = adapter.status()
            verdict = st.get("verdict", UNKNOWN_VERDICT)
            rec = self.supervisor.worker(wid)
            actions["workers"][wid] = {"verdict": verdict,
                                       "evidence": st.get("evidence", [])}
            if rec is None:
                continue
            if verdict == RUNNING:
                self.supervisor.heartbeat(wid, status="IMPLEMENTING", quota_state={})
                self.idle_reasons.pop(wid, None)
                # §45.8: resumption verified — clear the pending flag
                if wid in self._pending_verification:
                    self._pending_verification.discard(wid)
                    actions["workers"][wid]["resumption_verified"] = True
                    self._emit("worker.resumption_verified", worker=wid)
            elif verdict == IDLE:
                rec.quota_state = {}
                # §6 WORKER COMPLETION EVENT -> SUPERVISOR_CHECKIN (§45)
                self._check_in(wid, adapter, actions)
            elif verdict == WAITING_FOR_QUOTA:
                # §4/§5: Codex cooldown is NOT a programme stop. Emit the
                # capacity event, checkpoint its task/write ownership
                # (KEEP RESERVED — do not reassign mid-write-set), and let
                # the rest of the workforce keep producing. Codex re-enters
                # the pool automatically when its reset arrives.
                quota = st.get("quota", {})
                self.supervisor.heartbeat(wid, status="WAITING_FOR_QUOTA",
                                          quota_state=quota)
                actions["workers"][wid]["capacity_unavailable"] = quota
                self._emit("worker.capacity_unavailable", worker=wid,
                           pool=quota.get("pool", "unknown"),
                           reset_at=quota.get("reset_at"),
                           resets_in_s=quota.get("resets_in_s"))
            elif verdict == STALLED:
                self.supervisor.heartbeat(wid, status="INTERRUPTED")
            # OFFLINE / UNKNOWN: record honestly, do not fabricate health
            elif verdict in (OFFLINE, UNKNOWN_VERDICT):
                self.idle_reasons.setdefault(wid, SUPERVISOR_DEFECT)

        # §11-§14 watchdogs
        actions["watchdogs"] = self._watchdogs()
        # §33 tail: checkpoint every cycle (persist computes the honest
        # continuation flag itself — one computation, never two)
        self.persist()
        self._last_actions = [actions]
        return actions

    def _compute_continuation(self) -> bool:
        """§27/§45.8: the single honest continuation computation. True unless
        NOTHING remains: no unread handoffs, no open gaps, no supervisor
        defects, no in-flight check-in awaiting resumption verification."""
        return bool(
            self.supervisor.unreviewed_handoffs()
            or self.supervisor.open_gaps()
            or any(r == SUPERVISOR_DEFECT
                   for r in self.idle_reasons.values())
            or self._pending_verification)

    def _check_in(self, worker_id: str, adapter: WorkerAdapter,
                  actions: dict[str, Any]) -> None:
        """§45 priority order when a worker stops: determine state -> read
        output/handoff -> determine remaining requirements -> fast gap ->
        decide continuation/correction/new task -> issue instruction."""
        task = adapter.current_task()
        instruction = (
            "CONTINUE THE CURRENT BOUNDED TASK from your latest verified "
            "state. Do not redo completed work. Inspect your current "
            "repository/session first. Continue through implementation, "
            "testing, verification, commit/push and handoff unless a genuine "
            "blocker occurs.")
        result = adapter.send_instruction(instruction, continue_task=True)
        self.supervisor.heartbeat(worker_id, status="ASSIGNED",
                                  task_description=task.get("task", ""))
        if result.get("delivered"):
            self._pending_verification.add(worker_id)   # §45.8
        actions["workers"][worker_id]["check_in"] = {
            "action": "continue_current_task",
            "delivered": result.get("delivered", False),
            "channel": result.get("channel", ""),
            "evidence": result.get("evidence", [])}
        self._emit("worker.check_in", worker=worker_id,
                   delivered=result.get("delivered", False))
        # verify the worker returned to active on the NEXT cycle (§45.8)

    def worker_detail(self, worker_id: str) -> dict[str, Any]:
        """§17.J: one worker's full detail for the control surface — live
        verdict + adapter info + supervision record + current task + quota +
        review state. Reads from the SAME registry the cycle uses, so the UI
        and the daemon never diverge. Honest: an unknown worker is reported
        as unknown, never fabricated."""
        adapter = self.adapters.get(worker_id)
        rec = self.supervisor.worker(worker_id)
        if adapter is None and rec is None:
            return {"ok": False, "error_code": "UNKNOWN_WORKER",
                    "worker_id": worker_id}
        detail: dict[str, Any] = {
            "ok": True, "worker_id": worker_id,
            "application": getattr(adapter, "application", None),
            "role": getattr(adapter, "role", None),
            "verdict": None, "evidence": [],
            "record": rec.to_dict() if rec else None,
            "pending_verification": worker_id in self._pending_verification,
        }
        if adapter is not None:
            try:
                st = adapter.status()
                detail["verdict"] = st.get("verdict")
                detail["evidence"] = st.get("evidence", [])
                if st.get("quota"):
                    detail["quota"] = st["quota"]
                detail["current_task"] = adapter.current_task()
            except Exception as e:  # noqa: BLE001 — never crash the surface
                detail["evidence"] = [f"{type(e).__name__}: {e}"]
        return detail

    def control_continue(self, worker_id: str) -> dict[str, Any]:
        """§18 control surface: the owner/UI tells a worker to CONTINUE its
        current bounded task. Uses the SAME real adapter channel the cycle
        uses (opencode run / codex exec resume --last / ollama generate) —
        no second transport, no fabrication. The result is honest:
        delivered=True only when the adapter actually delivered."""
        adapter = self.adapters.get(worker_id)
        if adapter is None:
            return {"ok": False, "error_code": "UNKNOWN_WORKER",
                    "worker_id": worker_id}
        actions: dict[str, Any] = {"workers": {worker_id: {}}}
        self._check_in(worker_id, adapter, actions)
        ci = actions["workers"][worker_id].get("check_in", {})
        self.persist()
        return {"ok": True, "worker_id": worker_id,
                "delivered": ci.get("delivered", False),
                "channel": ci.get("channel", ""),
                "evidence": ci.get("evidence", [])}

    def _watchdogs(self) -> dict[str, Any]:
        """§11-§14: the runtime's self-checks. A violation is recorded as a
        SUPERVISOR DEFECT — visible, never hidden. Scans ALL supervised
        workers (not just currently-registered adapters): a worker whose
        adapter vanished is exactly the §32 INTERRUPTED case."""
        out: dict[str, Any] = {}
        # §13 handoff queue: no handoff may remain unread
        pending = self.supervisor.unreviewed_handoffs()
        if pending:
            out["handoffs_waiting"] = len(pending)
        # §12 idle without a reason is a supervisor defect
        bad_idle = []
        for w in self._supervised_worker_ids():
            if w in self.idle_reasons:
                continue
            rec = self.supervisor.worker(w)
            if rec is not None and rec.status in (AVAILABLE, "WAITING"):
                bad_idle.append(w)
        if bad_idle:
            out["idle_without_reason"] = bad_idle
            for w in bad_idle:
                self.idle_reasons[w] = SUPERVISOR_DEFECT
        # §34 ready work + available worker = scheduling defect if true
        ready = [t for t in self.hive._tasks.values()
                 if t.task_id not in self.hive._assignments]
        idle_workers = [w for w, r in self.idle_reasons.items()
                        if r != SUPERVISOR_DEFECT]
        if ready and idle_workers:
            out["ready_work_with_idle_workers"] = {
                "ready": len(ready), "idle": idle_workers}
        return out

    # -- durable state (§18, §32) ---------------------------------------------------
    @property
    def checkpoint_path(self) -> Path:
        return self.state_dir / "supervisor_runtime_checkpoint.json"

    def persist(self) -> None:
        """§18: persist EVERYTHING outside model context. continuation_
        required is computed FRESH at persist time (not the last cycle's
        value) so a power-cut checkpoint is always truthful (§27). An
        in-flight check-in (continue instruction sent, resumption NOT yet
        verified) keeps continuation_required True (§45.8)."""
        self.continuation_required = self._compute_continuation()
        data = {
            "cycles": self.cycles,
            "shift": self.shift,
            "continuation_required": self.continuation_required,
            "pending_verification": sorted(self._pending_verification),
            "idle_reasons": self.idle_reasons,
            "last_actions": self._last_actions,
            "events_tail": self.events[-50:],
            "workers": {w: (self.supervisor.worker(w).to_dict()
                            if self.supervisor.worker(w) else None)
                        for w in self.adapters},
            "adapters": {w: {"application": a.application,
                             "role": a.role}
                         for w, a in self.adapters.items()},
            "saved_at": _now(),
        }
        tmp = self.checkpoint_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str),
                       encoding="utf-8")
        tmp.replace(self.checkpoint_path)   # atomic: power-cut safe (§35)

    def recover(self) -> dict[str, Any]:
        """§19 CRASH/POWER-FAILURE RECOVERY: load durable state -> reconcile
        actual processes -> mark stale heartbeats INTERRUPTED -> resume."""
        recovered = {"loaded": False, "workers_reconciled": [],
                     "stale_marked": []}
        if self.checkpoint_path.exists():
            data = json.loads(self.checkpoint_path.read_text(
                encoding="utf-8"))
            self.cycles = data.get("cycles", 0)
            self.shift = data.get("shift", DAY)
            self.idle_reasons = data.get("idle_reasons", {})
            self._pending_verification = set(
                data.get("pending_verification", []))
            recovered["loaded"] = True
            recovered["resumed_continuation_required"] = data.get(
                "continuation_required", True)
            # §32: recovered workers stay supervised even before their
            # adapter re-registers
            for wid, wd in (data.get("workers") or {}).items():
                if wid and wd:
                    self._recovered_worker_ids.add(wid)
                    self.supervisor.register_worker(
                        wid, wd.get("worker_type", "EXTERNAL_AI_AGENT"),
                        wd.get("application", ""), wd.get("role", ""))
                    self.supervisor.worker(wid).status = wd.get(
                        "status", "AVAILABLE")
        for wid in self.adapters:
            rec = self.supervisor.worker(wid)
            if rec is not None and (_now() - rec.last_heartbeat) > \
                    self.cycle_interval_s * 3:
                rec.status = "INTERRUPTED"
                recovered["stale_marked"].append(wid)
            recovered["workers_reconciled"].append(wid)
        self._emit("runtime.recovered", **recovered)
        return recovered

    # -- daemon (§4: event-driven where possible, no busy-loop) ---------------------
    def acquire_instance_lock(self) -> bool:
        """§2 single-instance protection: exactly ONE Supervisor Runtime per
        state-dir. A stale lock (dead pid) is reclaimed. Returns False when
        another live instance owns the lock — the caller must exit rather
        than run a duplicate supervisor."""
        lock_path = self.state_dir / "supervisor.lock"
        self._lock_path = lock_path
        try:
            if lock_path.exists():
                try:
                    other = json.loads(lock_path.read_text(
                        encoding="utf-8"))
                    other_pid = int(other.get("pid", -1))
                except (ValueError, json.JSONDecodeError):
                    other_pid = -1
                # another live OS process owns it -> refuse. A stale lock
                # (dead pid, or a pid that is merely this same process
                # testing itself) is reclaimed.
                if other_pid > 0 and other_pid != os.getpid() and \
                        _pid_alive(other_pid) and not \
                        self._is_self_test_lock(other_pid):
                    return False      # a live supervisor owns this state
            tmp = lock_path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "pid": os.getpid(),
                "acquired_at": _now(),
                "adapters": sorted(self.adapters),
            }), encoding="utf-8")
            tmp.replace(lock_path)
            return True
        except OSError:
            return True   # lock unwritable: proceed (single-host assumption)

    def release_instance_lock(self) -> None:
        lock_path = getattr(self, "_lock_path", None)
        if lock_path and lock_path.exists():
            try:
                data = json.loads(lock_path.read_text(encoding="utf-8"))
                if data.get("pid") == os.getpid():
                    lock_path.unlink()
            except (OSError, json.JSONDecodeError):
                pass

    @staticmethod
    def _is_self_test_lock(pid: int) -> bool:
        """A lock written by THIS SAME OS process (unit tests construct two
        runtimes in one process) is not a competing supervisor — the real
        cross-process guarantee comes from the distinct-pid + liveness check
        in acquire_instance_lock."""
        return pid == os.getpid()

    def run_forever(self) -> None:  # pragma: no cover - daemon loop
        """§33/§48: the loop runs until STOPPED (signal or explicit stop) —
        NEVER until continuation_required happens to be False. A quiet cycle
        (all workers running, nothing pending) is a HEALTHY state to keep
        watching, not a reason to exit; the next idle worker must still be
        caught (§7: 'OpenCode must remain registered after task assignment').
        """
        if not self.acquire_instance_lock():
            self._emit("runtime.duplicate_instance_refused",
                       pid=os.getpid())
            return
        self.recover()
        self._install_signal_handlers()
        try:
            while not self._stop.is_set():
                try:
                    self.run_cycle()
                except Exception as e:  # noqa: BLE001 — §24 failure != stop
                    self._emit("runtime.cycle_error", error=str(e))
                self._stop.wait(self.cycle_interval_s)
        finally:
            self.persist()   # §32: persist before any boundary
            self.release_instance_lock()

    def _install_signal_handlers(self) -> None:  # pragma: no cover
        def _handler(signum: int, frame: Any) -> None:
            self._stop.set()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handler)
            except (ValueError, OSError):
                pass   # not main thread / unsupported platform

    # -- status for the control surface (§26) ----------------------------------------
    def status(self) -> dict[str, Any]:
        return {
            "cycles": self.cycles,
            "shift": self.shift,
            "continuation_required": self.continuation_required,
            "adapters": {w: self.adapters[w].status()["verdict"]
                         for w in self.adapters},
            "idle_reasons": dict(self.idle_reasons),
            "handoffs_pending": len(self.supervisor.unreviewed_handoffs()),
            "gaps_open": len(self.supervisor.open_gaps()),
            "supervision": self.supervisor.overview(),
            "resources": self.governor.overview()["pressure_state"],
            "checkpoint": str(self.checkpoint_path),
        }


def main(argv: Optional[list[str]] = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Aetherius Supervisor "
                                     "Runtime (persistent, §1-§33)")
    parser.add_argument("--state-dir", default="supervisor_state")
    parser.add_argument("--interval", type=float, default=120.0)
    parser.add_argument("--once", action="store_true",
                        help="run a single cycle and exit (testable)")
    parser.add_argument("--status", action="store_true",
                        help="print the durable checkpoint and exit")
    parser.add_argument("--with-opencode", action="store_true")
    parser.add_argument("--with-codex", action="store_true")
    parser.add_argument("--with-ollama", action="store_true",
                        help="register the local Ollama model worker "
                             "(free-first tier, §6)")
    parser.add_argument("--ollama-model", default=
                        "qwen2.5-coder:3b-instruct-q4_K_M")
    parser.add_argument("--watchdog", action="store_true",
                        help="run as the persistence watchdog (§2): ensure "
                             "exactly one Supervisor Runtime is alive, "
                             "restart it if not. Does NO project work.")
    args = parser.parse_args(argv)

    if args.watchdog:
        return _watchdog_loop(args)

    adapters: list[WorkerAdapter] = []
    if args.with_opencode:
        adapters.append(OpenCodeAdapter())
    if args.with_codex:
        adapters.append(CodexAdapter())
    if args.with_ollama:
        adapters.append(OllamaAdapter(model=args.ollama_model))
    runtime = SupervisorRuntime(args.state_dir, adapters=adapters,
                                cycle_interval_s=args.interval)

    if args.status:
        print(json.dumps(runtime.status(), indent=2, default=str))
        return 0
    if args.once:
        print(json.dumps(runtime.run_cycle(), indent=2, default=str))
        return 0
    runtime.run_forever()
    return 0


def _watchdog_loop(args: Any) -> int:  # pragma: no cover - daemon
    """§2 PERSISTENCE WATCHDOG: the supervisor-of-the-supervisor. Its ONLY
    job is that the Supervisor Runtime exists. It performs no project
    engineering. Architecture:

        WINDOWS -> WATCHDOG -> SUPERVISOR RUNTIME -> WORKER POOL

    Cycle: is the supervisor process alive? YES -> leave it alone.
    NO -> read the last checkpoint -> relaunch the runtime detached ->
    continue. Single-instance is enforced by the runtime's own lock, so a
    race between watchdog and a manual start cannot produce duplicates.
    """
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    lock_path = state_dir / "supervisor.lock"
    script = Path(__file__).resolve()
    repo_root = script.parent.parent
    stop = threading.Event()

    def _handler(signum: int, frame: Any) -> None:
        stop.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass

    while not stop.is_set():
        pid = None
        if lock_path.exists():
            try:
                pid = int(json.loads(lock_path.read_text(
                    encoding="utf-8")).get("pid", -1))
            except (ValueError, json.JSONDecodeError, OSError):
                pid = -1
        if pid is None or not _pid_alive(pid):
            # supervisor is gone -> relaunch it DETACHED so it survives the
            # watchdog's own death and any parent turn ending (§3)
            cmd = [sys.executable, str(script),
                   "--with-opencode", "--with-codex", "--with-ollama",
                   "--state-dir", str(state_dir),
                   "--interval", str(args.interval)]
            try:
                subprocess.Popen(
                    cmd, cwd=str(repo_root),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    creationflags=getattr(subprocess,
                                          "DETACHED_PROCESS", 0)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                _watchdog_log(state_dir, f"supervisor relaunched "
                                         f"(was pid {pid})")
            except OSError as e:
                _watchdog_log(state_dir, f"relaunch failed: {e}")
        stop.wait(max(30.0, args.interval / 2))
    return 0


def _watchdog_log(state_dir: Path, msg: str) -> None:
    """Append-only watchdog journal — power-cut readable, never rewritten."""
    try:
        with (state_dir / "watchdog.log").open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
