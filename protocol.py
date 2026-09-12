"""Structured action protocol v0.4 wire format (v0.6 runtime).

Kept (15): list read write edit shell finish mkdir delete move copy patch
search exists stat test.
Kept (4): restore diff capabilities status.
New in v0.6 (4, OWNER profile only): browser net proc git.
"""
from __future__ import annotations

import json
import re
from typing import Any

PROTOCOL_VERSION = "0.4"
ACCEPTED_VERSIONS = ("0.1", "0.2", "0.3", "0.4", "")

ACTIONS = ("list", "read", "write", "edit", "shell", "finish",
           "mkdir", "delete", "move", "copy", "patch",
           "search", "exists", "stat", "test",
           "restore", "diff", "capabilities", "status",
           "browser", "net", "proc", "git")

READ_ONLY_ACTIONS = frozenset({"list", "read", "search", "exists", "stat",
                               "diff", "capabilities", "status"})
MUTATING_ACTIONS = frozenset({"write", "edit", "mkdir", "delete", "move",
                              "copy", "patch", "shell", "test", "restore",
                              "browser", "net", "proc", "git"})
OWNER_ONLY_ACTIONS = frozenset({"browser", "net", "proc", "git"})

_KEY_ALIASES = {
    "filepath": "path", "file_path": "path", "filename": "path", "file": "path",
    "directory": "path", "dir": "path", "folder": "path",
    "oldstring": "old", "old_string": "old", "oldtext": "old", "old_text": "old",
    "target": "old", "needle": "old",
    "newstring": "new", "new_string": "new", "newtext": "new", "new_text": "new",
    "replacement": "new",
    "cmd": "command", "commands": "command",
    "code": "content", "text": "content", "data": "content", "body": "content",
    "tool": "action", "name": "action", "type": "action", "fn": "action",
    "source": "src", "from": "src", "origin": "src",
    "destination": "dest", "to": "dest", "target_path": "dest", "dst": "dest",
    "query": "pattern", "regex": "pattern", "needle_pattern": "pattern",
    "file_pattern": "glob", "include": "glob",
    "anchor_text": "anchor", "insert_text": "insert", "where": "position",
    "hunks": "edits", "changes": "edits", "operations": "edits",
    "preview": "dry_run", "dryrun": "dry_run",
    "permanent_delete": "permanent", "hard": "permanent",
    "recycle_id": "restore_id", "id": "restore_id",
    "diff_target": "target", "kind": "target",
    "operation": "op", "method": "op", "subcommand": "op",
    "address": "url", "link": "url", "href": "url",
    "process": "pid", "process_id": "pid",
    "repository": "repo", "message_text": "message",
}

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_candidate_texts(raw: str) -> list[str]:
    cands = [m.group(1).strip() for m in _FENCE_RE.finditer(raw) if m.group(1).strip()]
    cands.append(raw)
    return cands


def _find_json_objects(text: str) -> list[str]:
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth, in_str, esc, start, j = 0, False, False, i, i
        while j < n:
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(text[start:j + 1])
                        break
            j += 1
        i = (j + 1) if depth == 0 else (start + 1)
    return out


def _canon_key(k: str) -> str:
    key = k.strip()
    for form in (key, key.lower(), key.lower().replace(" ", "").replace("-", "_")):
        if form in _KEY_ALIASES:
            return _KEY_ALIASES[form]
    return key


def normalize_action(obj: dict[str, Any]) -> dict[str, Any]:
    obj = {str(k).strip(): v for k, v in obj.items()}
    if "arguments" in obj and isinstance(obj["arguments"], dict):
        args = {str(k).strip(): v for k, v in obj["arguments"].items()}
        base: dict[str, Any] = {}
        for k in ("action", "name", "tool", "type", "fn"):
            if k in obj:
                base["action"] = obj[k]
                break
        base.update(args)
        obj = base
    for nest in ("parameters", "input", "params"):
        if nest in obj and isinstance(obj[nest], dict) and "action" not in obj:
            obj = dict(obj[nest])
            break
    norm = {_canon_key(k): v for k, v in obj.items()}
    # protocol version passthrough (validated, not executed)
    if "protocol_version" in norm:
        norm["protocol_version"] = str(norm["protocol_version"])
    if isinstance(norm.get("action"), str):
        a = norm["action"].strip().lower().replace("-", "_")
        mapping = {"write_file": "write", "read_file": "read", "list_files": "list",
                   "list_dir": "list", "run": "shell", "run_shell": "shell",
                   "run_command": "shell", "exec": "shell", "bash": "shell",
                   "run_tests": "test", "run_test": "test", "pytest": "test",
                   "remove": "delete", "rm": "delete", "del": "delete",
                   "make_dir": "mkdir", "create_dir": "mkdir",
                   "rename": "move", "find": "search", "grep": "search",
                   "check": "exists", "file_exists": "exists",
                   "info": "stat", "done": "finish", "stop": "finish",
                   "complete": "finish", "apply_patch": "patch",
                   "undelete": "restore", "un_remove": "restore",
                   "show_diff": "diff", "get_status": "status",
                   "caps": "capabilities", "help": "capabilities",
                   "navigate": "browser", "goto": "browser", "browse": "browser",
                   "web_fetch": "net", "fetch": "net", "http_get": "net",
                   "run_process": "proc", "ps": "proc",
                   "git_status": "git"}
        norm["action"] = mapping.get(a, a)
    # legacy single patch -> edits form (kept for v0.1/v0.2 compat)
    if norm.get("action") == "patch" and "edits" not in norm:
        if isinstance(norm.get("old"), str) and isinstance(norm.get("new"), str):
            norm["edits"] = [{"old": norm.pop("old"), "new": norm.pop("new")}]
        elif isinstance(norm.get("anchor"), str) and isinstance(norm.get("insert"), str):
            norm["edits"] = [{"anchor": norm.pop("anchor"),
                              "insert": norm.pop("insert"),
                              "position": norm.pop("position", "after")}]
    return norm


def _need_str(a: dict, f: str, act: str) -> tuple[bool, str]:
    if f not in a:
        return False, f"action '{act}' missing required field: '{f}'"
    if not isinstance(a[f], str):
        return False, f"field '{f}' must be a string"
    if not a[f].strip() and f not in ("new", "message"):
        return False, f"field '{f}' must be a non-empty string"
    return True, ""


def _check_version(a: dict) -> tuple[bool, str]:
    v = str(a.get("protocol_version", ""))
    if v and v not in ACCEPTED_VERSIONS:
        return False, f"unsupported protocol_version {v!r} (bridge speaks {PROTOCOL_VERSION})"
    return True, ""


def _validate_patch_edits(edits: Any) -> tuple[bool, str | list]:
    if not isinstance(edits, list) or not edits:
        return False, "field 'edits' must be a non-empty list"
    clean: list[dict[str, Any]] = []
    for i, e in enumerate(edits):
        if not isinstance(e, dict):
            return False, f"edits[{i}] must be an object"
        e = {_canon_key(k): v for k, v in e.items()}
        if "old" in e and "new" in e:
            if not isinstance(e["old"], str) or not e["old"]:
                return False, f"edits[{i}].old must be a non-empty string"
            if not isinstance(e["new"], str):
                return False, f"edits[{i}].new must be a string"
            clean.append({"old": e["old"], "new": e["new"]})
        elif "anchor" in e and "insert" in e:
            if not isinstance(e["anchor"], str) or not e["anchor"]:
                return False, f"edits[{i}].anchor must be a non-empty string"
            if not isinstance(e["insert"], str):
                return False, f"edits[{i}].insert must be a string"
            pos = str(e.get("position", "after")).lower()
            if pos not in ("before", "after"):
                return False, f"edits[{i}].position must be before|after"
            clean.append({"anchor": e["anchor"], "insert": e["insert"],
                          "position": pos})
        else:
            return False, (f"edits[{i}] must be {{old,new}} or "
                           "{anchor,insert,position}")
    return True, clean


def validate_action(a: Any) -> tuple[bool, dict[str, Any] | str]:
    if not isinstance(a, dict):
        return False, "action must be a JSON object"
    if not isinstance(a.get("action"), str):
        return False, "missing required field: 'action'"
    ok, verr = _check_version(a)
    if not ok:
        return False, verr
    act = a["action"].strip().lower()
    if act not in ACTIONS:
        return False, f"unknown action {act!r}; must be one of {list(ACTIONS)}"

    if act == "list":
        a.setdefault("path", ".")
        ok, err = _need_str(a, "path", act)
        return (True, {"action": "list", "path": a["path"]}) if ok else (False, err)
    if act in ("read", "mkdir", "exists", "stat"):
        ok, err = _need_str(a, "path", act)
        return (True, {"action": act, "path": a["path"]}) if ok else (False, err)
    if act == "delete":
        ok, err = _need_str(a, "path", act)
        if not ok:
            return False, err
        perm = a.get("permanent", False)
        if not isinstance(perm, bool):
            return False, "field 'permanent' must be a boolean"
        return True, {"action": "delete", "path": a["path"], "permanent": perm}
    if act == "write":
        ok, err = _need_str(a, "path", act)
        if not ok:
            return False, err
        if "content" not in a:
            return False, "action 'write' missing required field: 'content'"
        if not isinstance(a["content"], str):
            return False, "field 'content' must be a string"
        return True, {"action": "write", "path": a["path"], "content": a["content"]}
    if act == "edit":
        for f in ("path", "old", "new"):
            if f not in a:
                return False, f"action 'edit' missing required field: '{f}'"
            if not isinstance(a[f], str):
                return False, f"field '{f}' must be a string"
        if not a["path"].strip():
            return False, "field 'path' must be a non-empty string"
        if a["old"] == "":
            return False, "field 'old' must be a non-empty string"
        return True, {"action": "edit", "path": a["path"], "old": a["old"], "new": a["new"]}
    if act == "patch":
        ok, err = _need_str(a, "path", act)
        if not ok:
            return False, err
        if "edits" not in a:
            return False, ("action 'patch' needs 'edits' (or legacy old/new, "
                            "or anchor/insert/position)")
        ok2, res = _validate_patch_edits(a["edits"])
        if not ok2:
            return False, res if isinstance(res, str) else "invalid edits"
        dry = a.get("dry_run", False)
        if not isinstance(dry, bool):
            return False, "field 'dry_run' must be a boolean"
        assert isinstance(res, list)
        return True, {"action": "patch", "path": a["path"], "edits": res,
                      "dry_run": dry}
    if act in ("move", "copy"):
        for f in ("src", "dest"):
            ok, err = _need_str(a, f, act)
            if not ok:
                return False, err
        return True, {"action": act, "src": a["src"], "dest": a["dest"]}
    if act == "restore":
        rid = a.get("restore_id", "")
        if not isinstance(rid, str) or not rid.strip():
            return False, "action 'restore' needs 'restore_id' (see delete result)"
        return True, {"action": "restore", "restore_id": rid.strip()}
    if act == "diff":
        target = str(a.get("target", "session")).lower()
        if target not in ("file", "session", "checkpoint"):
            return False, "diff 'target' must be file|session|checkpoint"
        if target == "file":
            ok, err = _need_str(a, "path", act)
            if not ok:
                return False, err
            return True, {"action": "diff", "target": "file", "path": a["path"]}
        if target == "checkpoint":
            lbl = a.get("label", "")
            if not isinstance(lbl, str) or not lbl.strip():
                return False, "checkpoint diff needs 'label'"
            return True, {"action": "diff", "target": "checkpoint", "label": lbl.strip()}
        return True, {"action": "diff", "target": "session"}
    if act == "search":
        ok, err = _need_str(a, "pattern", act)
        if not ok:
            return False, err
        path = a.get("path", ".")
        glob = a.get("glob", "")
        if not isinstance(path, str) or not isinstance(glob, str):
            return False, "fields 'path'/'glob' must be strings"
        return True, {"action": "search", "pattern": a["pattern"],
                      "path": path or ".", "glob": glob}
    if act in ("shell", "test"):
        ok, err = _need_str(a, "command", act)
        return (True, {"action": act, "command": a["command"]}) if ok else (False, err)
    if act == "browser":
        op = str(a.get("op", "")).strip().lower()
        valid = ("open", "tabs", "back", "forward", "reload", "click", "type",
                 "keyboard", "select", "scroll", "wait", "wait_idle", "text",
                 "links", "title", "url", "screenshot", "cookies", "upload",
                 "download_page", "paginate", "infinite", "close", "status")
        if op not in valid:
            return False, f"browser op must be one of {list(valid)}"
        out: dict[str, Any] = {"action": "browser", "op": op}
        for f in ("url", "selector", "text", "value", "key", "path", "dest",
                  "pattern"):
            if f in a:
                if not isinstance(a[f], str):
                    return False, f"browser field {f!r} must be a string"
                out[f] = a[f]
        for f in ("max_pages", "max_rounds", "timeout_s", "dy", "max_items"):
            if f in a:
                try:
                    out[f] = int(a[f])
                except (TypeError, ValueError):
                    return False, f"browser field {f!r} must be an integer"
        if op in ("open",) and not out.get("url"):
            return False, "browser open needs 'url'"
        if op in ("click", "type", "select", "upload") and not out.get("selector"):
            return False, f"browser {op} needs 'selector'"
        if op == "type" and "text" not in out:
            return False, "browser type needs 'text'"
        return True, out
    if act == "net":
        op = str(a.get("op", "get")).strip().lower()
        if op not in ("get", "download"):
            return False, "net op must be get|download"
        ok, err = _need_str(a, "url", act)
        if not ok:
            return False, err
        out = {"action": "net", "op": op, "url": a["url"]}
        if "dest" in a:
            if not isinstance(a["dest"], str) or not a["dest"].strip():
                return False, "net dest must be a non-empty string"
            out["dest"] = a["dest"]
        return True, out
    if act == "proc":
        op = str(a.get("op", "")).strip().lower()
        if op not in ("list", "launch", "spawn", "status", "wait", "kill"):
            return False, "proc op must be list|launch|spawn|status|wait|kill"
        out = {"action": "proc", "op": op}
        if "command" in a:
            if not isinstance(a["command"], str) or not a["command"].strip():
                return False, "proc command must be a non-empty string"
            out["command"] = a["command"]
        if "pid" in a:
            try:
                out["pid"] = int(a["pid"])
            except (TypeError, ValueError):
                return False, "proc pid must be an integer"
        if op in ("launch", "spawn") and "command" not in out:
            return False, f"proc {op} needs 'command'"
        if op in ("status", "wait", "kill") and "pid" not in out:
            return False, f"proc {op} needs 'pid'"
        return True, out
    if act == "git":
        op = str(a.get("op", "")).strip().lower()
        valid_g = ("status", "diff", "branch", "log", "checkout", "add",
                   "commit", "pull", "fetch", "merge", "rebase", "push")
        if op not in valid_g:
            return False, f"git op must be one of {list(valid_g)}"
        out = {"action": "git", "op": op}
        if "repo" in a:
            if not isinstance(a["repo"], str) or not a["repo"].strip():
                return False, "git repo must be a non-empty string"
            out["repo"] = a["repo"]
        else:
            out["repo"] = "."
        if "message" in a:
            if not isinstance(a["message"], str):
                return False, "git message must be a string"
            out["message"] = a["message"]
        if "args" in a:
            if not isinstance(a["args"], list) or \
                    not all(isinstance(x, str) for x in a["args"]):
                return False, "git args must be a string list"
            out["args"] = a["args"]
        if op == "commit" and not out.get("message"):
            return False, "git commit needs 'message'"
        return True, out
    if act in ("capabilities", "status"):
        return True, {"action": act}
    msg = a.get("message", "")
    if msg is not None and not isinstance(msg, str):
        return False, "field 'message' must be a string"
    return True, {"action": "finish", "message": msg or ""}


def parse_model_output(raw: str) -> tuple[dict[str, Any] | None, str, str]:
    raw_p = raw if isinstance(raw, str) else str(raw)
    if not raw_p.strip():
        return None, raw_p, "empty model response"
    first_err: str | None = None
    for cand in extract_candidate_texts(raw_p):
        for blob in _find_json_objects(cand):
            try:
                obj = json.loads(blob)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            norm = normalize_action(obj)
            if "action" not in norm:
                continue
            ok, res = validate_action(norm)
            if ok:
                assert isinstance(res, dict)
                return res, raw_p, ""
            if first_err is None and isinstance(res, str):
                first_err = res
    if first_err:
        return None, raw_p, first_err
    return None, raw_p, "no valid structured action found (expected one JSON object with 'action')"
