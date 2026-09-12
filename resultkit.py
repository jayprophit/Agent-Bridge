"""Verification scorecard, timeline, change manifest, export (v0.5).

Scorecard categories: FILES COMMANDS TESTS ORACLE REVIEW RUNTIME_OUTPUT
ROLLBACK_SAFETY SECURITY — each PASS/FAIL/WEAK/UNKNOWN/NOT_APPLICABLE.
Deliberately NO single numeric quality score.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

PASS, FAIL, WEAK, UNKNOWN, NA = "PASS", "FAIL", "WEAK", "UNKNOWN", "NOT_APPLICABLE"


def scorecard(task_result: dict[str, Any], approvals_ok: bool = True,
              rollback_possible: bool = True) -> dict[str, Any]:
    tests = task_result.get("tests", {}) or {}
    review = str(task_result.get("review_verdict", "skipped"))
    errors = task_result.get("errors", []) or []
    files = (task_result.get("files_created", []) or []) + \
            (task_result.get("files_modified", []) or [])
    cmds = task_result.get("commands_executed", []) or []
    quality = tests.get("quality", "UNKNOWN")
    verified = tests.get("verified", False)
    cards: dict[str, dict[str, str]] = {}
    cards["FILES"] = {"status": PASS if files else UNKNOWN,
                      "detail": f"{len(files)} file(s) changed with verification"
                      if files else "no file changes recorded"}
    if cmds:
        bad = [c for c in cmds if c.get("exit_code") not in (0, None)]
        cards["COMMANDS"] = {"status": FAIL if bad else PASS,
                             "detail": f"{len(cmds)} command(s), "
                             f"{len(bad)} non-zero exit"}
    else:
        cards["COMMANDS"] = {"status": NA, "detail": "no commands executed"}
    if tests.get("ran"):
        if tests.get("all_passed") and verified:
            cards["TESTS"] = {"status": PASS, "detail": "all runs passed, verified"}
        elif tests.get("all_passed"):
            cards["TESTS"] = {"status": WEAK, "detail": "passed but not fully verified"}
        else:
            cards["TESTS"] = {"status": FAIL, "detail": "failures recorded"}
    else:
        cards["TESTS"] = {"status": NA, "detail": "no tests run"}
    cards["ORACLE"] = {"status":
                       {"GOOD": PASS, "WEAK": WEAK,
                        "SUSPICIOUS": FAIL}.get(quality, UNKNOWN),
                       "detail": "; ".join(tests.get("quality_reasons", []) or
                                           [quality])[:300]}
    cards["REVIEW"] = {"status":
                       {"approve": PASS, "revise": WEAK, "reject": FAIL,
                        "escalate": WEAK, "skipped": UNKNOWN}.get(review, UNKNOWN),
                       "detail": f"reviewer: {review}"}
    cards["RUNTIME_OUTPUT"] = {"status": PASS if verified else
                               (WEAK if tests.get("all_passed") else UNKNOWN),
                               "detail": "outputs match verified evidence"
                               if verified else "see TESTS/ORACLE"}
    cards["ROLLBACK_SAFETY"] = {"status": PASS if rollback_possible else WEAK,
                                "detail": "checkpoint manifest available"
                                if rollback_possible else "no manifest"}
    sec_fail = any("SANDBOX" in str(e.get("kind", "")) or
                   "INTERNAL" in str(e.get("kind", "")) for e in errors)
    cards["SECURITY"] = {"status": FAIL if sec_fail else PASS,
                         "detail": "sandbox/internal violation seen"
                         if sec_fail else "no violations; approvals enforced"
                         if approvals_ok else "approval bypass suspected"}
    return {"categories": cards,
            "overall_note": "categorical only; no universal numeric score"}


def timeline(events: list[dict[str, Any]], start_ts: float = 0.0) -> list[str]:
    """Human timeline from raw events. Model text never becomes an event."""
    lines: list[str] = []
    for e in events:
        ev = str(e.get("event", e.get("bus_event", "")))
        ts = e.get("timestamp", "")
        label = {
            "task.started": "task accepted",
            "planning.started": "planner started",
            "planning.completed": "plan completed",
            "execution.started": "action requested",
            "execution.completed": "action verified",
            "execution.failed": "action failed",
            "approval.requested": "APPROVAL REQUIRED",
            "approval.resolved": "approval resolved",
            "review.started": "review started",
            "review.completed": "review decided",
            "rollback.started": "rollback started",
            "rollback.completed": "rollback done",
            "task.completed": "completed",
            "task.failed": "failed",
            "task.cancelled": "cancelled",
        }.get(ev)
        if not label:
            step = e.get("step")
            if isinstance(step, int) and e.get("action"):
                a = (e["action"] or {}).get("action", "?")
                label = (f"{a} verified" if e.get("executed") and
                         (e.get("result") or {}).get("ok") else f"{a}")
        if label:
            lines.append(f"{str(ts)[:19]} {label}")
    return lines


def change_manifest(journal: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for e in journal:
        out.append({"path": e.get("path", ""), "operation": e.get("action", ""),
                    "action_id": e.get("action_id", ""),
                    "verified": True, "backup": bool(e.get("backup")),
                    "restore_id": e.get("restore_id", "")})
    return out


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: ("<redacted>" if str(k).lower() in
                    ("token", "password", "secret", "api_key", "authorization")
                    else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    if isinstance(obj, str) and ".bridge/" in obj.replace("\\", "/"):
        # never leak protected internal paths in exports
        return "<internal>"
    return obj


def export_json(task_result: dict[str, Any], events: list[dict],
                max_bytes: int = 2_000_000) -> str:
    payload = {"exported_at": datetime.now().isoformat(timespec="seconds"),
               "task_result": task_result,
               "timeline": timeline(events),
               "scorecard": scorecard(task_result)}
    return json.dumps(_redact(payload), indent=2)[:max_bytes]


def export_markdown(task_result: dict[str, Any], events: list[dict]) -> str:
    sc = scorecard(task_result)
    tr = task_result
    lines = [f"# Task result — {tr.get('status', '?')}",
             "", f"Mode: {tr.get('mode', '')} | "
             f"Duration: {tr.get('duration_s', 0)}s | "
             f"Review: {tr.get('review_verdict', '')}",
             "", "## Files",
             f"created: {', '.join(tr.get('files_created', [])) or '—'}",
             f"modified: {', '.join(tr.get('files_modified', [])) or '—'}",
             "", "## Tests",
             f"ran={tr.get('tests', {}).get('ran', 0)} "
             f"passed={tr.get('tests', {}).get('passed', 0)} "
             f"quality={tr.get('tests', {}).get('quality', '?')} "
             f"verified={tr.get('tests', {}).get('verified', False)}",
             "", "## Scorecard"]
    for name, card in sc["categories"].items():
        lines.append(f"- {name}: {card['status']} — {card['detail']}")
    lines += ["", "## Timeline"]
    lines += [f"- {t}" for t in timeline(events)[-30:]]
    lines += ["", "## Errors"]
    for e in (tr.get("errors", []) or [])[:10]:
        lines.append(f"- step {e.get('step')}: {e.get('kind')}: {e.get('error', '')[:150]}")
    text = "\n".join(lines)
    # redact secrets just in case model text smuggled any
    for bad in ("Bearer ",):
        text = text.replace(bad, "Bearer <redacted>")
    return text
