"""Reference agent shell (v0.5). Terminal UI over the PUBLIC client only.

Usage:
  python -m reference_agent_shell.shell --url http://127.0.0.1:8471
  python -m reference_agent_shell.shell --embedded --root <dir>
  python -m reference_agent_shell.shell --embedded --root <dir> --script demo.txt

Commands: help, health, models, roots, new, use, task, watch, approve,
  deny, approve-session, final, revise, cancel, rollback, status,
  dashboard, events, timeline, diff, manifest, scorecard, result, export,
  history, prefs, reconnect, quit.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from client import AgentRuntimeClient  # noqa: E402  (public SDK only)

from reference_agent_shell import prefs as prefs_mod  # noqa: E402
from reference_agent_shell import views  # noqa: E402


class Shell:
    def __init__(self, client: AgentRuntimeClient, prefs=None,
                 runtime=None, out=None):
        self.client = client
        self.prefs = prefs or prefs_mod.Prefs()
        self.runtime = runtime  # embedded AgentRuntime or None (remote mode)
        self.out = out or sys.stdout
        self.session_id = ""
        self.task_id = ""
        self.event_index = 0
        self.endpoint = ""

    def emit(self, text: str = "") -> None:
        print(text, file=self.out, flush=True)

    # -- connection / discovery -------------------------------------------
    def cmd_health(self, args: str) -> None:
        try:
            h = self.client.health()
        except Exception as e:  # noqa: BLE001
            self.emit(f"runtime UNAVAILABLE: {views.safe(e)[:200]}")
            return
        self.emit(f"runtime {views.safe(h.get('status'))} "
                  f"(runtime {views.safe((h.get('runtime', '')))})")
        for name, c in (h.get("checks", {}) or {}).items():
            self.emit(f"  {views.safe(name):16} {views.safe(c.get('status'))}")

    def cmd_models(self, args: str) -> None:
        try:
            inv = self.client.models()
        except Exception as e:  # noqa: BLE001
            self.emit(f"inventory unavailable: {views.safe(e)[:150]}")
            return
        if not inv.get("models"):
            self.emit(f"no models reported ({views.safe(inv.get('error', ''))})")
            return
        for m in inv["models"]:
            self.emit(f"  {views.safe(m.get('name')):40} "
                      f"{views.safe(m.get('parameter_size')):8} "
                      f"ctx={views.safe(m.get('context'))}")

    def cmd_roots(self, args: str) -> None:
        caps = self.client.capabilities()
        self.emit(f"endpoint : {views.safe(self.endpoint)}")
        self.emit(f"runtime  : {views.safe(caps.get('runtime'))} "
                  f"api {views.safe(caps.get('compat', {}).get('api', 'v1'))} "
                  f"protocol {views.safe(caps.get('protocol_version'))}")
        self.emit(f"network  : {views.safe(caps.get('network_policy', ''))}")
        if self.runtime is not None:
            for r in self.runtime.cfg.allowed_workspace_roots:
                self.emit(f"  root: {views.safe(r)}")

    # -- sessions / tasks ----------------------------------------------------
    def cmd_new(self, args: str) -> None:
        parts = args.split()
        ws = parts[0] if parts else self.prefs.data.get("last_workspace", "")
        mode = parts[1] if len(parts) > 1 else self.prefs.data.get("default_mode", "hybrid")
        if not ws:
            self.emit("usage: new <workspace> [mode]")
            return
        try:
            s = self.client.create_session(ws, mode=mode)
        except Exception as e:  # noqa: BLE001
            self.emit(f"REFUSED: {views.safe(e)[:300]}")
            return
        self.session_id = s["session_id"]
        self.event_index = 0
        self.prefs.data["last_workspace"] = ws
        self.prefs.save()
        self.emit(f"session {views.safe(self.session_id)} mode={views.safe(s.get('mode'))}")

    def cmd_use(self, args: str) -> None:
        self.session_id = args.strip()
        self.event_index = 0
        self.emit(f"using {views.safe(self.session_id)}")

    def cmd_task(self, args: str) -> None:
        if not self.session_id:
            self.emit("no session: use `new` first")
            return
        if not args.strip():
            self.emit("usage: task <text> [--dry-run] [--no-review]")
            return
        dry = "--dry-run" in args
        text = args.replace("--dry-run", "").replace("--no-review", "").strip()
        self.emit(f"effective: mode=?, dry_run={dry} "
                  f"(policy authoritative server-side)")
        try:
            sub = self.client.submit_task(self.session_id, text)
        except Exception as e:  # noqa: BLE001
            self.emit(f"submit failed: {views.safe(e)[:200]}")
            return
        self.task_id = sub["task_id"]
        self.emit(f"task {views.safe(self.task_id)}"
                  f"{' (deduped)' if sub.get('deduped') else ''}")
        self.watch_loop()

    def watch_loop(self, limit: int = 400) -> None:
        for _ in range(limit):
            try:
                ev = self.client.events(self.session_id, self.event_index)
            except Exception as e:  # noqa: BLE001
                self.emit(f"events unavailable ({views.safe(e)[:100]}); retrying")
                time.sleep(3)
                continue
            for e in ev.get("events", []):
                self.event_index += 1
                if self.prefs.data.get("event_verbosity") == "raw":
                    self.emit(views.safe(json.dumps(e))[:300])
                else:
                    self.emit(views.event_line(e))
                if e.get("event") == "approval.requested":
                    self.show_approval(e)
            try:
                st = self.client.session_status(self.session_id)
            except Exception:
                time.sleep(3)
                continue
            tasks = st.get("tasks", {}) or {}
            if self.task_id and tasks.get(self.task_id) not in (
                    None, "QUEUED", "PLANNING", "EXECUTING", "WAITING_APPROVAL",
                    "TESTING", "REVIEWING", "REVISING"):
                self.emit(f"task {views.safe(self.task_id)}: "
                          f"{views.safe(tasks.get(self.task_id))}")
                return
            if st.get("pending_approvals"):
                self.emit(f"pending approvals: {views.safe(st['pending_approvals'])} "
                          f"(use: approve <id> | approve-session <id> | deny <id>)")
            time.sleep(2)

    # -- approvals / final gate ----------------------------------------------
    def show_approval(self, e: dict[str, Any]) -> None:
        aid = str(e.get("approval_id", ""))
        action = e.get("action", {}) or {}
        ctx = e.get("context", {}) or {}
        self.emit(views.approval_card(aid, action, ctx))
        self.emit("closing this client NEVER approves; server decides on timeout.")

    def cmd_approve(self, args: str, decision: str = "approve-once") -> None:
        try:
            out = self.client.approve(self.session_id, args.strip(), decision)
            self.emit(f"approval {views.safe(out.get('decision'))}")
        except Exception as e:  # noqa: BLE001
            self.emit(f"approve failed: {views.safe(e)[:200]}")

    def cmd_final(self, args: str) -> None:
        parts = args.split(None, 1)
        if len(parts) < 2:
            self.emit("usage: final accept|revise|rollback|cancel <task> [note]")
            return
        decision, rest = parts[0], parts[1]
        tid, _, note = rest.partition(" ")
        try:
            out = self.client.resolve_final(self.session_id, tid, decision, note)
            self.emit(f"final: {views.safe(out)}")
        except Exception as e:  # noqa: BLE001
            self.emit(f"final failed: {views.safe(e)[:200]}")

    def cmd_revise(self, args: str) -> None:
        tid, _, instruction = args.partition(" ")
        if not tid or not instruction:
            self.emit("usage: revise <task> <instruction>")
            return
        try:
            out = self.client.request_revision(self.session_id, tid, instruction)
            self.emit(f"revision child: {views.safe(out.get('child_task_id'))}")
        except Exception as e:  # noqa: BLE001
            self.emit(f"revise failed: {views.safe(e)[:200]}")

    # -- status / evidence -----------------------------------------------------
    def cmd_status(self, args: str) -> None:
        try:
            self.emit(views.dashboard(self.client.session_status(self.session_id)))
        except Exception as e:  # noqa: BLE001
            self.emit(f"status failed: {views.safe(e)[:200]}")

    def cmd_events(self, args: str) -> None:
        ev = self.client.events(self.session_id, 0)
        for e in ev.get("events", [])[-int(args or 20):]:
            self.emit(views.event_line(e))

    def cmd_timeline(self, args: str) -> None:
        for t in self.client.timeline(self.session_id).get("timeline", [])[-30:]:
            self.emit(f"  {views.safe(t)}")

    def cmd_diff(self, args: str) -> None:
        self.emit(views.safe(self.client.diff(
            self.session_id, *(args.split() or ["session"])) .get("diff"))[:4000])

    def cmd_manifest(self, args: str) -> None:
        man = self.client.manifest(self.session_id)
        for c in man.get("changes", [])[:50]:
            self.emit(f"  {views.safe(c.get('operation')):8} "
                      f"{views.safe(c.get('path'))} id={views.safe(c.get('action_id'))}")

    def cmd_scorecard(self, args: str) -> None:
        self.emit(views.scorecard_view(self.client.scorecard(self.session_id)))

    def cmd_result(self, args: str) -> None:
        st = self.client.session_status(self.session_id)
        self.emit(views.safe(json.dumps(st, indent=1))[:4000])

    def cmd_export(self, args: str) -> None:
        fmt = (args.strip() or "json")
        body = self.client.export(self.session_id, fmt=fmt)
        path = f"shell_export.{fmt if fmt != 'jsonl' else 'jsonl'}"
        Path(path).write_text(body if isinstance(body, str) else json.dumps(body),
                               encoding="utf-8")
        self.emit(f"exported {views.safe(path)} ({len(str(body))} chars)")

    def cmd_history(self, args: str) -> None:
        h = self.client.list_sessions()
        for s in h.get("sessions", [])[:20]:
            self.emit(f"  {views.safe(s.get('session_id'))} "
                      f"{views.safe(s.get('status'))} {views.safe(s.get('mode'))} "
                      f"{views.safe(s.get('workspace'))}")

    def cmd_cancel(self, args: str) -> None:
        try:
            self.emit(views.safe(self.client.cancel(
                self.session_id, args.strip() or self.task_id)))
        except Exception as e:  # noqa: BLE001
            self.emit(f"cancel failed: {views.safe(e)[:200]}")

    def cmd_rollback(self, args: str) -> None:
        if args.strip() != "CONFIRM":
            try:
                prev = self.client.diff(self.session_id)
                self.emit("PREVIEW (confirm with: rollback CONFIRM):")
                self.emit(views.safe(prev.get("diff"))[:2000])
            except Exception as e:  # noqa: BLE001
                self.emit(f"preview failed: {views.safe(e)[:200]}")
            return
        try:
            out = self.client.rollback(self.session_id)
            self.emit(f"rollback ok={views.safe(out.get('ok'))} "
                      f"restored={views.safe(out.get('restored'))} "
                      f"removed={views.safe(out.get('removed'))}")
        except Exception as e:  # noqa: BLE001
            self.emit(f"rollback failed: {views.safe(e)[:200]}")

    def cmd_prefs(self, args: str) -> None:
        if not args.strip():
            self.emit(views.safe(json.dumps(self.prefs.data, indent=1)))
            return
        k, _, v = args.partition("=")
        k, v = k.strip(), v.strip()
        if k in self.prefs.data:
            self.prefs.data[k] = v
            self.prefs.save()
            self.emit(f"pref {views.safe(k)}={views.safe(v)} (display only)")
        else:
            self.emit(f"unknown pref (policy prefs live server-side): {views.safe(k)}")

    def cmd_help(self, args: str) -> None:
        self.emit("health models roots new use task watch approve deny "
                  "approve-session final revise status events timeline diff "
                  "manifest scorecard result export history cancel rollback "
                  "prefs reconnect quit")

    def cmd_reconnect(self, args: str) -> None:
        try:
            self.client.health()
            self.emit(f"reconnected {views.safe(self.endpoint)}")
        except Exception as e:  # noqa: BLE001
            self.emit(f"still unavailable: {views.safe(e)[:150]}")

    def cmd_watch(self, args: str) -> None:
        self.watch_loop()

    def run_script(self, path: str) -> int:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            self.emit(f"> {views.safe(line)[:200]}")
            if self.dispatch(line) == "quit":
                break
        return 0

    def dispatch(self, line: str):
        cmd, _, rest = line.partition(" ")
        table = {
            "health": self.cmd_health, "models": self.cmd_models,
            "roots": self.cmd_roots, "new": self.cmd_new, "use": self.cmd_use,
            "task": self.cmd_task, "watch": self.cmd_watch,
            "approve": lambda a: self.cmd_approve(a, "approve-once"),
            "approve-session": lambda a: self.cmd_approve(a, "approve-session"),
            "deny": lambda a: self.cmd_approve(a, "deny"),
            "final": self.cmd_final, "revise": self.cmd_revise,
            "status": self.cmd_status, "events": self.cmd_events,
            "timeline": self.cmd_timeline, "diff": self.cmd_diff,
            "manifest": self.cmd_manifest, "scorecard": self.cmd_scorecard,
            "result": self.cmd_result, "export": self.cmd_export,
            "history": self.cmd_history, "cancel": self.cmd_cancel,
            "rollback": self.cmd_rollback, "prefs": self.cmd_prefs,
            "reconnect": self.cmd_reconnect, "help": self.cmd_help,
        }
        fn = table.get(cmd)
        if fn is None:
            self.emit(f"unknown: {views.safe(cmd)} (try: help)")
            return None
        try:
            return fn(rest)
        except Exception as e:  # noqa: BLE001  (shell never crashes on display)
            self.emit(f"error: {views.safe(e)[:200]}")
            return None

    def repl(self) -> int:
        self.emit("reference agent shell — public API only. `help` for commands.")
        while True:
            try:
                line = input("shell> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.emit("")
                return 0
            if line in ("quit", "exit"):
                return 0
            if line:
                self.dispatch(line)


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Reference agent shell (public API only)")
    p.add_argument("--url", default="http://127.0.0.1:8471")
    p.add_argument("--embedded", action="store_true")
    p.add_argument("--root", default="")
    p.add_argument("--token", default="")
    p.add_argument("--script", default="")
    p.add_argument("--prefs", default="")
    args = p.parse_args(argv)
    prefs = prefs_mod.Prefs(Path(args.prefs) if args.prefs else None)
    if args.embedded:
        from runtime import AgentRuntime, RuntimeConfig
        if not args.root:
            print("embedded mode needs --root", file=sys.stderr)
            return 2
        rt = AgentRuntime(RuntimeConfig(allowed_workspace_roots=[args.root]))
        # in-process client facade over the same public surface
        from client import AgentRuntimeClient  # noqa: F401
        client = EmbeddedClient(rt)
        shell = Shell(client, prefs, runtime=rt)
        shell.endpoint = "embedded"
    else:
        client = AgentRuntimeClient(args.url, token=args.token)
        shell = Shell(client, prefs)
        shell.endpoint = args.url
    if args.script:
        return shell.run_script(args.script)
    return shell.repl()


class EmbeddedClient:
    """In-process stand-in with the exact AgentRuntimeClient method surface,
    backed by the public AgentRuntime (never bridge internals)."""

    def __init__(self, runtime):
        self.rt = runtime

    def health(self):
        return self.rt.health()

    def capabilities(self):
        return self.rt.capabilities()

    def models(self):
        return self.rt.model_inventory()

    def diagnostics(self):
        return self.rt.diagnostics()

    def selfcheck(self):
        return {"checks": self.rt.self_check()}

    def schema(self):
        from service import api_schema
        return api_schema()

    def list_sessions(self, **kw):
        return {"sessions": self.rt.list_sessions(**kw)}

    def list_sessions(self, **kw):
        return {"sessions": self.rt.list_sessions(**kw)}

    def create_session(self, workspace, mode="", approval="", model="", roles=None):
        s = self.rt.create_session(workspace, mode=mode, approval=approval,
                                   model=model, roles=roles)
        return {"session_id": s.session_id, "mode": s.mode}

    def session_status(self, sid):
        s = self.rt.get_session(sid)
        d = s.status_dashboard()
        d["pending_final"] = bool(getattr(s, "_gate", None))
        return d

    def submit_task(self, sid, text, idempotency_key="", parent_task_id=""):
        s = self.rt.get_session(sid)
        tid = s.submit_task(text, idempotency_key, parent_task_id=parent_task_id)
        return {"task_id": tid, "status": s.tasks[tid].status,
                "deduped": bool(s.last_submit_deduped)}

    def events(self, sid, since=0):
        return self.rt.get_session(sid).events_since(since)

    def events(self, sid, since=0):
        return self.rt.get_session(sid).events_since(since)

    def cancel(self, sid, tid):
        return self.rt.get_session(sid).cancel_task(tid)

    def approve(self, sid, aid, decision="approve-once"):
        return self.rt.get_session(sid).resolve_approval(aid, decision)

    def resolve_final(self, sid, tid, decision, note=""):
        return self.rt.get_session(sid).resolve_final(tid, decision, note)

    def request_revision(self, sid, tid, instruction):
        return {"child_task_id": self.rt.get_session(sid).request_revision(tid, instruction)}

    def rollback(self, sid, label=""):
        return self.rt.get_session(sid).rollback(label)

    def delete_session(self, sid):
        return self.rt.delete_session(sid)

    def diff(self, sid, target="session", path="", label=""):
        return self.rt.session_diff(sid, target, path, label)

    def manifest(self, sid):
        return self.rt.session_manifest(sid)

    def scorecard(self, sid):
        return self.rt.session_scorecard(sid)

    def timeline(self, sid):
        return self.rt.session_timeline(sid)

    def export(self, sid, task_id="", fmt="json"):
        return self.rt.export_result(sid, task_id, fmt)

    def run_task(self, sid, text, **kw):
        return self.rt.get_session(sid).run_task(text, **kw)


if __name__ == "__main__":
    raise SystemExit(main())
