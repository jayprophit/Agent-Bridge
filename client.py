"""Tiny Python client SDK for the local runtime API (v0.4, stdlib only).

The interface Genesis may use later. Blocking helpers with polling
(no busy-wait: modest interval, generous default timeout).
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class ClientError(Exception):
    pass


class AgentRuntimeClient:
    def __init__(self, base: str = "http://127.0.0.1:8471",
                 token: str = "", timeout: int = 30):
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _req(self, method: str, path: str,
             payload: dict | None = None) -> Any:
        data = json.dumps(payload or {}).encode() if method in ("POST",) else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read().decode() or "{}")
            except ValueError:
                detail = {"error": f"HTTP {e.code}"}
            raise ClientError(f"HTTP {e.code}: {detail.get('error', '')}")
        except urllib.error.URLError as e:
            raise ClientError(f"cannot reach runtime: {e.reason}")

    def health(self) -> dict:
        return self._req("GET", "/health")

    def capabilities(self) -> dict:
        return self._req("GET", "/v1/capabilities")

    def models(self) -> dict:
        return self._req("GET", "/v1/models")

    def diagnostics(self) -> dict:
        return self._req("GET", "/v1/diagnostics")

    def selfcheck(self) -> dict:
        return self._req("GET", "/v1/selfcheck")

    def schema(self) -> dict:
        return self._req("GET", "/v1/schema")

    def list_sessions(self, status: str = "", workspace: str = "",
                      since: float = 0.0) -> dict:
        q = f"?status={status}&workspace={workspace}&since={since}"
        return self._req("GET", f"/v1/sessions{q}")

    def create_session(self, workspace: str, mode: str = "",
                       approval: str = "", model: str = "",
                       roles: dict | None = None, profile: str = "",
                       owner_authorized: bool = False,
                       network_policy: str = "") -> dict:
        return self._req("POST", "/v1/sessions",
                         {"workspace": workspace, "mode": mode,
                          "approval": approval, "model": model,
                          "roles": roles or {}, "profile": profile,
                          "owner_authorized": owner_authorized,
                          "network_policy": network_policy})

    def emergency_stop(self, reason: str = "operator stop") -> dict:
        return self._req("POST", "/v1/stop", {"reason": reason})

    def machine_caps(self) -> dict:
        return self._req("GET", "/v1/caps")

    def session_status(self, session_id: str) -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/status")

    def submit_task(self, session_id: str, text: str,
                    idempotency_key: str = "",
                    parent_task_id: str = "") -> dict:
        return self._req("POST", f"/v1/sessions/{session_id}/tasks",
                         {"text": text, "idempotency_key": idempotency_key,
                          "parent_task_id": parent_task_id})

    def request_revision(self, session_id: str, task_id: str,
                         instruction: str) -> dict:
        return self._req("POST", f"/v1/sessions/{session_id}/revise",
                         {"task_id": task_id, "instruction": instruction})

    def resolve_final(self, session_id: str, task_id: str, decision: str,
                      note: str = "") -> dict:
        return self._req("POST", f"/v1/sessions/{session_id}/final",
                         {"task_id": task_id, "decision": decision,
                          "note": note})

    def events(self, session_id: str, since: int = 0) -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/events?since={since}")

    def cancel(self, session_id: str, task_id: str) -> dict:
        return self._req("POST", f"/v1/sessions/{session_id}/cancel",
                         {"task_id": task_id})

    def approve(self, session_id: str, approval_id: str,
                decision: str = "approve-once") -> dict:
        return self._req("POST",
                         f"/v1/sessions/{session_id}/approvals/{approval_id}",
                         {"decision": decision})

    def rollback(self, session_id: str, label: str = "") -> dict:
        return self._req("POST", f"/v1/sessions/{session_id}/rollback",
                         {"label": label})

    def diff(self, session_id: str, target: str = "session", path: str = "",
             label: str = "") -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/diff"
                                f"?target={target}&path={path}&label={label}")

    def manifest(self, session_id: str) -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/manifest")

    def scorecard(self, session_id: str) -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/scorecard")

    def timeline(self, session_id: str) -> dict:
        return self._req("GET", f"/v1/sessions/{session_id}/timeline")

    def export(self, session_id: str, task_id: str = "",
               fmt: str = "json") -> Any:
        if fmt == "markdown":
            import urllib.request
            req = urllib.request.Request(
                f"{self.base}/v1/sessions/{session_id}/export"
                f"?task={task_id}&format=markdown", method="GET")
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return resp.read().decode("utf-8", "replace")
            except urllib.error.URLError as e:
                raise ClientError(f"cannot reach runtime: {e.reason}")
        return self._req("GET", f"/v1/sessions/{session_id}/export"
                                f"?task={task_id}&format={fmt}")

    def stream_events(self, session_id: str, since: int = 0,
                      timeout: int = 30) -> list[dict]:
        """SSE with Last-Event-ID; falls back to polling on any failure."""
        req = urllib.request.Request(
            f"{self.base}/v1/sessions/{session_id}/events/stream?since={since}",
            method="GET")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Last-Event-ID", str(since))
        req.add_header("Accept", "text/event-stream")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
        except Exception:
            return self.events(session_id, since)["events"]
        events: list[dict] = []
        payload: dict[str, str] = {}
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except ValueError:
                    pass
            elif not line.strip():
                payload = {}
        return events

    def delete_session(self, session_id: str) -> dict:
        return self._req("DELETE", f"/v1/sessions/{session_id}")

    def run_task(self, session_id: str, text: str, idempotency_key: str = "",
                 timeout: float = 900, poll: float = 3.0) -> dict:
        sub = self.submit_task(session_id, text, idempotency_key)
        tid = sub["task_id"]
        end = time.time() + timeout
        while time.time() < end:
            st = self.session_status(session_id)
            if st["tasks"].get(tid) in ("COMPLETED", "FAILED", "CANCELLED",
                                        "ROLLED_BACK", "INTERRUPTED"):
                return {"task_id": tid, "session": st}
            time.sleep(poll)
        raise ClientError("task wait timed out")
