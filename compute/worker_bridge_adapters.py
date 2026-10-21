"""Aetherius Agent Communications Bridge — worker adapter interface (§12).

The bridge asks the adapter to:
  discover() → connect() → send_message() → read_messages() →
  acknowledge() → status() → heartbeat() → cancel() → pause() →
  resume() → change_model_if_supported() → quota() → health()

The adapter selects the best actual control mechanism (§13 transport fallback).
GUI is FALLBACK TRANSPORT, not the semantic protocol (§13).
"""
from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from compute.agent_message import (
    AgentMessage,
    Capability,
    DeliveryState,
    Intent,
)


# --- adapter interface (§12) ------------------------------------------------------------

class WorkerAdapterInterface(ABC):
    """The contract every worker adapter implements (§12).

    OpenCode, Codex, Hermes subagents, GUI apps, cloud workers all
    implement this interface. The bridge speaks the same protocol to
    all of them (§33).
    """

    def __init__(self, worker_id: str, agent_id: str):
        self.worker_id = worker_id
        self.agent_id = agent_id
        self.capabilities: list[Capability] = []
        self.current_model: str = ""
        self.current_session_id: str = ""
        self.delivery_state: DeliveryState = DeliveryState.PENDING
        self.last_heartbeat: float = 0.0

    # -- discovery + connection (§12) ------------------------------------------

    @abstractmethod
    def discover(self) -> dict[str, Any]:
        """Discover the worker's current state (sessions, process, etc.).
        Returns honest facts — never fabricated availability (§3)."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish a connection. Returns True if reachable."""

    # -- messaging (§12) ---------------------------------------------------------

    @abstractmethod
    def send_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Send a message through the best available transport (§13).
        Returns {"delivered": bool, "channel": str, "evidence": [...]}."""

    @abstractmethod
    def read_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent messages/activity from the worker's session."""

    @abstractmethod
    def acknowledge(self, msg: AgentMessage) -> bool:
        """Check if the worker has ACKed a specific message (§7).
        Searches worker transcript/state for the task_id (§15)."""

    # -- status + heartbeat (§12, §9) ---------------------------------------------

    @abstractmethod
    def status(self) -> dict[str, Any]:
        """Current worker status: session, model, task, delivery state."""

    def heartbeat(self) -> dict[str, Any]:
        """Lightweight heartbeat (§9)."""
        self.last_heartbeat = time.time()
        return {
            "worker_id": self.worker_id,
            "agent_id": self.agent_id,
            "last_heartbeat": self.last_heartbeat,
            "delivery_state": self.delivery_state.value,
            "current_model": self.current_model,
        }

    # -- control (§12, §23) ---------------------------------------------------------

    @abstractmethod
    def cancel(self) -> bool:
        """CANCEL the current task (§23)."""

    @abstractmethod
    def pause(self) -> bool:
        """PAUSE the current task (§23)."""

    @abstractmethod
    def resume(self) -> bool:
        """RESUME a paused task (§23)."""

    def change_model_if_supported(self, model: str) -> bool:
        """Change the worker's model. Default: not supported (§12)."""
        return False

    def quota(self) -> dict[str, Any]:
        """Quota state for this worker. Default: unknown."""
        return {"worker_id": self.worker_id, "quota_state": "UNKNOWN"}

    def health(self) -> dict[str, Any]:
        """Health check: is the adapter actually functional?"""
        return {
            "worker_id": self.worker_id,
            "agent_id": self.agent_id,
            "healthy": True,
            "capabilities": [c.value for c in self.capabilities],
        }


# --- OpenCode adapter (§13, §J) -----------------------------------------------------------

class OpenCodeAdapter(WorkerAdapterInterface):
    """OpenCode worker adapter using the CLI channel (§13 transport #3).

    Transport priority (§13):
    1. native API/protocol — not available in OpenCode 1.18.30
    2. MCP/A2A — opencode.json wires hermes MCP serve, but not a direct A2A channel
    3. OpenCode CLI/session interface — USED HERE: `opencode session`, `opencode db`, `opencode run`
    4. supported local DB/session control — `opencode db` SQLite channel
    5. plugin/extension bridge — not implemented yet
    6. accessibility automation — GUI fallback (not used here)
    7. Win32/browser automation — GUI fallback
    8. clipboard + keyboard — GUI fallback

    The adapter uses `opencode run` for headless task delivery (§13 CLI channel)
    and `opencode db` for telemetry verification.
    """

    def __init__(self, worker_id: str = "opencode-01",
                 opencode_bin: str = "C:/Users/jpowe/AppData/Roaming/npm/opencode.cmd",
                 model: str = "nemotron-3-ultra-free"):
        super().__init__(worker_id, "opencode")
        self.bin = opencode_bin
        self.current_model = model
        self.capabilities = [
            Capability.CODING,
            Capability.FILES,
            Capability.TERMINAL,
            Capability.MODELS,
            Capability.TOOL_CALLS,
            Capability.STREAMING,
        ]

    def _run_cli(self, args: list[str], timeout: float = 30.0) -> tuple[bool, str]:
        """Run an opencode CLI command."""
        try:
            p = subprocess.run([self.bin] + args,
                               capture_output=True, text=True,
                               timeout=timeout, shell=True)
            return p.returncode == 0, (p.stdout or p.stderr or "")
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, str(e)

    def discover(self) -> dict[str, Any]:
        """Discover OpenCode sessions via `opencode session list` (§13)."""
        ok, out = self._run_cli(["session", "list"])
        if not ok:
            return {"status": "OFFLINE", "evidence": [f"session list failed: {out[:100]}"]}
        lines = [l.strip() for l in out.strip().split("\n") if l.strip() and "─" not in l and "Session ID" not in l]
        return {
            "status": "AVAILABLE",
            "sessions": len(lines),
            "evidence": [f"opencode session list returned {len(lines)} sessions"],
        }

    def connect(self) -> bool:
        """Check if OpenCode is reachable via CLI."""
        ok, out = self._run_cli(["--version"])
        return ok

    def send_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Send a TASK_ASSIGN via `opencode run` (headless CLI channel).

        This is transport #3 in the fallback chain (§13). It starts a
        HEADLESS session — it does NOT resume the GUI composer session.

        For TASK_ASSIGN: runs `opencode run --model <model> --dir <repo> <prompt>`
        where the prompt includes the task_id for receiver-side verification (§15).

        Returns {"delivered": bool, "channel": str, "evidence": [...]}
        """
        if msg.intent == Intent.TASK_ASSIGN:
            return self._send_task_assign(msg)
        elif msg.intent == Intent.CANCEL:
            return {"delivered": False, "channel": "cli",
                    "evidence": ["cancel not supported via headless CLI"]}
        elif msg.intent == Intent.HEARTBEAT:
            return {"delivered": True, "channel": "cli",
                    "evidence": ["heartbeat is local-only"]}
        else:
            return {"delivered": False, "channel": "cli",
                    "evidence": [f"intent {msg.intent.value} not supported via CLI"]}

    def _send_task_assign(self, msg: AgentMessage) -> dict[str, Any]:
        """Deliver a task via `opencode run` with the COMPLETE worker brief (§14).

        The brief is rendered automatically from the canonical envelope —
        Hermes never invents a prompt manually (§14). The task_id is embedded
        for receiver-side verification (§15).
        """
        repo = msg.constraints.get("worktree") or msg.constraints.get("repo") or ""
        prompt = self.render_for_worker(msg)
        cmd = [self.bin, "run", "--model", self.current_model]
        if repo:
            cmd.extend(["--dir", repo])
        cmd.append(prompt)

        try:
            p = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=msg.delivery_timeout_s, shell=True)
            output = (p.stdout or "") + (p.stderr or "")
            if p.returncode == 0:
                return {
                    "delivered": True,
                    "channel": "opencode-run (headless CLI)",
                    "evidence": [
                        "opencode run exited 0",
                        f"task_id in output: {msg.task_id in output}",
                    ],
                    "output": output[:2000],
                }
            return {
                "delivered": False,
                "channel": "opencode-run (headless CLI)",
                "evidence": [f"opencode run exited {p.returncode}: {output[:200]}"],
            }
        except subprocess.TimeoutExpired:
            return {
                "delivered": False,
                "channel": "opencode-run (headless CLI)",
                "evidence": [f"timed out after {msg.delivery_timeout_s}s"],
            }

    def render_for_worker(self, msg: AgentMessage) -> str:
        """Render the canonical envelope into a COMPLETE worker brief (§14).

        This is the fix for the "reply to this test task" failure: the brief
        carries everything the worker needs — objective, context, repo,
        worktree, baseline, write-set, acceptance, permissions, cost policy,
        evidence refs. A control nudge is NEVER sufficient (§14).
        """
        c = msg.constraints
        evidence_refs = "\n".join(f"  - {r}" for r in msg.evidence_refs) or "  (none)"
        write_set = "\n".join(f"  - {f}" for f in c.get("write_set", [])) or "  (none)"
        deps = "\n".join(f"  - {d}" for d in msg.dependencies) or "  (none)"
        actions = "\n".join(f"  - {a}" for a in msg.requested_actions) or \
            "  - ACK task ID, then TASK_START, then implement, then TASK_COMPLETE"

        return f"""TASK_ID: {msg.task_id}
PROJECT: {msg.project_id or "Agent-Bridge"}
PRIORITY: {msg.priority}
COST_POLICY: {c.get("cost_policy", "ZERO_INCREMENTAL_SPEND")}
BRANCH: {c.get("branch", "") or "(current branch)"}
WORKTREE/REPO: {c.get("worktree") or c.get("repo", "") or "(current directory)"}
BASELINE: {c.get("baseline_sha") or "(current HEAD)"}

OBJECTIVE:
{msg.objective}

WRITE_SET (only these files may be created/modified):
{write_set}

DEPENDENCIES:
{deps}

REQUESTED ACTIONS:
{actions}

PERMISSIONS: {c.get("permissions", []) or "(none beyond write-set)"}

EVIDENCE REFS:
{evidence_refs}

PROTOCOL REQUIREMENTS:
1. First reply with: ACK TASK_ID={msg.task_id}
2. Then reply with: TASK_START TASK_ID={msg.task_id}
3. Do the work described above.
4. Then reply with: TASK_COMPLETE TASK_ID={msg.task_id} followed by a HANDOFF
   summary containing: files changed, tests run, results, commit SHA, gaps.
5. Do NOT ask the owner anything. Routine authorised engineering does not
   require approval. Work autonomously to completion.
"""

    def read_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent sessions via `opencode session list`."""
        ok, out = self._run_cli(["session", "list"])
        if not ok:
            return []
        lines = [l.strip() for l in out.strip().split("\n")
                 if l.strip() and "─" not in l and "Session ID" not in l]
        sessions = []
        for line in lines[:limit]:
            parts = line.split()
            if len(parts) >= 2:
                sessions.append({
                    "session_id": parts[0],
                    "title": " ".join(parts[1:-2]) if len(parts) > 3 else "",
                    "updated": parts[-1] if len(parts) >= 2 else "",
                })
        return sessions

    def acknowledge(self, msg: AgentMessage) -> bool:
        """Check if OpenCode has ACKed a task by searching its transcript (§15).

        Searches the freshest OpenCode session for the task_id. This is the
        receiver-side evidence required for DELIVERY_VERIFIED (§15).
        """
        # Get the freshest session
        ok, out = self._run_cli(
            ["db", "SELECT id,time_updated FROM session "
                   "ORDER BY time_updated DESC LIMIT 1"])
        if not ok or not out.strip():
            return False
        lines = out.strip().split("\n")
        if len(lines) < 2:
            return False
        session_id = lines[1].split("\t")[0].strip()

        # Export the session and search for task_id
        ok, out = self._run_cli(["export", session_id])
        if not ok:
            return False
        return msg.task_id in out

    def status(self) -> dict[str, Any]:
        """Current OpenCode status via `opencode db`."""
        ok, out = self._run_cli(
            ["db", "SELECT id,title,agent,time_updated FROM session "
                   "ORDER BY time_updated DESC LIMIT 1"])
        if not ok:
            return {"status": "OFFLINE", "worker_id": self.worker_id}
        lines = out.strip().split("\n")
        if len(lines) < 2:
            return {"status": "AVAILABLE", "worker_id": self.worker_id,
                    "evidence": ["no sessions"]}
        parts = lines[1].split("\t")
        return {
            "status": "AVAILABLE",
            "worker_id": self.worker_id,
            "session_id": parts[0] if len(parts) > 0 else "",
            "title": parts[1] if len(parts) > 1 else "",
            "agent": parts[2] if len(parts) > 2 else "",
            "time_updated": parts[3] if len(parts) > 3 else "",
        }

    def cancel(self) -> bool:
        """Cancel: not directly supported via CLI. Honest limitation (§13)."""
        return False

    def pause(self) -> bool:
        """Pause: not supported via CLI. Honest limitation."""
        return False

    def resume(self) -> bool:
        """Resume: not supported via CLI. Honest limitation."""
        return False

    def quota(self) -> dict[str, Any]:
        """OpenCode quota: unknown from CLI. Honest."""
        return {"worker_id": self.worker_id, "agent_id": "opencode",
                "quota_state": "UNKNOWN",
                "evidence": ["opencode CLI does not expose quota"]}


# --- Codex adapter (§31, §K) ---------------------------------------------------------------

class CodexAdapter(WorkerAdapterInterface):
    """Codex worker adapter using the rollout-JSONL + `codex exec resume` channel.

    Transport priority (§13, adapted for Codex):
    1. native API — not available
    2. MCP/A2A — not available
    3. CLI/session interface — `codex exec resume --last` (session continuation)
    4. local DB/session control — rollout JSONL at ~/.codex/sessions/
    5-8. GUI fallback

    Instruction delivery via `codex exec resume --last` — the session-
    continuation channel (§36: continue the EXISTING session, don't start new).
    """

    def __init__(self, worker_id: str = "codex-01",
                 codex_home: str = "~/.codex",
                 model: str = ""):
        super().__init__(worker_id, "codex")
        self.home = Path(codex_home).expanduser()
        self.current_model = model
        self.capabilities = [
            Capability.CODING,
            Capability.FILES,
            Capability.TERMINAL,
            Capability.TOOL_CALLS,
            Capability.MODELS,
        ]

    def discover(self) -> dict[str, Any]:
        """Discover Codex sessions via rollout JSONL."""
        sessions_root = self.home / "sessions"
        if not sessions_root.is_dir():
            return {"status": "OFFLINE",
                    "evidence": [f"no sessions dir at {sessions_root}"]}
        rollouts = list(sessions_root.rglob("rollout-*.jsonl"))
        return {
            "status": "AVAILABLE",
            "sessions": len(rollouts),
            "evidence": [f"found {len(rollouts)} rollout files"],
        }

    def connect(self) -> bool:
        """Check if Codex CLI is available."""
        try:
            p = subprocess.run(["codex", "--version"],
                               capture_output=True, text=True, timeout=10)
            return p.returncode == 0
        except (subprocess.TimeoutExpired, OSError):
            return False

    def send_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Send a TASK_ASSIGN via `codex exec resume --last` (§31).

        This continues the EXISTING session. Quota state participates (§31):
        if Codex is in cooldown, delivery fails honestly.
        """
        if msg.intent == Intent.TASK_ASSIGN:
            return self._send_task_assign(msg)
        elif msg.intent == Intent.CANCEL:
            return {"delivered": False, "channel": "codex-exec",
                    "evidence": ["cancel not supported via exec"]}
        else:
            return {"delivered": False, "channel": "codex-exec",
                    "evidence": [f"intent {msg.intent.value} not supported"]}

    def _send_task_assign(self, msg: AgentMessage) -> dict[str, Any]:
        """Deliver a task via `codex exec resume --last` with task_id in prompt."""
        prompt = (
            f"TASK_ID: {msg.task_id}\n"
            f"PROJECT: {msg.project_id}\n"
            f"OBJECTIVE: {msg.objective}\n"
            f"COST_POLICY: {msg.constraints.get('cost_policy', 'ZERO_INCREMENTAL_SPEND')}\n"
            f"\nAcknowledge with: ACK TASK_ID={msg.task_id}\n"
        )
        try:
            p = subprocess.run(
                ["codex", "exec", "resume", "--last", prompt],
                capture_output=True, text=True,
                timeout=msg.delivery_timeout_s)
            output = (p.stdout or "") + (p.stderr or "")
            if p.returncode == 0:
                return {
                    "delivered": True,
                    "channel": "codex exec resume --last",
                    "evidence": [
                        f"codex exec exited 0",
                        f"output contains task_id: {msg.task_id in output}",
                    ],
                    "output": output[:2000],
                }
            else:
                return {
                    "delivered": False,
                    "channel": "codex exec resume --last",
                    "evidence": [f"exited {p.returncode}: {output[:200]}"],
                }
        except subprocess.TimeoutExpired:
            return {
                "delivered": False,
                "channel": "codex exec resume --last",
                "evidence": [f"timed out after {msg.delivery_timeout_s}s"],
            }

    def read_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent Codex rollout sessions."""
        sessions_root = self.home / "sessions"
        if not sessions_root.is_dir():
            return []
        rollouts = sorted(sessions_root.rglob("rollout-*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        sessions = []
        for r in rollouts[:limit]:
            sessions.append({
                "file": str(r),
                "modified": r.stat().st_mtime,
                "session_id": r.stem,
            })
        return sessions

    def acknowledge(self, msg: AgentMessage) -> bool:
        """Check if Codex ACKed by searching the newest rollout for task_id."""
        sessions_root = self.home / "sessions"
        if not sessions_root.is_dir():
            return False
        rollouts = sorted(sessions_root.rglob("rollout-*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if not rollouts:
            return False
        # Check the newest rollout for the task_id
        try:
            content = rollouts[0].read_text(encoding="utf-8")
            return msg.task_id in content
        except OSError:
            return False

    def status(self) -> dict[str, Any]:
        """Current Codex status."""
        sessions_root = self.home / "sessions"
        if not sessions_root.is_dir():
            return {"status": "OFFLINE", "worker_id": self.worker_id}
        rollouts = sorted(sessions_root.rglob("rollout-*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if not rollouts:
            return {"status": "AVAILABLE", "worker_id": self.worker_id,
                    "evidence": ["no rollouts"]}
        newest = rollouts[0]
        age_s = time.time() - newest.stat().st_mtime
        return {
            "status": "AVAILABLE",
            "worker_id": self.worker_id,
            "newest_rollout": str(newest),
            "age_s": round(age_s, 1),
        }

    def cancel(self) -> bool:
        """Cancel: not supported via exec. Honest."""
        return False

    def pause(self) -> bool:
        """Pause: not supported via exec. Honest."""
        return False

    def resume(self) -> bool:
        """Resume: not supported via exec. Honest."""
        return False

    def quota(self) -> dict[str, Any]:
        """Codex quota: parse cooldown from rollout if present (§31)."""
        sessions_root = self.home / "sessions"
        if not sessions_root.is_dir():
            return {"worker_id": self.worker_id, "quota_state": "UNKNOWN"}
        rollouts = sorted(sessions_root.rglob("rollout-*.jsonl"),
                          key=lambda p: p.stat().st_mtime, reverse=True)
        if not rollouts:
            return {"worker_id": self.worker_id, "quota_state": "UNKNOWN"}
        try:
            content = rollouts[0].read_text(encoding="utf-8")
            if "usage_limit" in content.lower() or "cooldown" in content.lower():
                return {"worker_id": self.worker_id, "quota_state": "COOLDOWN",
                        "evidence": ["newest rollout contains usage limit"]}
            return {"worker_id": self.worker_id, "quota_state": "AVAILABLE"}
        except OSError:
            return {"worker_id": self.worker_id, "quota_state": "UNKNOWN"}


# --- internal Hermes subagent adapter (§32, §L) --------------------------------------------

class InternalAgentAdapter(WorkerAdapterInterface):
    """Internal Hermes subagent adapter (§32).

    Uses the SAME protocol internally (§32: "Hermes should not have one
    supervision system for external apps and another for its own subagents").

    Transport: in-process queue (delegate_task equivalent). The adapter
    wraps the existing Hermes delegation mechanism with the bridge protocol.
    """

    def __init__(self, worker_id: str = "hermes-subagent-01",
                 subagent_func: Optional[Any] = None):
        super().__init__(worker_id, "hermes")
        self._subagent_func = subagent_func  # delegate_task equivalent
        self.capabilities = [
            Capability.CODING,
            Capability.RESEARCH,
            Capability.FILES,
            Capability.TERMINAL,
            Capability.SUBAGENTS,
            Capability.TOOL_CALLS,
        ]

    def discover(self) -> dict[str, Any]:
        """Internal agent: always available if the subagent function is set."""
        return {
            "status": "AVAILABLE" if self._subagent_func else "NO_FUNC",
            "worker_id": self.worker_id,
            "evidence": ["in-process adapter"],
        }

    def connect(self) -> bool:
        """In-process: always connected if function is available."""
        return self._subagent_func is not None

    def send_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Send a TASK_ASSIGN to an internal subagent via delegate_task."""
        if msg.intent != Intent.TASK_ASSIGN:
            return {"delivered": False, "channel": "in-process",
                    "evidence": [f"intent {msg.intent.value} not supported"]}
        if not self._subagent_func:
            return {"delivered": False, "channel": "in-process",
                    "evidence": ["no subagent function configured"]}

        prompt = (
            f"TASK_ID: {msg.task_id}\n"
            f"OBJECTIVE: {msg.objective}\n"
            f"PROJECT: {msg.project_id}\n"
            f"COST_POLICY: {msg.constraints.get('cost_policy', 'ZERO_INCREMENTAL_SPEND')}\n"
        )
        try:
            # Call the subagent function (delegate_task equivalent)
            result = self._subagent_func(prompt)
            return {
                "delivered": True,
                "channel": "in-process (Hermes subagent)",
                "evidence": [f"subagent returned: {str(result)[:200]}"],
                "output": str(result)[:2000],
            }
        except Exception as e:
            return {
                "delivered": False,
                "channel": "in-process",
                "evidence": [f"subagent error: {str(e)[:200]}"],
            }

    def read_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Internal agent: messages are in the Hermes session. Honest: not accessible here."""
        return []

    def acknowledge(self, msg: AgentMessage) -> bool:
        """Internal agent: ACK is synchronous (send_message returns the result)."""
        return True  # in-process delivery is synchronous

    def status(self) -> dict[str, Any]:
        """Internal agent status."""
        return {
            "status": "AVAILABLE" if self._subagent_func else "NO_FUNC",
            "worker_id": self.worker_id,
            "agent_id": "hermes",
        }

    def cancel(self) -> bool:
        """Cancel: not supported for in-process (synchronous)."""
        return False

    def pause(self) -> bool:
        """Pause: not supported for in-process (synchronous)."""
        return False

    def resume(self) -> bool:
        """Resume: not supported for in-process (synchronous)."""
        return False


# --- generic GUI-agent adapter (§14, §M) -----------------------------------------------------

class GuiAgentAdapter(WorkerAdapterInterface):
    """Generic GUI-agent adapter (§14, §M).

    When an app is GUI-only, the adapter:
    1. Translates Aetherius message to a human prompt (§14)
    2. Inserts into the app (via GUI automation)
    3. Sends
    4. Verifies transcript (receiver-side evidence §15)
    5. Converts worker response back to typed event (§14)

    This is the FALLBACK TRANSPORT (§13). GUI automation is NOT the semantic
    protocol — it's just how we reach GUI-only apps.
    """

    def __init__(self, worker_id: str, agent_id: str,
                 gui_send_func: Optional[Any] = None,
                 gui_read_func: Optional[Any] = None):
        super().__init__(worker_id, agent_id)
        self._gui_send = gui_send_func   # function(prompt: str) -> bool
        self._gui_read = gui_read_func   # function() -> str (transcript text)
        self.capabilities = [
            Capability.CODING,
            Capability.FILES,
        ]

    def discover(self) -> dict[str, Any]:
        """Check if the GUI automation functions are configured."""
        return {
            "status": "AVAILABLE" if self._gui_send else "NO_GUI_FUNC",
            "worker_id": self.worker_id,
            "evidence": ["GUI fallback transport"],
        }

    def connect(self) -> bool:
        """GUI adapter: connected if send function is available."""
        return self._gui_send is not None

    def send_message(self, msg: AgentMessage) -> dict[str, Any]:
        """Send via GUI automation (§14 wrapper)."""
        if msg.intent != Intent.TASK_ASSIGN:
            return {"delivered": False, "channel": "gui",
                    "evidence": [f"intent {msg.intent.value} not supported via GUI"]}
        if not self._gui_send:
            return {"delivered": False, "channel": "gui",
                    "evidence": ["no GUI send function configured"]}

        # Build human-readable prompt with task_id for verification (§14, §15)
        prompt = (
            f"TASK_ID: {msg.task_id}\n"
            f"OBJECTIVE: {msg.objective}\n"
            f"PROJECT: {msg.project_id}\n"
        )
        try:
            sent = self._gui_send(prompt)
            if sent:
                # Verify receipt: search transcript for task_id (§15)
                verified = False
                if self._gui_read:
                    transcript = self._gui_read()
                    verified = msg.task_id in transcript
                return {
                    "delivered": True,
                    "channel": "gui-automation (fallback transport)",
                    "evidence": [
                        f"GUI send returned True",
                        f"task_id in transcript: {verified}",
                    ],
                    "delivery_verified": verified,
                }
            else:
                return {
                    "delivered": False,
                    "channel": "gui-automation",
                    "evidence": ["GUI send returned False"],
                }
        except Exception as e:
            return {
                "delivered": False,
                "channel": "gui-automation",
                "evidence": [f"GUI error: {str(e)[:200]}"],
            }

    def read_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read GUI transcript via the configured read function."""
        if not self._gui_read:
            return []
        try:
            transcript = self._gui_read()
            return [{"transcript": transcript[:5000]}]
        except Exception:
            return []

    def acknowledge(self, msg: AgentMessage) -> bool:
        """Check GUI transcript for task_id (§15 delivery verification)."""
        if not self._gui_read:
            return False
        try:
            transcript = self._gui_read()
            return msg.task_id in transcript
        except Exception:
            return False

    def status(self) -> dict[str, Any]:
        """GUI agent status."""
        return {
            "status": "AVAILABLE" if self._gui_send else "NO_GUI_FUNC",
            "worker_id": self.worker_id,
            "agent_id": self.agent_id,
        }

    def cancel(self) -> bool:
        """Cancel via GUI: not supported generically. Honest."""
        return False

    def pause(self) -> bool:
        """Pause via GUI: not supported generically. Honest."""
        return False

    def resume(self) -> bool:
        """Resume via GUI: not supported generically. Honest."""
        return False
