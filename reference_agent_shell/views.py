"""Display sanitization + views (reference shell). Every model-controlled
string is untrusted display data: control characters stripped, lengths
bounded, never interpreted (no ANSI sequences from model text, HTML-escaped
where a browser view might reuse these strings)."""
from __future__ import annotations

import html
import re
from typing import Any

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def safe(text: Any, limit: int = 2000) -> str:
    s = "" if text is None else str(text)
    s = _CTRL.sub("", s)
    s = s.replace("\x1b", "")
    if len(s) > limit:
        s = s[:limit] + f"...[+{len(s) - limit} chars]"
    return s


def safe_html(text: Any, limit: int = 2000) -> str:
    return html.escape(safe(text, limit))


FRIENDLY = {
    "task.started": "task accepted",
    "planning.started": "PLANNING",
    "planning.completed": "plan completed",
    "execution.started": "action requested",
    "execution.completed": "action verified",
    "execution.failed": "action FAILED",
    "approval.requested": "APPROVAL REQUIRED",
    "approval.resolved": "approval resolved",
    "review.started": "REVIEW started",
    "review.completed": "REVIEW decided",
    "rollback.started": "rollback started",
    "rollback.completed": "rollback done",
    "task.completed": "COMPLETED",
    "task.failed": "FAILED",
    "task.cancelled": "CANCELLED",
}


def event_line(e: dict[str, Any]) -> str:
    name = str(e.get("event", e.get("bus_event", "?")))
    label = FRIENDLY.get(name, name)
    extra = ""
    if e.get("action"):
        a = e["action"] or {}
        extra = f" {safe(a.get('action', ''))} {safe(a.get('path', a.get('command', '')))}"[:90]
    if name == "approval.requested":
        extra = f" risk={safe((e.get('context') or {}).get('risk', ''))}"
    return f"[{safe(str(e.get('timestamp', ''))[:19])}] {label}{extra}"


def dashboard(st: dict[str, Any]) -> str:
    tasks = st.get("tasks", {}) or {}
    lines = [
        f"session  : {safe(st.get('session_id'))} [{safe(st.get('status'))}]",
        f"mode     : {safe(st.get('mode'))}",
        f"tasks    : {safe(tasks)}",
        f"files    : {safe(st.get('files_touched'))}",
        f"tests    : {safe(st.get('tests'))}",
        f"review   : {safe(st.get('review'))}",
        f"approvals pending: {safe(st.get('pending_approvals'))}",
        f"errors   : {len(st.get('errors', []) or [])}",
        f"duration : {safe(st.get('duration_s'))}s",
    ]
    comp = st.get("competence") or {}
    if comp:
        lines.append(
            f"competence: valid={safe(comp.get('valid_action_ratio'))} "
            f"malformed={safe(comp.get('malformed'))} "
            f"loops={safe(comp.get('loops'))} hint={safe(comp.get('hint'))}")
    return "\n".join(lines)


def approval_card(aid: str, action: dict[str, Any], ctx: dict[str, Any]) -> str:
    return "\n".join([
        f"approval {safe(aid)} risk={safe(ctx.get('risk'))}",
        f"  action : {safe(action.get('action'))}",
        f"  target : {safe(action.get('path', action.get('command', '')))}",
        f"  reason : {safe(ctx.get('reason'))}",
        f"  diff   : {safe(ctx.get('diff_preview'))[:400]}",
    ])


def scorecard_view(sc: dict[str, Any]) -> str:
    lines = []
    for name, card in (sc.get("scorecard", {}).get("categories", {}) or {}).items():
        lines.append(f"{safe(name):14} {safe(card.get('status')):8} {safe(card.get('detail'))[:100]}")
    return "\n".join(lines)
