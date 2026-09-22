"""Sandboxed executor v0.3 (stdlib only). Migrated from v0.2, same API.

New: atomic writes, .bridge internal dir + path protection, safe
recycle/restore (delete recycles by default), multi-hunk patch + dry-run,
diff (file/session/checkpoint without Git), capabilities/status (read-only,
served from bridge-provided context). Verification evidence on every op.
"""
from __future__ import annotations

import difflib
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

BRIDGE_DIR = ".bridge"
PROTECTED_PREFIXES = (BRIDGE_DIR,)


def _safe_name(rel: str) -> str:
    """Filesystem-safe recycle leaf for any rel (relative or absolute)."""
    import hashlib as _hl
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", rel)[-80:] or "file"
    return f"{clean}.{_hl.sha256(rel.encode()).hexdigest()[:12]}"


class SandboxViolation(Exception):
    pass


def _decode_traversal(s: str) -> str:
    prev, cur = "", s
    for _ in range(3):
        cur = urllib.parse.unquote(cur)
        if cur == prev:
            break
        prev = cur
    return cur


def _is_protected_rel(rel: str) -> bool:
    first = rel.replace("\\", "/").split("/", 1)[0].lower()
    return first in PROTECTED_PREFIXES


class Sandbox:
    def __init__(self, workspace: Path):
        ws = Path(workspace).expanduser().resolve()
        if not ws.is_dir():
            raise ValueError(f"workspace is not a directory: {ws}")
        self.workspace = ws

    def resolve(self, user_path: str, allow_internal: bool = False) -> Path:
        if not isinstance(user_path, str):
            raise SandboxViolation("path must be a string")
        if "\x00" in user_path:
            raise SandboxViolation("blocked: null byte in path")
        s = user_path.strip()
        if not s:
            raise SandboxViolation("blocked: empty path")
        if s in (".", "./", ".\\"):
            return self.workspace
        decoded = _decode_traversal(s).replace("\\", "/")
        if decoded != s.replace("\\", "/"):
            dec = decoded.strip()
            segs = [seg.strip().lower() for seg in dec.split("/")]
            if any(seg == ".." for seg in segs):
                raise SandboxViolation(f"blocked: encoded traversal: {user_path!r}")
            if (dec.startswith("/") or re.match(r"^[a-zA-Z]:", dec)
                    or dec.startswith("//")):
                raise SandboxViolation(f"blocked: encoded absolute path: {user_path!r}")
        p = Path(s)
        candidate = p.resolve() if p.is_absolute() else (self.workspace / p).resolve()
        try:
            rel = candidate.relative_to(self.workspace)
        except ValueError:
            raise SandboxViolation(f"blocked: path escapes workspace: {user_path!r}")
        if str(rel) != "." and _is_protected_rel(str(rel)) and not allow_internal:
            raise SandboxViolation(
                "INTERNAL_PROTECTED: .bridge internals are not modifiable "
                f"by model actions: {user_path!r}")
        if os.name == "nt" and ":" in candidate.name:
            raise SandboxViolation("blocked: ADS-style path")
        return candidate


ALLOWED_BINARIES_STRICT = frozenset({"python", "python3", "py"})
ALLOWED_BINARIES_DEV = frozenset({"python", "python3", "py", "dir", "ls", "echo",
                                  "type", "cat", "pwd", "where", "whoami",
                                  "dotnet", "node", "npm"})
BLOCKED_SHELL_TOKENS = ("&&", "||", ";", "|", ">", "<", "`", "$(", "${", "\n", "\r")


def _exe_base(argv0: str) -> str:
    base = os.path.basename(argv0.strip().strip('"').strip("'"))
    low = base.lower()
    return low[:-4] if low.endswith(".exe") else low


def _utcnow() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Executor:
    def __init__(self, workspace: Path, shell_timeout_s: int = 60,
                 max_output_chars: int = 8000, shell_profile: str = "dev",
                 cache: Any | None = None, session_id: str = "",
                 setup_dirs: bool = True, owner_mode: bool = False):
        self.sandbox = Sandbox(workspace)
        self.workspace = self.sandbox.workspace
        self.shell_timeout_s = shell_timeout_s
        self.max_output = max_output_chars
        self.shell_profile = shell_profile
        self.owner_mode = owner_mode
        self.cache = cache
        try:
            if self.cache is not None and hasattr(self.cache, "bind"):
                self.cache.bind(self.workspace)
        except Exception:
            pass
        self.allowlist = (ALLOWED_BINARIES_STRICT if shell_profile == "strict"
                          else ALLOWED_BINARIES_DEV)
        self.session_id = session_id or uuid.uuid4().hex[:12]
        # Managed executors (explicit session_id from bridge/runtime) enforce
        # session-bound policy subjects. Direct/unmanaged use keeps the
        # legacy workspace-only subject and prior behavior.
        self._session_managed = bool(session_id)
        self.journal: list[dict[str, Any]] = []  # mutation evidence for diff/rollback
        self.context: dict[str, Any] = {}  # set by bridge (capabilities/status)
        self.completed: dict[str, dict[str, Any]] = {}  # action_id -> result
        # Per-path write serialization: concurrent same-file writers take
        # turns (write+verify+record), so every writer's self-verification
        # reads back its own content and the file is never torn.
        self._write_locks: dict[str, threading.Lock] = {}
        self._write_locks_guard = threading.Lock()
        if setup_dirs:
            self._ensure_bridge_dirs()

    def _check_policy(self, action: str, resource: str) -> dict[str, Any]:
        """Check policy for an action before execution."""
        from aether_policy_bridge import (
            evaluate_capability_request, action_to_capability,
            workspace_subject,
        )
        ws_str = str(self.workspace.resolve())
        # Normalize resource to workspace-relative forward-slash path
        # so it matches the grant pattern workspace:<ws>/**
        norm_resource = resource.replace("\\", "/")
        if not norm_resource.startswith("workspace:"):
            norm_resource = f"workspace:{ws_str}/{norm_resource}".replace("\\", "/")
        # Shared canonical mapping (same as bridge gate).
        cap = action_to_capability(action)
        capability = f"{cap.service}:{cap.action}"
        subject = workspace_subject(
            ws_str, self.session_id if self._session_managed else "")
        policy_eval = evaluate_capability_request(
            subject=subject,
            capability=capability,
            resource=norm_resource,
            context={
                "timestamp": int(time.time()),
                "network_origin": "local",
                "device_trust": 100,
                "attributes": {
                    "action": action,
                    "executor": True,
                }
            }
        )
        return policy_eval

    def _resolve(self, user_path: str, allow_internal: bool = False) -> Path:
        """Owner-aware path resolution. Safe profiles use the sandbox;
        owner mode uses the machine namespace (still validated)."""
        if self.owner_mode:
            from owner import resolve_owner_path
            return resolve_owner_path(user_path, base=self.workspace)
        return self.sandbox.resolve(user_path, allow_internal=allow_internal)

    def _rel(self, target: Path) -> str:
        """Display path: workspace-relative when possible, else absolute."""
        try:
            return str(target.relative_to(self.workspace))
        except ValueError:
            return str(target)

    def _audit(self, kind: str, detail: dict[str, Any]) -> None:
        """Append-only owner audit trail (model actions can never write here:
        .bridge stays resolve-blocked in both modes)."""
        try:
            import json as _json
            log = self.workspace / BRIDGE_DIR / "logs" / "audit.jsonl"
            log.parent.mkdir(parents=True, exist_ok=True)
            rec = {"timestamp": _utcnow(), "session": self.session_id,
                   "kind": kind}
            rec.update({k: (str(v)[:2000]) for k, v in detail.items()})
            with open(log, "a", encoding="utf-8") as f:
                f.write(_json.dumps(rec) + "\n")
        except OSError:
            pass

    def close_browsers(self) -> dict[str, Any]:
        """Close browser sessions owned by this run (leak prevention)."""
        closed = 0
        try:
            import browser_cdp
            owned = [k for k in list(browser_cdp._OWNED)]
            for key in owned:
                try:
                    browser_cdp._OWNED.pop(key, None).stop()
                    closed += 1
                except Exception:
                    pass
        except Exception:
            pass
        return {"ok": True, "closed": closed}

    # -- internal paths (bridge subsystems only) ---------------------------
    def _ensure_bridge_dirs(self) -> None:
        for sub in ("sessions", "logs", "memory", "recycle", "backups",
                    "cache", "checkpoints"):
            try:
                (self.workspace / BRIDGE_DIR / sub).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

    def _internal(self, *parts: str) -> Path:
        return self.workspace / BRIDGE_DIR / Path(*parts)

    def _cache_invalidate(self, *paths: str) -> None:
        try:
            if self.cache is not None:
                for p in paths:
                    self.cache.invalidate(p)
        except Exception:
            pass

    def _record(self, entry: dict[str, Any]) -> None:
        entry = dict(entry)
        entry.setdefault("timestamp", _utcnow())
        entry.setdefault("session", self.session_id)
        self.journal.append(entry)

    def _admin_gate(self, *targets: Path) -> dict[str, Any] | None:
        """Owner-mode UAC honesty: refuse admin-needing mutations when the
        runtime is not elevated. Safe profiles are unaffected."""
        if not self.owner_mode:
            return None
        from owner import check_admin
        for t in targets:
            denial = check_admin(t)
            if denial:
                self._audit("admin_required", {"target": str(t)})
                return denial
        return None

    # -- atomic write helper ------------------------------------------------
    def _atomic_write_text(self, target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = target.stat().st_mode if target.exists() else None
        fd, tmp = tempfile.mkstemp(dir=str(target.parent),
                                   prefix=".bridge-tmp-", suffix=".part")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, target)  # atomic on same filesystem
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        if mode is not None:
            try:
                os.chmod(target, mode)
            except OSError:
                pass

    # -- file tools ----------------------------------------------------------
    def do_list(self, path: str = ".") -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if not target.exists():
            return {"ok": False, "error": f"not found: {path!r}"}
        if target.is_file():
            return {"ok": True, "path": self._rel(target),
                    "entries": [target.name]}
        try:
            entries = sorted(e.name + ("/" if e.is_dir() else "") for e in target.iterdir())
        except OSError as e:
            return {"ok": False, "error": f"list failed: {e}"}
        rel = "." if target == self.workspace else self._rel(target)
        return {"ok": True, "path": rel, "entries": entries}

    def do_read(self, path: str) -> dict[str, Any]:
        if self.cache is not None:
            try:
                hit = self.cache.get_read(path)
                if hit is not None:
                    return hit
            except Exception:
                pass
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        gated = self._admin_gate(target)
        if gated:
            return gated
        if not target.is_file():
            return {"ok": False, "error": f"file not found: {path!r}"}
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": "file is not valid UTF-8 text"}
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        res: dict[str, Any] = {"ok": True,
                               "path": self._rel(target),
                               "content": content[: self.max_output * 4],
                               "bytes": target.stat().st_size}
        try:
            if self.cache is not None:
                self.cache.put_read(path, target, res)
        except Exception:
            pass
        return res

    def do_write(self, path: str, content: str, action_id: str = "") -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        rel = self._rel(target)
        gated = self._admin_gate(target)
        if gated:
            return gated
        existed = target.is_file()
        original = target.read_bytes() if existed else None
        with self._write_lock_for(target):
            try:
                self._atomic_write_text(target, content)
            except OSError as e:
                return {"ok": False, "error": f"EXECUTION_ERROR: write failed: {e}"}
            try:
                actual = target.read_text(encoding="utf-8")
            except OSError as e:
                return {"ok": False, "error": f"EXECUTION_ERROR: verify failed: {e}"}
            if actual != content:
                return {"ok": False, "error": "EXECUTION_ERROR: content mismatch after write"}
            self._cache_invalidate(path)
            self._record({"action": "write", "action_id": action_id, "path": rel,
                          "existed": existed, "backup": original, "bytes": len(content)})
        return {"ok": True, "path": rel, "bytes": target.stat().st_size, "verified": True}

    def _write_lock_for(self, target: Path) -> threading.Lock:
        """Return (creating if needed) the serialization lock for a path."""
        key = str(target)
        with self._write_locks_guard:
            lock = self._write_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._write_locks[key] = lock
            return lock

    @staticmethod
    def _content_hash(content: str) -> str:
        import hashlib
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def do_edit(self, path: str, old: str, new: str, action_id: str = "",
                expected_hash: str = "") -> dict[str, Any]:
        """Safe edit with re-read/reconcile support (v0.8.1).

        Preferred repair flow: READ (note current_hash) -> VERIFY
        expected_hash -> PRECISE PATCH -> on mismatch RE-READ the
        returned preview -> RECONCILE -> retry with fresh expected_hash
        -> VALIDATE -> atomic WRITE -> VERIFY. expected_hash mismatches
        never mutate: the caller gets current_hash + preview instead.
        """
        if old == new:
            return {"ok": False,
                    "error": "edit refused: old and new are identical (no-op)"}
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if not target.is_file():
            return {"ok": False, "error": f"file not found: {path!r}"}
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        current_hash = self._content_hash(content)
        preview = content[:600]
        if expected_hash and expected_hash != current_hash:
            return {"ok": False, "kind": "EDIT_CONFLICT",
                    "error": "edit refused: file changed since read "
                             "(expected_hash mismatch; no changes made)",
                    "current_hash": current_hash,
                    "expected_hash": expected_hash,
                    "preview": preview}
        if old not in content:
            return {"ok": False, "kind": "EDIT_MISS",
                    "error": "edit failed: target text not found (no changes made)",
                    "current_hash": current_hash, "preview": preview}
        original = content.encode("utf-8")
        try:
            self._atomic_write_text(target, content.replace(old, new, 1))
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: edit write-back failed: {e}"}
        if new not in target.read_text(encoding="utf-8"):
            return {"ok": False, "error": "EXECUTION_ERROR: edit not present after write"}
        self._cache_invalidate(path)
        rel = self._rel(target)
        self._record({"action": "edit", "action_id": action_id, "path": rel,
                      "existed": True, "backup": original})
        new_hash = self._content_hash(target.read_text(encoding="utf-8"))
        return {"ok": True, "path": rel, "replaced": True, "verified": True,
                "current_hash": new_hash}

    # -- multi-hunk patch engine ---------------------------------------------
    @staticmethod
    def _locate(content: str, anchor: str) -> list[int]:
        idx, out = 0, []
        while True:
            i = content.find(anchor, idx)
            if i < 0:
                return out
            out.append(i)
            idx = i + 1

    def _plan_patch(self, content: str, edits: list[dict[str, Any]]) -> tuple[bool, Any]:
        """Dry-run planner: returns (ok, plan-or-error). No mutation."""
        lines = content.splitlines(keepends=True)
        line_starts = [0]
        for ln in lines:
            line_starts.append(line_starts[-1] + len(ln))

        def to_range(pos: int, length: int) -> list[int]:
            import bisect
            l0 = bisect.bisect_right(line_starts, pos) - 1
            l1 = bisect.bisect_right(line_starts, pos + max(length, 1)) - 1
            return [l0 + 1, l1 + 1]  # 1-based

        plan, sim = [], content
        for i, e in enumerate(edits):
            if "old" in e:
                hits = self._locate(sim, e["old"])
                if len(hits) == 0:
                    return False, f"hunk {i}: anchor not found"
                if len(hits) > 1:
                    return False, f"hunk {i}: ambiguous anchor ({len(hits)} matches)"
                plan.append({"hunk": i, "type": "replace",
                             "range": to_range(hits[0], len(e["old"])),
                             "matched": True})
                sim = sim[:hits[0]] + e["new"] + sim[hits[0] + len(e["old"]):]
            else:
                hits = self._locate(sim, e["anchor"])
                if len(hits) == 0:
                    return False, f"hunk {i}: insert anchor not found"
                if len(hits) > 1:
                    return False, f"hunk {i}: ambiguous insert anchor ({len(hits)})"
                at = hits[0] if e["position"] == "before" else hits[0] + len(e["anchor"])
                plan.append({"hunk": i, "type": f"insert-{e['position']}",
                             "range": to_range(hits[0], len(e["anchor"])),
                             "matched": True})
                sim = sim[:at] + e["insert"] + sim[at:]
        return True, {"hunks": plan, "all_matched": True,
                      "would_succeed": True, "result_bytes": len(sim.encode())}

    def do_patch(self, path: str, edits: list[dict[str, Any]] | None = None,
                 old: str | None = None, new: str | None = None,
                 dry_run: bool = False, action_id: str = "") -> dict[str, Any]:
        if edits is None:
            if old is None or new is None:
                return {"ok": False, "error": "patch needs edits or old/new"}
            edits = [{"old": old, "new": new}]

        def _is_noop(e: dict[str, Any]) -> bool:
            if "old" in e:
                return e["old"] == e.get("new", "")
            return not e.get("insert", "")

        if edits and all(_is_noop(e) for e in edits):
            return {"ok": False,
                    "error": "patch refused: all hunks are no-ops"}
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        gated = self._admin_gate(target)
        if gated and not dry_run:
            return gated
        if not target.is_file():
            return {"ok": False, "error": f"file not found: {path!r}"}
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"read failed: {e}"}
        rel = self._rel(target)
        ok, plan = self._plan_patch(content, edits)
        if dry_run:
            if not ok:
                return {"ok": False, "dry_run": True, "path": rel,
                        "error": plan, "would_succeed": False}
            assert isinstance(plan, dict)
            return {"ok": True, "dry_run": True, "path": rel,
                    "hunks": plan["hunks"], "all_matched": True,
                    "would_succeed": True, "result_bytes": plan["result_bytes"],
                    "note": "NOT EXECUTED (dry-run preview)"}
        if not ok:
            return {"ok": False, "error": f"patch failed: {plan}"}
        # apply sequentially (anchors validated against evolving content)
        sim = content
        for e in edits:
            if "old" in e:
                at = sim.find(e["old"])
                sim = sim[:at] + e["new"] + sim[at + len(e["old"]):]
            else:
                at = sim.find(e["anchor"])
                at = at if e["position"] == "before" else at + len(e["anchor"])
                sim = sim[:at] + e["insert"] + sim[at:]
        original = content.encode("utf-8")
        try:
            self._atomic_write_text(target, sim)
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: patch write-back failed: {e}"}
        after = target.read_text(encoding="utf-8")
        for e in edits:
            probe = e.get("new", e.get("insert", ""))
            if probe and probe not in after:
                return {"ok": False, "error": "EXECUTION_ERROR: patch not present after write"}
        self._cache_invalidate(path)
        self._record({"action": "patch", "action_id": action_id, "path": rel,
                      "existed": True, "backup": original,
                      "hunks": len(edits)})
        assert isinstance(plan, dict)
        return {"ok": True, "path": rel, "patched": True,
                "hunks": plan["hunks"], "verified": True}

    def do_mkdir(self, path: str, action_id: str = "") -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        gated = self._admin_gate(target)
        if gated:
            return gated
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: mkdir failed: {e}"}
        if not target.is_dir():
            return {"ok": False, "error": "EXECUTION_ERROR: directory missing after mkdir"}
        rel = self._rel(target)
        self._record({"action": "mkdir", "action_id": action_id, "path": rel,
                      "existed": False, "backup": None})
        return {"ok": True, "path": rel, "verified": True}

    # -- safe recycle / restore ------------------------------------------------
    def do_delete(self, path: str, permanent: bool = False,
                  action_id: str = "") -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if target == self.workspace:
            return {"ok": False, "error": "delete refused: workspace root"}
        gated = self._admin_gate(target)
        if gated:
            return gated
        if not target.exists():
            return {"ok": False, "error": f"not found: {path!r}"}
        rel = self._rel(target)
        if target.is_dir() and not target.is_symlink():
            try:
                target.rmdir()
                self._cache_invalidate(path)
                self._record({"action": "delete-dir", "action_id": action_id,
                              "path": rel, "existed": True, "backup": None})
                return {"ok": True, "path": path, "deleted": True, "verified": True}
            except OSError:
                return {"ok": False, "error": "delete refused: directory not empty"}
        # file/symlink -> recycle (default) or permanent (elevated approval)
        original = target.read_bytes() if target.is_file() else None
        if permanent:
            try:
                target.unlink()
            except OSError as e:
                return {"ok": False, "error": f"EXECUTION_ERROR: delete failed: {e}"}
            self._cache_invalidate(path)
            self._record({"action": "delete-permanent", "action_id": action_id,
                          "path": rel, "existed": True, "backup": original})
            return {"ok": True, "path": path, "deleted": True,
                    "permanent": True, "verified": not target.exists()}
        rid = f"r-{self.session_id}-{uuid.uuid4().hex[:8]}"
        dest = self._internal("recycle", rid, _safe_name(rel))
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(dest))
            meta = {"restore_id": rid, "original_path": rel,
                    "recycle_path": self._rel(dest),
                    "timestamp": _utcnow(), "session": self.session_id,
                    "action_id": action_id}
            (self._internal("recycle", rid, "meta.json")).write_text(
                json.dumps(meta, indent=2), encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: recycle failed: {e}"}
        if target.exists():
            return {"ok": False, "error": "EXECUTION_ERROR: target still exists after recycle"}
        self._cache_invalidate(path)
        self._record({"action": "delete", "action_id": action_id, "path": rel,
                      "existed": True, "backup": original, "restore_id": rid})
        return {"ok": True, "path": path, "deleted": True, "recycled": True,
                "restore_id": rid, "verified": True}

    def do_restore(self, restore_id: str, action_id: str = "") -> dict[str, Any]:
        if not restore_id or "/" in restore_id or "\\" in restore_id or ".." in restore_id:
            return {"ok": False, "error": "invalid restore_id"}
        meta_p = self._internal("recycle", restore_id, "meta.json")
        if not meta_p.exists():
            return {"ok": False, "error": f"unknown restore_id: {restore_id!r}"}
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
        except ValueError:
            return {"ok": False, "error": "corrupt recycle metadata (refusing)"}
        try:
            dest = self._resolve(meta["original_path"])
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        src_dir = self._internal("recycle", restore_id)
        # find recycled payload (original filename under rid dir)
        candidates = [p for p in src_dir.rglob("*") if p.is_file() and p.name != "meta.json"]
        if not candidates:
            return {"ok": False, "error": "recycled content missing (refusing)"}
        if dest.exists():
            return {"ok": False, "error": "restore refused: destination exists"}
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(candidates[0]), str(dest))
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: restore failed: {e}"}
        self._cache_invalidate(meta["original_path"])
        self._record({"action": "restore", "action_id": action_id,
                      "path": meta["original_path"], "existed": False,
                      "backup": None, "restore_id": restore_id})
        return {"ok": True, "path": meta["original_path"], "restored": True,
                "verified": dest.exists()}

    def do_move(self, src: str, dest: str, action_id: str = "") -> dict[str, Any]:
        try:
            s, d = self._resolve(src), self._resolve(dest)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if s == self.workspace or d == self.workspace:
            return {"ok": False, "error": "move refused involving workspace root"}
        gated = self._admin_gate(s, d)
        if gated:
            return gated
        if not s.exists():
            return {"ok": False, "error": f"source not found: {src!r}"}
        orig = s.read_bytes() if s.is_file() else None
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(s), str(d))
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: move failed: {e}"}
        if s.exists() or not d.exists():
            return {"ok": False, "error": "EXECUTION_ERROR: move state invalid after op"}
        self._cache_invalidate(src, dest)
        self._record({"action": "move", "action_id": action_id,
                      "path": self._rel(d), "src": src,
                      "existed": False, "backup": orig})
        return {"ok": True, "src": src, "dest": self._rel(d),
                "verified": True}

    def do_copy(self, src: str, dest: str, action_id: str = "") -> dict[str, Any]:
        try:
            s, d = self._resolve(src), self._resolve(dest)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        gated = self._admin_gate(d)
        if gated:
            return gated
        if not s.is_file():
            return {"ok": False, "error": f"source file not found: {src!r}"}
        try:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(s), str(d))
        except OSError as e:
            return {"ok": False, "error": f"EXECUTION_ERROR: copy failed: {e}"}
        if not d.is_file() or d.stat().st_size != s.stat().st_size:
            return {"ok": False, "error": "EXECUTION_ERROR: copy verification failed"}
        self._cache_invalidate(dest)
        self._record({"action": "copy", "action_id": action_id,
                      "path": self._rel(d),
                      "existed": False, "backup": None})
        return {"ok": True, "src": src, "dest": self._rel(d),
                "verified": True}

    def do_search(self, pattern: str, path: str = ".", glob: str = "") -> dict[str, Any]:
        try:
            base = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if not pattern:
            return {"ok": False, "error": "empty search pattern"}
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return {"ok": False, "error": f"invalid regex: {e}"}
        roots = [base] if base.is_file() else ([p for p in base.rglob("*") if p.is_file()]
                                                if base.is_dir() else [])
        matches: list[dict[str, Any]] = []
        for f in roots[:2000]:
            if BRIDGE_DIR in f.parts and ".bridge_memory" not in f.name:
                pass  # search includes .bridge for auditability (read-only anyway)
            if glob and not fnmatch.fnmatch(f.name, glob):
                continue
            try:
                if f.stat().st_size > 1_000_000:
                    continue
                text = f.read_text(encoding="utf-8", errors="strict")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    try:
                        rel = self._rel(f.resolve())
                    except ValueError:
                        continue
                    matches.append({"file": rel, "line": i, "text": line[:300]})
                    if len(matches) >= 100:
                        return {"ok": True, "matches": matches, "truncated": True}
        return {"ok": True, "matches": matches, "truncated": False}

    def do_exists(self, path: str) -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        return {"ok": True, "path": path, "exists": target.exists(),
                "is_file": target.is_file() if target.exists() else False,
                "is_dir": target.is_dir() if target.exists() else False}

    def do_stat(self, path: str) -> dict[str, Any]:
        try:
            target = self._resolve(path)
        except SandboxViolation as e:
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        if not target.exists():
            return {"ok": False, "error": f"not found: {path!r}"}
        st = target.stat()
        return {"ok": True, "path": self._rel(target),
                "size": st.st_size, "is_file": target.is_file(),
                "is_dir": target.is_dir(), "mtime": st.st_mtime}

    # -- diff (read-only, no git required) ------------------------------------
    def _unified(self, rel: str, before: bytes | None, after: bytes | None) -> str:
        b = (before or b"").decode("utf-8", "replace").splitlines()
        a = (after or b"").decode("utf-8", "replace").splitlines()
        return "\n".join(difflib.unified_diff(b, a, f"a/{rel}", f"b/{rel}"))[:6000]

    def do_diff(self, target: str = "session", path: str = "",
                label: str = "") -> dict[str, Any]:
        if target == "file":
            if not path:
                return {"ok": False, "error": "file diff needs 'path'"}
            try:
                t = self._resolve(path)
            except SandboxViolation as e:
                return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
            rel = self._rel(t)
            before = None
            for entry in reversed(self.journal):
                if entry.get("path") == rel and entry.get("backup") is not None:
                    before = entry["backup"]
                    break
            after = t.read_bytes() if t.is_file() else None
            return {"ok": True, "target": "file", "path": rel,
                    "diff": self._unified(rel, before, after) or "(no changes)"}
        if target == "checkpoint":
            man = self._internal("checkpoints", label, "manifest.json")
            if not man.exists():
                return {"ok": False, "error": f"unknown checkpoint label: {label!r}"}
            try:
                entries = json.loads(man.read_text(encoding="utf-8")).get("files", {})
            except ValueError:
                return {"ok": False, "error": "corrupt checkpoint manifest"}
            diffs = []
            for rel, en in entries.items():
                t = self.workspace / rel
                after = t.read_bytes() if t.is_file() else None
                d = self._unified(rel, en.get("backup"), after)
                if d:
                    diffs.append(d)
            return {"ok": True, "target": "checkpoint", "label": label,
                    "diff": "\n".join(diffs)[:8000] or "(no changes)"}
        diffs = []
        for entry in self.journal:
            rel = entry.get("path", "")
            if not rel:
                continue
            t = self.workspace / rel
            if entry.get("action") in ("write", "edit", "patch"):
                after = t.read_bytes() if t.is_file() else None
                d = self._unified(rel, entry.get("backup"), after)
                if d:
                    diffs.append(d)
            elif entry.get("action") in ("delete",):
                d = self._unified(rel, entry.get("backup"), None)
                if d:
                    diffs.append(d)
            elif entry.get("action") in ("copy", "move", "mkdir"):
                diffs.append(f"+++ {entry['action']} {rel}")
        return {"ok": True, "target": "session",
                "diff": "\n".join(diffs)[:8000] or "(no changes)"}

    # -- read-only introspection ------------------------------------------------
    def do_capabilities(self) -> dict[str, Any]:
        from protocol import ACTIONS, PROTOCOL_VERSION
        c = dict(self.context)
        out: dict[str, Any] = {"ok": True, "protocol_version": PROTOCOL_VERSION,
                "actions": list(ACTIONS),
                "mode": c.get("mode", ""), "approval": c.get("approval", ""),
                "workspace": c.get("workspace_name", "."),
                "shell_profile": c.get("shell_profile", "dev"),
                "test_profile": c.get("test_profile", "python"),
                "reviewer": c.get("reviewer", True),
                "limitations": ["no network installs without approval",
                                "single simple shell commands only",
                                ".bridge internals are model-read-only",
                                "delete recycles by default"]}
        if self.owner_mode and "owner" in c:
            out["owner"] = c["owner"]
            out["limitations"] = ["UAC remains authoritative",
                                  ".bridge audit trail is model-read-only"]
        return out

    def do_status(self) -> dict[str, Any]:
        s = dict(self.context.get("session", {}))
        s.update({"ok": True, "journal_ops": len(self.journal)})
        return s

    # -- shell -------------------------------------------------------------------
    def _shell_allowed(self, command: str) -> str | None:
        if not command.strip():
            return "empty command"
        for tok in BLOCKED_SHELL_TOKENS:
            if tok in command:
                return f"blocked shell token {tok!r} (single simple commands only)"
        try:
            parts = shlex.split(command, posix=False)
        except ValueError as e:
            return f"unparseable command: {e}"
        if not parts:
            return "empty command"
        if _exe_base(parts[0]) not in self.allowlist:
            return (f"blocked executable {parts[0]!r}; profile={self.shell_profile} "
                    f"allowlist={sorted(self.allowlist)} (approval may override)")
        return None

    def do_shell(self, command: str, approval_override: bool = False) -> dict[str, Any]:
        if self.owner_mode or self.shell_profile == "owner":
            return self._do_shell_owner(command)
        denied = self._shell_allowed(command)
        if denied and not (approval_override and "blocked executable" in denied):
            return {"ok": False, "error": denied, "exit_code": None}
        if denied and approval_override and "blocked executable" not in denied:
            return {"ok": False, "error": denied, "exit_code": None}
        try:
            parts = shlex.split(command, posix=False)
        except ValueError as e:
            return {"ok": False, "error": f"unparseable command: {e}", "exit_code": None}
        try:
            proc = subprocess.run(parts, cwd=str(self.workspace), capture_output=True,
                                  text=True, timeout=self.shell_timeout_s, shell=False)
        except FileNotFoundError:
            return {"ok": False, "error": f"executable not found: {parts[0]!r}", "exit_code": None}
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "TIMEOUT: shell timeout", "exit_code": None}
        except OSError as e:
            return {"ok": False, "error": f"shell failed: {e}", "exit_code": None}
        return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
                "stdout": (proc.stdout or "")[: self.max_output],
                "stderr": (proc.stderr or "")[: self.max_output]}

    def _do_shell_owner(self, command: str) -> dict[str, Any]:
        """OWNER shell profile: arbitrary commands as the current Windows
        user token (UAC still applies). Evidence, never claims."""
        from owner import emergency_active
        stopped, _ = emergency_active()
        if stopped:
            return {"ok": False, "error": "EMERGENCY_STOPPED: new commands refused",
                    "exit_code": None}
        if not command.strip():
            return {"ok": False, "error": "empty command", "exit_code": None}
        t0 = time.monotonic()
        try:
            proc = subprocess.Popen(
                command, cwd=str(self.workspace), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, shell=True)
        except OSError as e:
            return {"ok": False, "error": f"launch failed: {e}", "exit_code": None}
        pid = proc.pid
        try:
            out, err = proc.communicate(timeout=self.shell_timeout_s)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except OSError:
                pass
            return {"ok": False, "error": "TIMEOUT: shell timeout",
                    "exit_code": None, "pid": pid}
        res = {"ok": proc.returncode == 0, "command": command,
               "cwd": str(self.workspace), "exit_code": proc.returncode,
               "stdout": (out or "")[: self.max_output],
               "stderr": (err or "")[: self.max_output],
               "duration_s": round(time.monotonic() - t0, 3), "pid": pid}
        self._audit("shell", {"command": command, "exit_code": proc.returncode,
                              "pid": pid})
        return res

    def do_test(self, command: str, approval_override: bool = False) -> dict[str, Any]:
        start = time.monotonic()
        r = self.do_shell(command, approval_override=approval_override)
        dur = round(time.monotonic() - start, 3)
        out = {"command": command, "exit_code": r.get("exit_code"),
               "stdout": r.get("stdout", ""), "stderr": r.get("stderr", ""),
               "duration_s": dur, "passed": bool(r.get("ok")), "ok": bool(r.get("ok"))}
        if not r.get("ok") and r.get("error"):
            out["error"] = r["error"]
        return out

    # -- dispatch ------------------------------------------------------------------
    def dispatch(self, action: dict[str, Any],
                 approval_override: bool = False, action_id: str = "") -> dict[str, Any]:
        from protocol import MUTATING_ACTIONS as _MUT
        # Action-id idempotency: a completed mutation is never re-executed.
        if action_id and action_id in self.completed and action.get("action") in _MUT:
            prior = dict(self.completed[action_id])
            prior["dedup"] = True
            prior["note"] = "duplicate action_id: recorded result returned, not re-executed"
            return prior
        res = self._dispatch_inner(action, approval_override, action_id)
        if action_id and action.get("action") in _MUT:
            self.completed[action_id] = dict(res)
        return res

    def _dispatch_inner(self, action: dict[str, Any],
                        approval_override: bool = False,
                        action_id: str = "") -> dict[str, Any]:
        act = action.get("action")
        # Policy evaluation gate for mutating actions. delete/restore are
        # included: AUTO_SAFE/OWNER grants scope them to the workspace and
        # the approval gate still makes the risk decision.
        mutating_actions = {"write", "edit", "patch", "mkdir", "delete",
                           "restore", "move", "copy", "shell", "test"}
        if act in mutating_actions:
            # Determine resource path
            resource = action.get("path", action.get("src", action.get("dest", action.get("command", ""))))
            policy_eval = self._check_policy(act, resource)
            if not policy_eval.get("allowed", False):
                return {"ok": False, "error": policy_eval.get("reason", "Policy denied"),
                        "kind": "POLICY_DENIED", "executed": False}

        if act == "list":
            return self.do_list(action.get("path", "."))
        if act == "read":
            return self.do_read(action["path"])
        if act == "write":
            return self.do_write(action["path"], action["content"], action_id)
        if act == "edit":
            return self.do_edit(action["path"], action["old"], action["new"], action_id,
                                expected_hash=str(action.get("expected_hash", "") or ""))
        if act == "patch":
            return self.do_patch(action["path"], edits=action.get("edits"),
                                 old=action.get("old"), new=action.get("new"),
                                 dry_run=action.get("dry_run", False), action_id=action_id)
        if act == "mkdir":
            return self.do_mkdir(action["path"], action_id)
        if act == "delete":
            return self.do_delete(action["path"],
                                  permanent=action.get("permanent", False),
                                  action_id=action_id)
        if act == "restore":
            return self.do_restore(action["restore_id"], action_id)
        if act == "move":
            return self.do_move(action["src"], action["dest"], action_id)
        if act == "copy":
            return self.do_copy(action["src"], action["dest"], action_id)
        if act == "search":
            return self.do_search(action["pattern"], action.get("path", "."),
                                  action.get("glob", ""))
        if act == "exists":
            return self.do_exists(action["path"])
        if act == "stat":
            return self.do_stat(action["path"])
        if act == "diff":
            kw: dict[str, Any] = {"target": action.get("target", "session")}
            if "path" in action:
                kw["path"] = action["path"]
            if "label" in action:
                kw["label"] = action["label"]
            return self.do_diff(**kw)
        if act == "capabilities":
            return self.do_capabilities()
        if act == "status":
            return self.do_status()
        if act == "shell":
            return self.do_shell(action["command"], approval_override=approval_override)
        if act == "test":
            return self.do_test(action["command"], approval_override=approval_override)
        if act == "browser":
            return self.do_browser(action, action_id)
        if act == "net":
            return self.do_net(action, action_id)
        if act == "proc":
            return self.do_proc(action, action_id)
        if act == "git":
            return self.do_git(action, action_id)
        if act == "finish":
            return {"ok": True, "finished": True, "message": action.get("message", "")}
        return {"ok": False, "error": f"unknown action {act!r}"}

    # -- owner-only tools (policy gates these to OWNER profile) ------------------
    def _need_owner(self) -> dict[str, Any] | None:
        if not self.owner_mode:
            return {"ok": False,
                    "error": "refused: owner-only tool outside OWNER profile"}
        from owner import emergency_active
        stopped, reason = emergency_active()
        if stopped:
            return {"ok": False, "error": f"EMERGENCY_STOPPED: {reason}"}
        return None

    def do_browser(self, action: dict[str, Any], action_id: str = "") -> dict[str, Any]:
        refused = self._need_owner()
        if refused:
            return refused
        import browser_cdp
        op = action.get("op", "")
        sess_id = f"owner-{self.session_id}"
        try:
            if op == "status":
                import sysinfo
                return {"ok": True, "available": True,
                        "exe": browser_cdp.find_browser()}
            if op == "open":
                sess = browser_cdp.BrowserSession()
                res = sess.launch()
                res.update(sess.open_url(action["url"]))
                browser_cdp._OWNED[sess_id] = sess
                res["session"] = sess_id
                self._audit("browser.open", {"url": action["url"]})
                return res
            sess = browser_cdp._OWNED.get(sess_id)
            if sess is None and op != "close":
                return {"ok": False,
                        "error": "no open browser session: use op=open first"}
            if op == "close":
                if sess is None:
                    return {"ok": True, "closed": True, "note": "none open"}
                out = sess.stop()
                browser_cdp._OWNED.pop(sess_id, None)
                return out
            fn = {"tabs": lambda: {"ok": True, "note": "single-page session"},
                  "back": sess.back, "forward": sess.forward,
                  "reload": sess.reload, "title": lambda: {"ok": True, "title": sess.title()},
                  "url": lambda: {"ok": True, "url": sess.current_url()},
                  "cookies": sess.cookies}.get(op)
            if fn is not None:
                res = fn()
                self._audit("browser." + op, {"session": sess_id})
                return res
            if op == "click":
                res = sess.click(action["selector"])
            elif op == "type":
                res = sess.type_text(action["selector"], action.get("text", ""))
            elif op == "keyboard":
                res = sess.keyboard(action.get("key", "Enter"))
            elif op == "select":
                res = sess.select_option(action["selector"], action.get("value", ""))
            elif op == "scroll":
                res = sess.scroll(action.get("dy", 800))
            elif op == "wait":
                res = sess.wait_for(action["selector"], action.get("timeout_s", 20))
            elif op == "wait_idle":
                res = sess.wait_network_idle(action.get("timeout_s", 20))
            elif op == "text":
                res = sess.dom_text(action.get("selector", "body"),
                                    action.get("max_items", 20000))
            elif op == "links":
                res = sess.links(action.get("max_items", 200))
            elif op == "screenshot":
                dest = action.get("path") or str(
                    self.workspace / f"shot-{sess_id}.png")
                try:
                    d = self._resolve(dest)
                except Exception as e:  # noqa: BLE001
                    return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
                res = sess.screenshot(d)
            elif op == "upload":
                res = sess.upload(action["selector"], action.get("path", ""))
            elif op == "download_page":
                res = sess.dom_text("html", 200000)
                res["url"] = sess.current_url()
            elif op == "paginate":
                res = sess.paginate(action.get("selector", 'a[rel="next"]'),
                                    action.get("max_pages", 20),
                                    action.get("pattern", ""))
            elif op == "infinite":
                res = sess.infinite_scroll(action.get("max_rounds", 15),
                                           action.get("pattern", ""))
            else:
                return {"ok": False, "error": f"unknown browser op: {op!r}"}
            res["session"] = sess_id
            self._audit("browser." + op, {"session": sess_id,
                                          "selector": action.get("selector", "")})
            return res
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"browser failed: {e}"}

    def do_net(self, action: dict[str, Any], action_id: str = "") -> dict[str, Any]:
        refused = self._need_owner()
        if refused:
            return refused
        import net as netmod
        try:
            if action.get("op", "get") == "download":
                dd = self._resolve(action.get("dest") or ".")
                res = netmod.download(action["url"], dd if dd.is_dir() or
                                      not dd.suffix else dd.parent)
            else:
                res = netmod.http_get(action["url"])
                res.pop("_raw", None)
            self._audit("net." + action.get("op", "get"), {"url": action["url"],
                                                           "status": res.get("status")})
            self._record({"action": "net", "action_id": action_id,
                          "path": "", "existed": False, "backup": None})
            return res
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"net failed: {e}"}

    def do_proc(self, action: dict[str, Any], action_id: str = "") -> dict[str, Any]:
        refused = self._need_owner()
        if refused:
            return refused
        import proc as procmod
        op = action.get("op", "")
        try:
            if op == "list":
                res = procmod.list_processes()
            elif op in ("launch",):
                res = procmod.launch(action["command"], cwd=self.workspace,
                                     timeout_s=self.shell_timeout_s)
            elif op == "spawn":
                res = procmod.spawn(action["command"], cwd=self.workspace)
            elif op == "status":
                res = procmod.proc_status(action["pid"])
            elif op == "wait":
                res = procmod.wait_for(action["pid"], 60)
            elif op == "kill":
                res = procmod.terminate(action["pid"])
            else:
                return {"ok": False, "error": f"unknown proc op: {op!r}"}
            self._audit("proc." + op, {"command": action.get("command", ""),
                                       "pid": action.get("pid", "")})
            return res
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"proc failed: {e}"}

    def do_git(self, action: dict[str, Any], action_id: str = "") -> dict[str, Any]:
        refused = self._need_owner()
        if refused:
            return refused
        import gitops
        repo = action.get("repo", ".")
        try:
            rp = self._resolve(repo)
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"SANDBOX_VIOLATION: {e}"}
        res = gitops.operate(rp, action.get("op", ""),
                             action.get("args", []),
                             action.get("message", ""))
        self._audit("git." + action.get("op", ""), {"repo": str(rp),
                                                    "ok": res.get("ok")})
        if res.get("ok") and action.get("op") not in (
                "status", "diff", "branch", "log"):
            self._record({"action": "git:" + action.get("op", ""),
                          "action_id": action_id, "path": str(rp),
                          "existed": True, "backup": None})
        return res


ALLOWED_BINARIES = ALLOWED_BINARIES_DEV
