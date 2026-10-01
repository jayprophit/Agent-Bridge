"""Typed action intake (POST /v1/actions): an adapter into the execution fabric.

Aetherius already speaks this contract (BridgeActionRequest over
POST /v1/actions), but no such route existed: the request hit a 404 that the
transport normalized into a legitimate-looking FAILED. This module is the other
half. It is an adapter, not a fabric:

    HTTP request
        -> parse (this module)
        -> protocol.validate_action (protocol.py, canonical vocabulary)
        -> actor/session resolution (runtime.py, existing sessions)
        -> policy / P25 authority state (aether_policy_bridge, existing engine)
        -> approval handling (the session's own approval gate)
        -> canonical executor (executor.py, existing dispatch)
        -> journal (the session's own task history and events)
        -> effect/result mapping (task_result fields, existing truth)

Nothing here reimplements validation, approval, policy, execution or
journaling. Every one of those is owned elsewhere and called, never copied.

Permanent:
    SCHEMA VALID   != AUTHORIZED
    REQUEST CLAIM  != AUTHORITY
    HTTP SUCCESS   != EFFECT SUCCESS
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from typing import Any, Callable

TERMINAL_STATUSES = ("COMPLETED", "FAILED", "CANCELLED", "ROLLED_BACK",
                      "INTERRUPTED")

# BridgeActionRequest actions the intake will not carry. `finish` is loop
# control: it ends a model turn, it is never a world effect, and executing it
# outside the loop is meaningless.
REFUSED_VERBS = frozenset({"finish"})

# Actions whose resource names a command rather than a path. For these the
# intake takes the command from payload["command"] (falling back to the
# resource field) and applies the glob rule only; the shell profile, policy
# engine and sandbox still gate what may actually run.
COMMAND_FAMILY = frozenset({"shell", "test"})

# Error strings that are safe to return: they describe the request, never
# internal state, paths outside the workspace, or policy internals.
_BAD_ACTION = "invalid action: must name a known bridge action"
_BAD_RESOURCE = "invalid resource: must be one concrete target"


class DirectedProvider:
    """The action, not a model. Emits the validated action verbatim, then
    finishes. One instance per role so reviewer verdict parsing can never
    re-emit the action as a second step."""

    def __init__(self, action_json: str, model: str = "directed-action"):
        self._script = [action_json,
                        '{"action":"finish","message":"directed action complete"}']
        self.model = model
        self.calls = 0

    def list_models(self) -> list[str]:
        return [self.model]

    def chat(self, messages, temperature: float = 0.1,
             num_predict: int = 640) -> str:
        self.calls += 1
        if self._script:
            return self._script.pop(0)
        return '{"action":"finish","message":"directed action complete"}'


def directed_factory(action: dict[str, Any]) -> Callable[[str], DirectedProvider]:
    payload = json.dumps(action, sort_keys=True)

    def make(role: str) -> DirectedProvider:
        return DirectedProvider(payload)

    return make


def _verb(action_field: Any) -> tuple[str, str]:
    """Split a namespaced `service:verb` or bare `verb` request action.

    Returns (service_or_empty, verb) or ("", "") when malformed.
    """
    if not isinstance(action_field, str) or not action_field:
        return "", ""
    if ":" in action_field:
        service, _, verb = action_field.partition(":")
        if not service or not verb or ":" in verb:
            return "", ""
        return service, verb
    return "", action_field


def build_bridge_action(body: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Translate a BridgeActionRequest body into a bridge action dict.

    Returns (action_dict, "") on success or (None, reason) on refusal. The
    canonical backstop is protocol.validate_action: anything it rejects is
    refused no matter what this mapping produced.
    """
    from protocol import ACTIONS, validate_action

    service, verb = _verb(body.get("action"))
    if not verb:
        return None, _BAD_ACTION
    if verb in REFUSED_VERBS:
        return None, f"unsupported operation: {verb!r} is loop control, not a world action"
    if verb not in ACTIONS:
        return None, f"unknown action: {verb!r}"
    if service:
        # The namespaced form must be the canonical pairing, not an invented
        # one: filesystem:write is real, filesystem:delete-account is not.
        from aether_policy_bridge import action_to_capability as _map
        cap = _map(verb)
        if f"{cap.service}:{cap.action}" != f"{service}:{verb}":
            return None, f"unknown action: {body.get('action')!r}"

    resource = body.get("resource", "")
    if not isinstance(resource, str) or not resource:
        return None, _BAD_RESOURCE
    payload = body.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return None, "invalid payload: must be a JSON object"

    action: dict[str, Any] = {"action": verb}
    if verb in ("move", "copy"):
        dest = payload.get("dest", "")
        if not isinstance(dest, str) or not dest:
            return None, f"invalid resource: {verb!r} needs payload.dest"
        dest_err = _refuse_pattern_or_escape(dest, "destination")
        if dest_err:
            return None, dest_err
        action["src"] = resource
        action["dest"] = dest
        for key, value in payload.items():
            if key != "dest":
                action[key] = value
    elif verb in COMMAND_FAMILY:
        command = payload.get("command", resource)
        if not isinstance(command, str) or not command:
            return None, _BAD_RESOURCE
        action["command"] = command
        for key, value in payload.items():
            if key != "command":
                action[key] = value
    elif verb == "restore":
        action["restore_id"] = payload.get("restore_id", resource)
        for key, value in payload.items():
            if key != "restore_id":
                action[key] = value
    else:
        action["path"] = resource
        action.update(payload)

    ok, validated = validate_action(action)
    if not ok:
        return None, f"invalid action: {validated}"
    return validated, ""


def _refuse_pattern_or_escape(value: str, what: str) -> str:
    """One concrete target, never a pattern and never an escape. Used for the
    resource and, for move/copy, the destination too: authority for a source
    must never be read as covering a destination nobody checked."""
    if any(ch in value for ch in ("*", "?", "[", "]", "{", "}")):
        return f"invalid {what}: patterns are not concrete targets"
    if ".." in value.replace("\\", "/").split("/"):
        return f"invalid {what}: path escapes the workspace"
    if len(value) > 1 and value[1] == ":" or value.startswith("/"):
        return f"invalid {what}: absolute references are refused"
    return ""


def _intake_resource_ok(verb: str, resource: str, workspace: str) -> str:
    """Typed-contract strictness, before the canonical gates run.

    A glob in a typed request is never meaningful: it is a mistake or an
    evasion attempt, and neither deserves execution. Escapes and absolute
    references are refused for path-family actions; the sandbox and policy
    remain the backstop, this is just the intake refusing to ask a question
    it already knows the answer to.
    """
    if verb in COMMAND_FAMILY:
        if any(ch in resource for ch in ("*", "?", "[", "]", "{", "}")):
            return "invalid resource: patterns are not concrete targets"
        return ""
    return _refuse_pattern_or_escape(resource, "resource")


def _principal_error(principal: Any) -> str:
    """Shape-check caller-supplied identity metadata. Absent is fine (legacy
    path); present-but-malformed is a 400, because garbage identity metadata
    must not reach the journal as if it were attribution."""
    if principal is None:
        return ""
    from aether_policy_bridge import parse_principal, validate_principal
    parsed = parse_principal(principal)
    if parsed is None:
        return "invalid principal: must be {kind, id, on_behalf_of?}"
    errors = validate_principal(parsed)
    if errors:
        return "invalid principal: " + "; ".join(errors)
    return ""


def _owner_request(body: dict[str, Any], runtime) -> tuple[bool, str]:
    """Map the wire owner_mode to a session decision. Only "" / SAFE pass
    through as normal; OWNER* demands the runtime's own owner authorization
    (the same rule as session creation); anything else is a 400."""
    mode = body.get("owner_mode", "")
    if mode in ("", "SAFE", "safe"):
        return False, ""
    if mode in ("OWNER", "owner", "OWNER_FULL_ACCESS"):
        if not runtime.cfg.owner_authorized:
            return False, ("owner elevation refused: this runtime is not "
                           "owner-authorized")
        return True, ""
    return False, f"invalid owner_mode: {mode!r}"


def action_fingerprint(action: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(action, sort_keys=True, default=str).encode()).hexdigest()


def map_action_outcome(session, task_id: str, action_id: str,
                       wait_expired: bool = False,
                       wait_ms: int = 0) -> dict[str, Any]:
    """Translate session/task truth into the BridgeOutcome vocabulary.

    Terminal states and waiting approvals map exactly; a task that simply has
    not settled maps to UNKNOWN_OUTCOME with its live status attached, never
    to a fabricated terminal value.
    """
    base = {"action_id": action_id, "session_id": session.session_id,
            "task_id": task_id}
    rec = session.tasks.get(task_id)
    if rec is None:
        out = dict(base)
        out.update({"outcome": "FAILED", "error": "task record lost"})
        return out
    pending = list(session.pending_approvals)
    if rec.status in TERMINAL_STATUSES:
        if rec.status == "CANCELLED":
            out = dict(base)
            out.update({"outcome": "CANCELLED", "status": rec.status})
            return out
        if rec.status != "COMPLETED":
            result = rec.result or {}
            out = dict(base)
            out.update({"outcome": "FAILED", "status": rec.status,
                        "error": str(result.get("finished_reason", rec.status))})
            return out
        result = rec.result or {}
        denied = int(result.get("denied_actions", 0) or 0)
        effected = bool(result.get("effect_achieved", False))
        if denied and not effected:
            kinds = [e.get("kind", "") for e in result.get("errors", [])]
            kinds = [k for k in kinds if k]
            out = dict(base)
            out.update({
                "outcome": "DENIED", "status": rec.status,
                "error": "action denied: " + (", ".join(kinds) or "no effect"),
                "denied_actions": denied, "effect_achieved": False,
                "blocked": bool(result.get("blocked", True)),
                "approvals": result.get("approvals", [])})
            return out
        task_result = result.get("task_result", result)
        out = dict(base)
        out.update({
            "outcome": "SUCCEEDED", "status": rec.status,
            "output": {
                "files_created": task_result.get("files_created", []),
                "files_modified": task_result.get("files_modified", []),
                "files_deleted": task_result.get("files_deleted", []),
                "commands_executed": task_result.get("commands_executed", []),
                "review_verdict": task_result.get("review_verdict", ""),
                "finished_reason": task_result.get("finished_reason", ""),
            },
            "effect_achieved": effected,
            "denied_actions": denied,
            "blocked": False})
        return out
    if pending:
        out = dict(base)
        out.update({"outcome": "WAITING_APPROVAL", "status": rec.status,
                    "approval_id": pending[0], "approval_ids": pending})
        return out
    out = dict(base)
    if wait_expired:
        out.update({
            "outcome": "TIMED_OUT", "status": rec.status,
            "error": (f"action not settled within {wait_ms}ms; "
                      f"GET /v1/actions/{action_id} for the current state")})
    else:
        out.update({"outcome": "UNKNOWN_OUTCOME", "status": rec.status,
                    "note": "task not settled"})
    return out


def submit_directed_action(runtime, body: dict[str, Any],
                           wait_ms: int = 30000) -> tuple[int, dict[str, Any]]:
    """Full intake orchestration. Returns (http_code, response).

    Raises nothing: malformed input becomes 4xx, authority refusals become 403
    or DENIED outcomes, and anything unexpected becomes a 500 with the exception
    class only (never internals).
    """
    import time as _time
    from runtime import TASK_ACTIVE

    action_id = body.get("action_id", "")
    if not isinstance(action_id, str) or not action_id:
        return 400, {"outcome": "FAILED",
                     "error": "invalid action_id: a non-empty id is required"}
    if len(action_id) > 128:
        return 400, {"outcome": "FAILED",
                     "error": "invalid action_id: too long"}

    principal = body.get("principal")
    principal_err = _principal_error(principal)
    if principal_err:
        return 400, {"outcome": "FAILED", "error": principal_err,
                     "action_id": action_id}

    owner, owner_err = _owner_request(body, runtime)
    if owner_err:
        code = 403 if owner_err.startswith("owner elevation refused") else 400
        return code, {"outcome": "FAILED", "error": owner_err,
                      "action_id": action_id}

    workspace_raw = body.get("workspace", "")
    label = body.get("session_id", "")
    if not isinstance(label, str):
        return 400, {"outcome": "FAILED",
                     "error": "invalid session_id", "action_id": action_id}

    # --- session resolution (existing sessions only; ids are never forged)
    session = None
    workspace = ""
    if label:
        try:
            sid = runtime.resolve_session_label(label, workspace_raw or "")
        except ValueError as e:
            return 409, {"outcome": "FAILED", "error": str(e),
                         "action_id": action_id}
        if sid is not None:
            try:
                session = runtime.get_session(sid)
            except KeyError:
                session = None
        if session is None and not workspace_raw:
            return 400, {"outcome": "FAILED",
                         "error": "unknown session label and no workspace "
                                  "to create one",
                         "action_id": action_id}

    # --- action translation + canonical validation (before any state changes)
    action, action_err = build_bridge_action(body)
    if action is None:
        return 400, {"outcome": "FAILED", "error": action_err,
                     "action_id": action_id}
    resource = str(action.get("path", action.get("src", action.get(
        "dest", action.get("command", "")))))
    verb = str(action.get("action", ""))
    ws_for_check = workspace_raw or (str(session.workspace) if session else "")
    strict_err = _intake_resource_ok(verb, resource, ws_for_check) \
        if ws_for_check else ""
    if strict_err:
        return 400, {"outcome": "FAILED", "error": strict_err,
                     "action_id": action_id}
    if principal is not None:
        action["principal"] = principal

    fingerprint = action_fingerprint(action)

    # --- workspace authorization (403 on escape; canonical check)
    try:
        ws = runtime.authorize_workspace(
            workspace_raw or (session.workspace if session else ""))
    except (PermissionError, ValueError) as e:
        return 403, {"outcome": "FAILED", "error": f"workspace refused: {e}",
                     "action_id": action_id}

    # --- collision / replay handling (before creating anything)
    try:
        prior = runtime.lookup_action(action_id)
    except KeyError:
        prior = None
    if prior is not None:
        if prior["fingerprint"] != fingerprint:
            return 409, {"outcome": "FAILED",
                         "error": f"action id collision: {action_id!r} already "
                                  "names a different action",
                         "action_id": action_id}
        try:
            old_session = runtime.get_session(prior["session_id"])
        except KeyError:
            old_session = None
        if old_session is None:
            pass  # prior session is gone; fall through and re-run honestly
        else:
            response = map_action_outcome(old_session, prior["task_id"],
                                          action_id)
            response["deduped"] = True
            return 200, response

    # --- session attach-or-create
    try:
        if session is None:
            if label:
                sid = runtime.resolve_session_label(label, str(ws))
                if sid is not None:
                    session = runtime.get_session(sid)
            if session is None:
                approval = body.get("approval", "")
                if approval is not None and not isinstance(approval, str):
                    return 400, {"outcome": "FAILED",
                                 "error": "invalid approval",
                                 "action_id": action_id}
                interactive = bool(body.get("interactive", False))
                profile = "OWNER_FULL_ACCESS" if owner else ""
                session = runtime.create_session(
                    str(ws), mode="build", approval=approval or "",
                    profile=profile, owner_authorized=owner,
                    interactive=interactive)
                if label:
                    runtime.bind_session_label(label, session.session_id)
        else:
            if str(session.workspace) != str(ws):
                return 409, {"outcome": "FAILED",
                             "error": "session workspace does not match the "
                                      "request workspace",
                             "action_id": action_id}
    except PermissionError as e:
        return 403, {"outcome": "FAILED", "error": str(e),
                     "action_id": action_id}
    except (ValueError, KeyError) as e:
        return 400, {"outcome": "FAILED", "error": str(e),
                     "action_id": action_id}

    # --- directed submission (the decided action; no model is involved)
    text = (f"directed action {action_id}: {verb} {resource} "
            f"(BridgeActionRequest intake; no model involved)")
    try:
        task_id = session.submit_task(
            text, idempotency_key=action_id,
            provider_factory=directed_factory(action))
    except (ValueError, KeyError) as e:
        return 400, {"outcome": "FAILED", "error": str(e),
                     "action_id": action_id}
    deduped = bool(session.last_submit_deduped)
    try:
        runtime.register_action(action_id, session.session_id, task_id,
                                 fingerprint)
    except ValueError as e:
        return 409, {"outcome": "FAILED", "error": str(e),
                     "action_id": action_id}

    # --- bounded wait: approval pause returns promptly, terminal maps exactly
    wait_ms = max(0, min(int(wait_ms), 300000))
    deadline = _time.time() + wait_ms / 1000.0
    while True:
        with session.lock:
            rec = session.tasks.get(task_id)
            status = rec.status if rec else "UNKNOWN"
            waiting = bool(session.pending_approvals) and \
                status in TASK_ACTIVE
            terminal = status in TERMINAL_STATUSES
        if terminal or waiting:
            break
        if _time.time() >= deadline:
            response = map_action_outcome(session, task_id, action_id,
                                          wait_expired=True, wait_ms=wait_ms)
            response["deduped"] = deduped
            return 200, response
        _time.sleep(0.15)

    response = map_action_outcome(session, task_id, action_id)
    response["deduped"] = deduped
    return 200, response


def action_status(runtime, action_id: str) -> tuple[int, dict[str, Any]]:
    """Current outcome for a previously accepted action."""
    try:
        entry = runtime.lookup_action(action_id)
    except KeyError:
        return 404, {"outcome": "FAILED",
                     "error": f"unknown action: {action_id}"}
    try:
        session = runtime.get_session(entry["session_id"])
    except KeyError:
        return 200, {"action_id": action_id,
                     "session_id": entry["session_id"],
                     "task_id": entry["task_id"],
                     "outcome": "FAILED",
                     "error": "session is gone; outcome unrecoverable"}
    return 200, map_action_outcome(session, entry["task_id"], action_id)
