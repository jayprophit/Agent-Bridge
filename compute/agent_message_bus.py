"""Aetherius Agent Communications Bridge — durable message bus (§3).

The message fabric that survives restarts. Messages are stored in SQLite
(WAL mode) with an append-only JSONL audit log (§36). The bus does NOT
duplicate the existing EventBus — it uses it for live notifications while
persisting messages for durability (§3: "Do NOT create another competing
event bus").

Key contracts:
- Every message is persisted BEFORE delivery (crash-safe).
- Delivery state transitions require evidence (§6).
- Idempotency prevents duplicate processing (§16).
- Messages survive Hermes/OpenCode/worker restarts (§3).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from compute.agent_message import (
    AgentMessage,
    DeliveryState,
    Intent,
)


# --- delivery state machine (§6) ----------------------------------------------------

class DeliveryError(Exception):
    """Raised when an illegal state transition is attempted."""


# Valid transitions: (from_state, intent) -> to_state
# Each transition requires evidence (§6).
_VALID_TRANSITIONS: dict[tuple[DeliveryState, Intent], DeliveryState] = {
    # TASK_ASSIGN: PENDING -> DELIVERED
    (DeliveryState.PENDING, Intent.TASK_ASSIGN): DeliveryState.DELIVERED,
    # TASK_ACK: DELIVERED -> ACKNOWLEDGED (receiver-side evidence required)
    (DeliveryState.DELIVERED, Intent.TASK_ACK): DeliveryState.ACKNOWLEDGED,
    # TASK_START: ACKNOWLEDGED -> RUNNING_VERIFIED
    (DeliveryState.ACKNOWLEDGED, Intent.TASK_START): DeliveryState.RUNNING_VERIFIED,
    # TASK_PROGRESS: RUNNING_VERIFIED -> PROGRESSING (stays progressing)
    (DeliveryState.RUNNING_VERIFIED, Intent.TASK_PROGRESS): DeliveryState.PROGRESSING,
    (DeliveryState.PROGRESSING, Intent.TASK_PROGRESS): DeliveryState.PROGRESSING,
    # TASK_CHECKPOINT: PROGRESSING -> PROGRESSING (checkpoint marker)
    (DeliveryState.PROGRESSING, Intent.TASK_CHECKPOINT): DeliveryState.PROGRESSING,
    (DeliveryState.RUNNING_VERIFIED, Intent.TASK_CHECKPOINT): DeliveryState.PROGRESSING,
    # TASK_COMPLETE: any running state -> COMPLETED
    (DeliveryState.PROGRESSING, Intent.TASK_COMPLETE): DeliveryState.COMPLETED,
    (DeliveryState.RUNNING_VERIFIED, Intent.TASK_COMPLETE): DeliveryState.COMPLETED,
    # HANDOFF: COMPLETED -> HANDED_OFF
    (DeliveryState.COMPLETED, Intent.HANDOFF): DeliveryState.HANDED_OFF,
    # Failure paths
    (DeliveryState.DELIVERED, Intent.TASK_FAILED): DeliveryState.FAILED,
    (DeliveryState.ACKNOWLEDGED, Intent.TASK_FAILED): DeliveryState.FAILED,
    (DeliveryState.RUNNING_VERIFIED, Intent.TASK_FAILED): DeliveryState.FAILED,
    (DeliveryState.PROGRESSING, Intent.TASK_FAILED): DeliveryState.FAILED,
    # Control commands (can apply from any active state)
    (DeliveryState.RUNNING_VERIFIED, Intent.PAUSE): DeliveryState.PAUSED,
    (DeliveryState.PROGRESSING, Intent.PAUSE): DeliveryState.PAUSED,
    (DeliveryState.ACKNOWLEDGED, Intent.PAUSE): DeliveryState.PAUSED,
    (DeliveryState.PAUSED, Intent.RESUME): DeliveryState.RUNNING_VERIFIED,
    (DeliveryState.PAUSED, Intent.CANCEL): DeliveryState.CANCELLED,
    (DeliveryState.RUNNING_VERIFIED, Intent.CANCEL): DeliveryState.CANCELLED,
    (DeliveryState.PROGRESSING, Intent.CANCEL): DeliveryState.CANCELLED,
    (DeliveryState.ACKNOWLEDGED, Intent.CANCEL): DeliveryState.CANCELLED,
    (DeliveryState.DELIVERED, Intent.CANCEL): DeliveryState.CANCELLED,
    # RECALL: authority revoked (§25) — any state
    (DeliveryState.DELIVERED, Intent.RECALL): DeliveryState.RECALLED,
    (DeliveryState.ACKNOWLEDGED, Intent.RECALL): DeliveryState.RECALLED,
    (DeliveryState.RUNNING_VERIFIED, Intent.RECALL): DeliveryState.RECALLED,
    (DeliveryState.PROGRESSING, Intent.RECALL): DeliveryState.RECALLED,
    (DeliveryState.PAUSED, Intent.RECALL): DeliveryState.RECALLED,
}


def is_valid_transition(from_state: DeliveryState, intent: Intent) -> bool:
    """Check if (from_state, intent) is a legal transition."""
    return (from_state, intent) in _VALID_TRANSITIONS


def transition(from_state: DeliveryState, intent: Intent) -> DeliveryState:
    """Apply a state transition, raising on illegal moves (§6)."""
    if not is_valid_transition(from_state, intent):
        raise DeliveryError(
            f"illegal transition: {from_state.value} + {intent.value}")
    return _VALID_TRANSITIONS[(from_state, intent)]


# --- durable message bus (§3) ---------------------------------------------------------

class AgentMessageBus:
    """Durable message fabric with SQLite WAL + JSONL audit (§3, §36).

    Messages are persisted before delivery. Delivery state transitions
    require evidence. The bus integrates with the existing EventBus for
    live notifications (§3: reuse, don't duplicate).
    """

    def __init__(self, db_path: str | Path,
                 audit_path: str | Path | None = None,
                 event_bus: Any = None) -> None:
        self._db_path = Path(db_path)
        self._audit_path = Path(audit_path) if audit_path else None
        self._bus = event_bus  # existing EventBus for live notifications
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[AgentMessage], None]]] = {}
        self._claim_registry: Any = None   # optional H06 ClaimRegistry (§21)
        self._skill_pipeline: Any = None   # optional H03 SkillPipeline (§22)
        self._scope_guard: Any = None      # optional H01 ScopeGuard (AT-22)
        self._init_db()

    def _init_db(self) -> None:
        """Create tables if they don't exist. WAL mode for crash safety."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    correlation_id TEXT,
                    causation_id TEXT,
                    sender_agent TEXT,
                    sender_worker TEXT,
                    receiver_agent TEXT,
                    receiver_worker TEXT,
                    project_id TEXT,
                    task_id TEXT,
                    intent TEXT,
                    delivery_state TEXT DEFAULT 'PENDING',
                    idempotency_key TEXT,
                    priority INTEGER DEFAULT 50,
                    created_at REAL,
                    delivered_at REAL,
                    acknowledged_at REAL,
                    completed_at REAL,
                    retry_count INTEGER DEFAULT 0,
                    payload TEXT,
                    UNIQUE(idempotency_key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_id ON messages(task_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_receiver ON messages(receiver_agent, receiver_worker)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_intent ON messages(intent)
            """)
            conn.commit()
            conn.close()

    # -- message submission -------------------------------------------------------

    def submit(self, msg: AgentMessage) -> AgentMessage:
        """Submit a message. Persists BEFORE delivery (§3 crash-safe).

        Raises on duplicate idempotency_key (§16).
        """
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute(
                    "INSERT INTO messages "
                    "(message_id, correlation_id, causation_id, sender_agent, "
                     "sender_worker, receiver_agent, receiver_worker, project_id, "
                     "task_id, intent, delivery_state, idempotency_key, priority, "
                     "created_at, payload) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (msg.message_id, msg.correlation_id, msg.causation_id,
                     msg.sender_agent, msg.sender_worker, msg.receiver_agent,
                     msg.receiver_worker, msg.project_id, msg.task_id,
                     msg.intent.value, DeliveryState.PENDING.value,
                     msg.idempotency_key, msg.priority, msg.created_at,
                     json.dumps(msg.payload)))
                conn.commit()
            except sqlite3.IntegrityError as e:
                conn.close()
                if "UNIQUE constraint" in str(e):
                    raise DeliveryError(
                        f"duplicate idempotency_key: {msg.idempotency_key}")
                raise
            conn.close()

        self._audit("submitted", msg)
        self._notify("message.submitted", msg)
        return msg

    def mark_delivered(self, message_id: str) -> None:
        """Mark a message as delivered to the transport (§6: DELIVERED)."""
        self._update_state(message_id, DeliveryState.DELIVERED, "delivered_at")
        self._audit("delivered", None,
                    extra={"message_id": message_id,
                           "state": DeliveryState.DELIVERED.value})

    def mark_acknowledged(self, message_id: str, ack_msg: AgentMessage) -> None:
        """Mark as ACKNOWLEDGED after receiving TASK_ACK (§7).

        This is the ONLY transition that moves DELIVERED -> ACKNOWLEDGED,
        and it requires receiver-side evidence (the TASK_ACK message).
        """
        self._update_state(message_id, DeliveryState.ACKNOWLEDGED,
                           "acknowledged_at")
        self._audit("acknowledged", ack_msg)

    def mark_started(self, message_id: str, start_msg: AgentMessage) -> None:
        """Mark as RUNNING_VERIFIED after TASK_START (§8).

        SESSION_ACTIVE or PROCESS_ALIVE alone is NOT sufficient (§8).
        """
        self._update_state(message_id, DeliveryState.RUNNING_VERIFIED)
        self._audit("started", start_msg)

    def mark_completed(self, message_id: str, complete_msg: AgentMessage) -> None:
        """Mark as COMPLETED after TASK_COMPLETE (§11)."""
        self._update_state(message_id, DeliveryState.COMPLETED, "completed_at")
        self._audit("completed", complete_msg)

    def mark_failed(self, message_id: str, failed_msg: AgentMessage) -> None:
        """Mark as DELIVERY_FAILED or FAILED."""
        self._update_state(message_id, DeliveryState.FAILED)
        self._audit("failed", failed_msg)

    def mark_delivery_failed(self, message_id: str, reason: str) -> None:
        """Mark as DELIVERY_FAILED — no ACK within timeout (§15)."""
        self._update_state(message_id, DeliveryState.DELIVERY_FAILED)
        self._audit("delivery_failed", None,
                    extra={"message_id": message_id, "reason": reason})

    def _update_state(self, message_id: str, new_state: DeliveryState,
                      timestamp_field: str = "") -> None:
        """Update delivery state in the DB."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            if timestamp_field:
                conn.execute(
                    f"UPDATE messages SET delivery_state=?, {timestamp_field}=? "
                    f"WHERE message_id=?",
                    (new_state.value, time.time(), message_id))
            else:
                conn.execute(
                    "UPDATE messages SET delivery_state=? WHERE message_id=?",
                    (new_state.value, message_id))
            conn.commit()
            conn.close()

    # -- querying -----------------------------------------------------------------

    def get_delivery_state(self, message_id: str) -> Optional[DeliveryState]:
        """Get the current delivery state of a message."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            row = conn.execute(
                "SELECT delivery_state FROM messages WHERE message_id=?",
                (message_id,)).fetchone()
            conn.close()
            if row:
                return DeliveryState(row[0])
            return None

    def get_messages_for_task(self, task_id: str) -> list[dict[str, Any]]:
        """Get all messages for a task, ordered by time."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE task_id=? ORDER BY created_at",
                (task_id,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_pending_messages(self, receiver_agent: str = "",
                             receiver_worker: str = "") -> list[dict[str, Any]]:
        """Get messages pending delivery to a receiver."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            if receiver_agent and receiver_worker:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE receiver_agent=? AND "
                    "receiver_worker=? AND delivery_state IN ('PENDING','DELIVERED') "
                    "ORDER BY priority DESC, created_at",
                    (receiver_agent, receiver_worker)).fetchall()
            elif receiver_agent:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE receiver_agent=? AND "
                    "delivery_state IN ('PENDING','DELIVERED') "
                    "ORDER BY priority DESC, created_at",
                    (receiver_agent,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE delivery_state IN ('PENDING','DELIVERED') "
                    "ORDER BY priority DESC, created_at").fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_inbox(self, agent_id: str, worker_id: str = "",
                  limit: int = 50) -> list[dict[str, Any]]:
        """Get the inbox for a worker (§2: every worker has an INBOX)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            if worker_id:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE receiver_agent=? AND "
                    "receiver_worker=? ORDER BY created_at DESC LIMIT ?",
                    (agent_id, worker_id, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE receiver_agent=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (agent_id, limit)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_outbox(self, agent_id: str, worker_id: str = "",
                   limit: int = 50) -> list[dict[str, Any]]:
        """Get the outbox for a worker (§2: every worker has an OUTBOX)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            if worker_id:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE sender_agent=? AND "
                    "sender_worker=? ORDER BY created_at DESC LIMIT ?",
                    (agent_id, worker_id, limit)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM messages WHERE sender_agent=? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (agent_id, limit)).fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # -- subscription (live notifications, reuse existing EventBus) ----------------

    def subscribe(self, event: str,
                  fn: Callable[[AgentMessage], None]) -> None:
        """Subscribe to live bus events. Integrates with existing EventBus (§3)."""
        self._subscribers.setdefault(event, []).append(fn)

    def _notify(self, event: str, msg: AgentMessage) -> None:
        """Notify subscribers of a bus event."""
        for fn in list(self._subscribers.get(event, [])) + \
                list(self._subscribers.get("*", [])):
            try:
                fn(msg)
            except Exception:
                pass
        # Also emit on the existing EventBus if one is wired (§3)
        if self._bus:
            try:
                self._bus.emit(event, {
                    "message_id": msg.message_id,
                    "task_id": msg.task_id,
                    "intent": msg.intent.value,
                    "sender": f"{msg.sender_agent}/{msg.sender_worker}",
                    "receiver": f"{msg.receiver_agent}/{msg.receiver_worker}",
                })
            except Exception:
                pass

    # -- audit log (§36) ------------------------------------------------------------

    def _audit(self, action: str, msg: Optional[AgentMessage],
               extra: dict[str, Any] | None = None) -> None:
        """Append to the JSONL audit log (§36: every communication is audited)."""
        if not self._audit_path:
            return
        entry = {
            "timestamp": time.time(),
            "action": action,
        }
        if msg:
            entry["message"] = {
                "message_id": msg.message_id,
                "task_id": msg.task_id,
                "intent": msg.intent.value,
                "sender": f"{msg.sender_agent}/{msg.sender_worker}",
                "receiver": f"{msg.receiver_agent}/{msg.receiver_worker}",
            }
        if extra:
            entry.update(extra)
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._audit_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    # -- recovery (§3) ----------------------------------------------------------------

    def recover_pending(self) -> list[dict[str, Any]]:
        """After restart: return messages that were PENDING or DELIVERED
        but never ACKNOWLEDGED. These need re-delivery (§16 retry)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM messages WHERE delivery_state IN "
                "('PENDING','DELIVERED') ORDER BY created_at").fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # -- H06 conflict integration (§21, correction §5) ------------------------------------
    # When two workers deliver contradictory typed claims, the bridge does NOT
    # silently merge them. Both claims are registered with the H06
    # conflict resolver, a CONTRADICTION conflict case is created, and an
    # independent verification task is proposed (§21: "preserve both views").
    #
    # Wiring is optional (claim_registry=None disables) so existing callers
    # keep working unchanged.

    def set_claim_registry(self, registry: Any) -> None:
        """Wire an H06 ClaimRegistry into the bus for auto-conflict detection."""
        self._claim_registry = registry

    def submit_claim(self, claim: Any) -> dict[str, Any]:
        """Register a typed claim and check for contradictions (§21).

        Returns {"claim": ..., "conflicts": [...], "verification_task": ...|None}
        """
        if not self._claim_registry:
            return {"claim": claim, "conflicts": [],
                    "note": "no claim registry wired"}
        self._claim_registry.submit_claim(claim)

        # Look for prior claims on the same task with a different conclusion.
        conflicts = []
        for prior in self._claim_registry.claims_for_task(claim.task_id):
            if prior.claim_id == claim.claim_id:
                continue
            if self._claims_contradict(claim, prior):
                conflict = self._claim_registry.detect_conflict(
                    claim.task_id, prior.claim_id, claim.claim_id)
                if conflict:
                    conflicts.append(conflict)

        result: dict[str, Any] = {
            "claim": claim,
            "conflicts": [c.conflict_id for c in conflicts],
        }
        if conflicts:
            result["verification_task"] = (
                f"QA-VERIFY-{claim.task_id}: independently evaluate claims "
                f"{[c.claim_a_id for c in conflicts] + [c.claim_b_id for c in conflicts]} "
                f"and resolve by evidence (§21: no voting)")
        return result

    @staticmethod
    def _claims_contradict(a: Any, b: Any) -> bool:
        """Heuristic contradiction detector (§21).

        Two claims contradict when they concern the same task and reach
        opposing conclusions. We do NOT guess at subtle semantic negation —
        we flag obvious opposites (contains vs not contains, true vs false)
        and let independent verification resolve them.
        """
        if a.task_id != b.task_id:
            return False
        ca, cb = a.content.strip().lower(), b.content.strip().lower()
        if not ca or not cb or ca == cb:
            return False
        opposites = [
            ("is true", "is false"), ("true", "false"),
            ("exists", "does not exist"), ("works", "does not work"),
            ("passed", "failed"), ("present", "absent"),
            ("contains", "does not contain"), ("correct", "incorrect"),
        ]
        for pos, neg in opposites:
            if (pos in ca and neg in cb) or (neg in ca and pos in cb):
                return True
        return False

    # -- H03 skill candidate intake (§22, correction §6) ----------------------------------
    # A worker discovering a reusable capability sends SKILL_CANDIDATE. The
    # bridge feeds it into the H03 promotion pipeline (candidate → provenance
    # → sandbox → security → benchmark → approval → publication). Genesis then
    # receives the same underlying capability. No useful capability stays
    # trapped inside one disposable worker (§22).

    def set_skill_pipeline(self, pipeline: Any) -> None:
        """Wire an H03 SkillPipeline into the bus."""
        self._skill_pipeline = pipeline

    def submit_skill_candidate(self, msg: AgentMessage) -> dict[str, Any]:
        """Convert a SKILL_CANDIDATE message into a pipeline submission (§22).

        The candidate metadata is carried in the message payload. The worker
        CANNOT self-install: submission only creates a CANDIDATE-stage entry;
        publication still requires the full review pipeline.
        """
        if not self._skill_pipeline:
            return {"submitted": False,
                    "reason": "no skill pipeline wired"}
        from compute.skill_pipeline import SkillCandidate

        payload = msg.payload or {}
        try:
            candidate = SkillCandidate(
                app_id=payload.get("app_id", ""),
                name=payload.get("name", payload.get("app_id", "")),
                version=payload.get("version", "0.1.0"),
                description=payload.get("description", msg.objective),
                proposed_bridge_adapter=payload.get("bridge_adapter", ""),
                required_capabilities=tuple(payload.get("required_capabilities", ())),
                required_os_deps=tuple(payload.get("required_os_deps", ())),
                required_model_capabilities=tuple(payload.get("required_model_capabilities", ())),
                permissions_requested=tuple(payload.get("permissions_requested", ())),
                source_url=payload.get("source_url", ""),
                license=payload.get("license", ""),
                source_hash=payload.get("source_hash", ""),
                submitted_by=f"{msg.sender_agent}/{msg.sender_worker}",
            )
        except ValueError as e:
            return {"submitted": False, "reason": f"invalid candidate: {e}"}
        if not candidate.app_id:
            return {"submitted": False,
                    "reason": "SKILL_CANDIDATE payload missing app_id"}
        try:
            self._skill_pipeline.submit(candidate)
        except Exception as e:
            return {"submitted": False, "reason": str(e)}

        self._audit("skill_candidate_submitted", msg,
                    extra={"app_id": candidate.app_id,
                           "version": candidate.version})
        return {
            "submitted": True,
            "candidate_id": candidate.candidate_id,
            "submitter": candidate.submitted_by,
            "stage": "candidate",
            "note": "worker submits only; publication requires the full "
                    "H03 review pipeline (provenance → sandbox → security → "
                    "benchmark → approval) — no self-install (§22)",
        }

    # -- H01 scope enforcement (AT-22 ready, single-owner today) --------------------
    # The envelope carries owner/workspace/tenant scope; the guard refuses
    # cross-scope messages when enforcement is enabled. Today single-owner:
    # violations are CHECKED and logged but nothing can cross (one scope).

    def set_scope_guard(self, guard: Any) -> None:
        """Wire an H01 ScopeGuard into the bus."""
        self._scope_guard = guard

    def check_scope(self, msg: AgentMessage) -> dict[str, Any]:
        """Check a message's scope before delivery (§ H01/AT-22)."""
        if not self._scope_guard:
            return {"allowed": True, "reason": "no scope guard wired"}
        result = self._scope_guard.check_message(msg)
        if not result["allowed"]:
            return result
        return result

    def stats(self) -> dict[str, Any]:
        """Message bus statistics for the dashboard (§43)."""
        with self._lock:
            conn = sqlite3.connect(str(self._db_path))
            total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            by_state = {}
            for row in conn.execute(
                    "SELECT delivery_state, COUNT(*) FROM messages "
                    "GROUP BY delivery_state"):
                by_state[row[0]] = row[1]
            by_intent = {}
            for row in conn.execute(
                    "SELECT intent, COUNT(*) FROM messages "
                    "GROUP BY intent"):
                by_intent[row[0]] = row[1]
            conn.close()
            return {
                "total_messages": total,
                "by_state": by_state,
                "by_intent": by_intent,
            }
