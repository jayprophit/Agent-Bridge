"""CLI as API client (v0.6). All commands go through AgentRuntime/Session —
no duplicated policy logic, no direct executor imports.

Commands: runtime health | session create/status/events/delete |
task run/submit/wait/cancel | approval approve/deny | rollback |
capabilities | caps | stop | replay | serve
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from runtime import AgentRuntime, RuntimeConfig

_RT: AgentRuntime | None = None


def _runtime(args: Any) -> AgentRuntime:
    global _RT
    if _RT is None:
        _RT = AgentRuntime(RuntimeConfig(
            allowed_workspace_roots=args.root or
            [os.getenv("AGENT_BRIDGE_ROOT", ".")],
            default_mode=args.mode or "hybrid",
            preset=args.preset or "LOW_RESOURCE",
            profile=getattr(args, "profile", "") or "",
            owner_authorized=bool(getattr(args, "owner_authorized", False)),
            network_policy=getattr(args, "network", "") or "LOCAL_MODEL_NETWORK"))
    return _RT


def _out(obj: Any) -> int:
    print(json.dumps(obj, indent=2, default=str)[:8000])
    return 0


def cmd_health(args: Any) -> int:
    return _out(_runtime(args).health())


def cmd_capabilities(args: Any) -> int:
    return _out(_runtime(args).capabilities())


def cmd_caps(args: Any) -> int:
    return _out(_runtime(args).machine_inventory())


def cmd_stop(args: Any) -> int:
    return _out(_runtime(args).emergency_stop(
        getattr(args, "reason", "") or "operator stop"))


def cmd_session_create(args: Any) -> int:
    rt = _runtime(args)
    s = rt.create_session(args.workspace, mode=args.mode or "",
                          approval=args.approval or "",
                          profile=getattr(args, "profile", "") or "",
                          owner_authorized=bool(getattr(args, "owner_authorized", False)))
    return _out({"session_id": s.session_id, "mode": s.mode})


def cmd_session_status(args: Any) -> int:
    rt = _runtime(args)
    s = rt.get_session(args.session)
    with s.lock:
        return _out({"session_id": s.session_id, "status": s.status,
                     "tasks": {t: r.status for t, r in s.tasks.items()},
                     "pending_approvals": list(s.pending_approvals)})


def cmd_session_delete(args: Any) -> int:
    return _out(_runtime(args).delete_session(args.session))


def cmd_events(args: Any) -> int:
    s = _runtime(args).get_session(args.session)
    return _out(s.events_since(args.since))


def cmd_task_run(args: Any) -> int:
    rt = _runtime(args)
    s = rt.get_session(args.session) if args.session else \
        rt.create_session(args.workspace or rt.cfg.allowed_workspace_roots[0])
    task = args.task or (Path(args.task_file).read_text(encoding="utf-8")
                         if args.task_file else "")
    if not task:
        print("provide --task or --task-file", file=sys.stderr)
        return 2
    tid = s.submit_task(task, args.idempotency_key or "")
    if args.wait:
        res = s.wait_task(tid, timeout=args.timeout)
        return _out({"task_id": tid, "result": res})
    return _out({"task_id": tid, "status": "submitted"})


def cmd_task_cancel(args: Any) -> int:
    s = _runtime(args).get_session(args.session)
    return _out(s.cancel_task(args.task))


def cmd_approval(args: Any, approve: bool) -> int:
    s = _runtime(args).get_session(args.session)
    decision = "approve-once" if approve else "deny"
    if args.decision:
        decision = args.decision
    return _out(s.resolve_approval(args.approval_id, decision))


def cmd_rollback(args: Any) -> int:
    s = _runtime(args).get_session(args.session)
    return _out(s.rollback(args.label or ""))


def cmd_replay(args: Any) -> int:
    from replay import audit, rerun_safe, verify
    if args.replay_mode == "verify":
        return _out(verify(args.file, args.workspace or "."))
    if args.replay_mode == "rerun_safe":
        return _out(rerun_safe(args.file))
    return _out(audit(args.file))


def cmd_serve(args: Any) -> int:
    from service import serve
    rt = _runtime(args)
    srv = serve(rt, args.host or "127.0.0.1", args.port or 8471)
    print(f"serving /v1 on http://{srv.server_address[0]}:{srv.server_address[1]}",
          flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="runtime-cli",
                                description="Genesis Local Agent Runtime CLI")
    p.add_argument("--root", action="append", default=[])
    p.add_argument("--mode", default="")
    p.add_argument("--approval", default="")
    p.add_argument("--preset", default="")
    p.add_argument("--profile", default="",
                   choices=["", "SAFE_EXPLORATION", "ASSISTED_BUILD",
                            "AUTONOMOUS_SANDBOX", "PRECIOUS_PROJECT",
                            "OWNER_FULL_ACCESS"])
    p.add_argument("--owner-authorized", action="store_true")
    p.add_argument("--network", default="",
                   choices=["", "LOCAL_MODEL_NETWORK", "EXTERNAL_NETWORK",
                            "NO_NETWORK"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health").set_defaults(fn=lambda a: cmd_health(a))
    sub.add_parser("capabilities").set_defaults(fn=lambda a: cmd_capabilities(a))
    sub.add_parser("caps").set_defaults(fn=lambda a: cmd_caps(a))
    st = sub.add_parser("stop")
    st.add_argument("--reason", default="operator stop")
    st.set_defaults(fn=lambda a: cmd_stop(a))

    sc = sub.add_parser("session-create")
    sc.add_argument("--workspace", required=True)
    sc.set_defaults(fn=lambda a: cmd_session_create(a))
    ss = sub.add_parser("session-status")
    ss.add_argument("--session", required=True)
    ss.set_defaults(fn=lambda a: cmd_session_status(a))
    sd = sub.add_parser("session-delete")
    sd.add_argument("--session", required=True)
    sd.set_defaults(fn=lambda a: cmd_session_delete(a))
    ev = sub.add_parser("events")
    ev.add_argument("--session", required=True)
    ev.add_argument("--since", type=int, default=0)
    ev.set_defaults(fn=lambda a: cmd_events(a))

    tr = sub.add_parser("task-run")
    tr.add_argument("--session", default="")
    tr.add_argument("--workspace", default="")
    tr.add_argument("--task", default="")
    tr.add_argument("--task-file", default="")
    tr.add_argument("--idempotency-key", default="")
    tr.add_argument("--wait", action="store_true")
    tr.add_argument("--timeout", type=float, default=1200)
    tr.set_defaults(fn=lambda a: cmd_task_run(a))
    tc = sub.add_parser("task-cancel")
    tc.add_argument("--session", required=True)
    tc.add_argument("--task", required=True)
    tc.set_defaults(fn=lambda a: cmd_task_cancel(a))

    for name, approve in (("approval-approve", True), ("approval-deny", False)):
        ap = sub.add_parser(name)
        ap.add_argument("--session", required=True)
        ap.add_argument("--approval-id", required=True)
        ap.add_argument("--decision", default="")
        ap.set_defaults(fn=(lambda a, ap=approve: cmd_approval(a, ap)))

    rb = sub.add_parser("rollback")
    rb.add_argument("--session", required=True)
    rb.add_argument("--label", default="")
    rb.set_defaults(fn=lambda a: cmd_rollback(a))

    rp = sub.add_parser("replay")
    rp.add_argument("--file", required=True)
    rp.add_argument("--replay-mode", default="audit",
                    choices=["audit", "verify", "rerun_safe"])
    rp.add_argument("--workspace", default=".")
    rp.set_defaults(fn=lambda a: cmd_replay(a))

    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8471)
    sv.set_defaults(fn=lambda a: cmd_serve(a))
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
