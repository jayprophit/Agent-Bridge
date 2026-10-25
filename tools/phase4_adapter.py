"""Phase 4 harmless tools integrated into Agent Bridge (FINAL, approval-gated).

Corrections vs original:
- Strict input validation: reject bool-as-number, NaN/inf, oversized strings,
  out-of-range numbers, huge ints (no OverflowError).
- Thread-safe idempotency store (process-local; documented as non-durable).
- Idempotency: validate trusted identity BEFORE cache lookup; bind cached
  entries to (agent_id, tool_id, canonical arg fingerprint); reject conflicting reuse.
- Conservative input size limits.
- Identity required at execution boundary (deny-by-default if missing).
- Audit hook (optional callback) invoked outside the idempotency lock; exceptions swallowed.
- Honest capability flags: timeout is advisory (dispatcher enforces real timeout).
- ToolAdapter subclass for dispatcher compatibility.
- Monotonic time for elapsed duration.
- Execution ID validation (type + length).

Trust boundary: this module is intended to be invoked by the Agent Bridge
dispatcher, which performs real identity/permission/audit. Direct callers must
supply a verified agent_id; missing identity is denied. A caller-supplied
agent_id is NOT proof of authentication; the dispatcher must pass a trusted
value (e.g. from session context).
"""
from __future__ import annotations

import json
import time
import uuid
import math
import threading
import hashlib
from typing import Any, Callable, Optional

from tools.registry import ToolRecord, READ_ONLY
from tools.adapter import ToolAdapter

PHASE4_TOOLS = {
    "phase4.add_numbers": {
        "display_name": "add_numbers",
        "description": "Add two numbers.",
        "input_schema": {"a": "number", "b": "number"},
        "risk_class": READ_ONLY,
        "max_str_len": 0,
        "max_num_abs": 1e15,
    },
    "phase4.reverse_string": {
        "display_name": "reverse_string",
        "description": "Reverse a string.",
        "input_schema": {"s": "string"},
        "risk_class": READ_ONLY,
        "max_str_len": 10000,
    },
    "phase4.uppercase": {
        "display_name": "uppercase",
        "description": "Uppercase a string.",
        "input_schema": {"s": "string"},
        "risk_class": READ_ONLY,
        "max_str_len": 10000,
    },
    "phase4.synthetic_data_query": {
        "display_name": "synthetic_data_query",
        "description": "Return canned synthetic records (read-only).",
        "input_schema": {"topic": "string"},
        "risk_class": READ_ONLY,
        "max_str_len": 1000,
    },
}

MAX_EXECUTION_ID_LEN = 128

_idempotency_lock = threading.Lock()
_idempotency_store: dict[str, dict] = {}


def _arg_fingerprint(args: Any) -> str:
    try:
        canonical = json.dumps(args, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001
        canonical = repr(args)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_execution_id(eid: Any) -> tuple[bool, str]:
    if not isinstance(eid, str) or not eid.strip():
        return False, "execution_id must be a non-empty string"
    if len(eid) > MAX_EXECUTION_ID_LEN:
        return False, "execution_id exceeds length limit"
    return True, "ok"


def _validate(tid: str, args: Any, agent_id: Any) -> tuple[bool, str]:
    if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
        return False, "agent_id required"
    meta = PHASE4_TOOLS[tid]
    if not isinstance(args, dict):
        return False, "args must be object"
    schema = meta["input_schema"]
    for k in args:
        if k not in schema:
            return False, f"unexpected arg {k}"
    for k, t in schema.items():
        if k not in args:
            return False, f"missing arg {k}"
        v = args[k]
        if t == "number":
            if isinstance(v, bool):
                return False, f"{k} must be number (bool not allowed)"
            if isinstance(v, int):
                limit = meta.get("max_num_abs", 1e15)
                if abs(v) > limit:
                    return False, f"{k} exceeds numeric limit"
            elif isinstance(v, float):
                try:
                    if not math.isfinite(v):
                        return False, f"{k} must be finite"
                except (OverflowError, ValueError, TypeError):
                    return False, f"{k} must be finite"
                limit = meta.get("max_num_abs", 1e15)
                if abs(v) > limit:
                    return False, f"{k} exceeds numeric limit"
            else:
                return False, f"{k} must be number"
        elif t == "string":
            if not isinstance(v, str):
                return False, f"{k} must be string"
            if len(v) > meta.get("max_str_len", 10000):
                return False, f"{k} exceeds length limit"
    return True, "ok"


def register_phase4_tools(registry) -> None:
    for tid, meta in PHASE4_TOOLS.items():
        adapter = Phase4Adapter(tid)
        rec = ToolRecord(
            tool_id=tid,
            tool_family="phase4",
            display_name=meta["display_name"],
            description=meta["description"],
            status="AVAILABLE",
            backend="phase4",
            available=True,
            installed=True,
            input_schema=meta["input_schema"],
            risk_class=meta["risk_class"],
            supports_audit=True,
            supports_timeout=False,
        )
        registry.register(rec, adapter=adapter)


def phase4_tool_records() -> list:
    out = []
    for tid, meta in PHASE4_TOOLS.items():
        out.append(ToolRecord(
            tool_id=tid,
            tool_family="phase4",
            display_name=meta["display_name"],
            description=meta["description"],
            status="AVAILABLE",
            backend="phase4",
            available=True,
            installed=True,
            input_schema=meta["input_schema"],
            risk_class=meta["risk_class"],
            supports_audit=True,
            supports_timeout=False,
        ))
    return out


def _sanitize_timeout(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 10.0
    if not math.isfinite(f) or f <= 0:
        return 10.0
    if f > 3600:
        return 3600.0
    return f


def _safe_audit(cb, eid, tid, agent_id, status, error, result, elapsed):
    if cb is None:
        return
    try:
        cb(eid, tid, agent_id, status, error, result, elapsed)
    except Exception:  # noqa: BLE001
        pass


def execute_phase4_tool(tid, args, execution_id=None, timeout_s=10, agent_id=None, audit_cb=None):
    # 1. Trusted caller identity first.
    if not agent_id or not isinstance(agent_id, str) or not agent_id.strip():
        _safe_audit(audit_cb, None, tid, agent_id, "rejected", "agent_id required", None, 0.0)
        return {"execution_id": None, "status": "rejected", "error": "agent_id required"}

    # 2. Tool known.
    if tid not in PHASE4_TOOLS:
        eid = execution_id or str(uuid.uuid4())
        if execution_id is not None:
            vok, vmsg = _validate_execution_id(execution_id)
            if not vok:
                _safe_audit(audit_cb, None, tid, agent_id, "rejected", vmsg, None, 0.0)
                return {"execution_id": None, "status": "rejected", "error": vmsg}
        _safe_audit(audit_cb, eid, tid, agent_id, "rejected", "unknown tool", None, 0.0)
        return {"execution_id": eid, "status": "rejected", "error": "unknown tool"}

    # 3. Validate args.
    try:
        ok, msg = _validate(tid, args, agent_id)
    except Exception as e:  # noqa: BLE001
        ok, msg = False, f"validation error: {e}"
    if not ok:
        eid = execution_id or str(uuid.uuid4())
        if execution_id is not None:
            vok, vmsg = _validate_execution_id(execution_id)
            if not vok:
                _safe_audit(audit_cb, None, tid, agent_id, "rejected", vmsg, None, 0.0)
                return {"execution_id": None, "status": "rejected", "error": vmsg}
            eid = execution_id
        _safe_audit(audit_cb, eid, tid, agent_id, "rejected", msg, None, 0.0)
        return {"execution_id": eid, "status": "rejected", "error": msg}

    # 4. Validate execution id.
    if execution_id is None:
        eid = str(uuid.uuid4())
    else:
        vok, vmsg = _validate_execution_id(execution_id)
        if not vok:
            _safe_audit(audit_cb, None, tid, agent_id, "rejected", vmsg, None, 0.0)
            return {"execution_id": None, "status": "rejected", "error": vmsg}
        eid = execution_id

    arg_fp = _arg_fingerprint(args)
    timeout_s = _sanitize_timeout(timeout_s)

    # 5. Idempotency lookup.
    with _idempotency_lock:
        prior = _idempotency_store.get(eid)
        if prior is not None:
            if (prior.get("agent_id") == agent_id
                    and prior.get("tool_id") == tid
                    and prior.get("arg_fp") == arg_fp):
                if prior.get("completed"):
                    return {
                        "execution_id": eid,
                        "status": "duplicate",
                        "result": prior.get("result"),
                        "latency_s": prior.get("latency_s"),
                    }
                return {"execution_id": eid, "status": "duplicate", "result": None,
                        "note": "in-flight"}
            _safe_audit(audit_cb, eid, tid, agent_id, "rejected",
                        "execution_id reused with conflicting identity/tool/args", None, 0.0)
            return {"execution_id": eid, "status": "rejected",
                    "error": "execution_id reused with conflicting identity/tool/args"}

        _idempotency_store[eid] = {
            "agent_id": agent_id,
            "tool_id": tid,
            "arg_fp": arg_fp,
            "result": None,
            "latency_s": None,
            "status": "in-flight",
            "completed": False,
        }

    # 7. Execute.
    t0 = time.monotonic()
    try:
        if tid == "phase4.add_numbers":
            result = args["a"] + args["b"]
        elif tid == "phase4.reverse_string":
            result = args["s"][::-1]
        elif tid == "phase4.uppercase":
            result = args["s"].upper()
        elif tid == "phase4.synthetic_data_query":
            result = [{"id": i, "topic": args["topic"], "value": i * 10} for i in range(3)]
        else:
            raise ValueError("not implemented")
        elapsed = time.monotonic() - t0
        if elapsed > timeout_s:
            with _idempotency_lock:
                entry = _idempotency_store.get(eid)
                if entry is not None:
                    entry["status"] = "timeout"
                    entry["completed"] = True
                    entry["latency_s"] = round(elapsed, 4)
            _safe_audit(audit_cb, eid, tid, agent_id, "timeout", f"{elapsed}s", None, elapsed)
            return {"execution_id": eid, "status": "timeout", "error": "exceeded timeout"}
        with _idempotency_lock:
            entry = _idempotency_store.get(eid)
            if entry is not None:
                entry["result"] = result
                entry["latency_s"] = round(elapsed, 4)
                entry["status"] = "ok"
                entry["completed"] = True
        _safe_audit(audit_cb, eid, tid, agent_id, "ok", None, result, elapsed)
        return {"execution_id": eid, "status": "ok", "result": result,
                "latency_s": round(elapsed, 4)}
    except Exception as e:  # noqa: BLE001
        elapsed = time.monotonic() - t0
        with _idempotency_lock:
            entry = _idempotency_store.get(eid)
            if entry is not None:
                entry["status"] = "error"
                entry["completed"] = True
                entry["latency_s"] = round(elapsed, 4)
        _safe_audit(audit_cb, eid, tid, agent_id, "error", repr(e), None, elapsed)
        return {"execution_id": eid, "status": "error", "error": repr(e)}


class Phase4Adapter(ToolAdapter):
    def __init__(self, tool_id: str):
        self.tool_id = tool_id
        self.family = "phase4"

    def probe(self) -> dict:
        return {"available": True, "status": "AVAILABLE"}

    def validate(self, arguments: dict) -> tuple[bool, str]:
        if not isinstance(arguments, dict):
            return False, "args must be object"
        meta = PHASE4_TOOLS.get(self.tool_id)
        if meta is None:
            return False, "unknown tool"
        schema = meta["input_schema"]
        for k in arguments:
            if k not in schema:
                return False, f"unexpected arg {k}"
        for k, t in schema.items():
            if k not in arguments:
                return False, f"missing arg {k}"
            v = arguments[k]
            if t == "number":
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    return False, f"{k} must be number"
                if isinstance(v, int):
                    if abs(v) > meta.get("max_num_abs", 1e15):
                        return False, f"{k} exceeds numeric limit"
                else:
                    try:
                        if not math.isfinite(v):
                            return False, f"{k} must be finite"
                    except (OverflowError, ValueError, TypeError):
                        return False, f"{k} must be finite"
                    if abs(v) > meta.get("max_num_abs", 1e15):
                        return False, f"{k} exceeds numeric limit"
            elif t == "string":
                if not isinstance(v, str):
                    return False, f"{k} must be string"
                if len(v) > meta.get("max_str_len", 10000):
                    return False, f"{k} exceeds length limit"
        return True, "ok"

    def execute(self, arguments: dict, context=None) -> dict:
        ctx = context or {}
        agent_id = ctx.get("trusted_agent_id", ctx.get("agent_id"))
        execution_id = ctx.get("execution_id")
        audit_cb = ctx.get("audit_cb")
        timeout_s = ctx.get("timeout_s", 10)
        res = execute_phase4_tool(
            self.tool_id, arguments, execution_id=execution_id,
            timeout_s=timeout_s, agent_id=agent_id, audit_cb=audit_cb,
        )
        out = dict(res)
        out["ok"] = (res.get("status") == "ok")
        if "result" in res:
            out["output"] = res["result"]
        if res.get("status") not in ("ok", "duplicate"):
            out["error"] = res.get("error", res.get("status"))
        return out

    def verify(self, result: dict) -> tuple[bool, str]:
        if not isinstance(result, dict):
            return False, "result not dict"
        if result.get("ok") is True:
            return True, ""
        if result.get("status") in ("ok", "duplicate"):
            return True, ""
        return False, str(result.get("error", "not ok"))

    def cancel(self) -> dict:
        return {"ok": True, "note": "nothing cancellable"}


def phase4_records():
    return phase4_tool_records()


def ensure_phase4_registered(registry) -> bool:
    """Idempotent bootstrap helper.

    Returns True if registration performed, False if already registered.
    Safe to call repeatedly; never raises on duplicate tool_id.
    """
    existing = set(getattr(registry, "ids", lambda: [])())
    if "phase4.add_numbers" in existing:
        return False
    try:
        register_phase4_tools(registry)
        return True
    except ValueError:
        return False
