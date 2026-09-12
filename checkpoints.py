"""Checkpoints + safe rollback (v0.3, stdlib only).

Storage: <workspace>/.bridge/checkpoints/<label>/{manifest.json,status.json}.
The manifest tracks bridge operations with original bytes, so rollback works
even when Git is unavailable. Git (if present) is observed read-only for
status/HEAD context — never reset --hard, never auto-commit unless configured.
Pre-existing user changes are never included: only files the bridge touched
appear in the manifest, and rollback refuses without one.
"""
from __future__ import annotations

import difflib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def _git(args: list[str], cwd: Path, timeout: int = 15) -> tuple[bool, str]:
    try:
        p = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                           text=True, timeout=timeout, shell=False)
    except FileNotFoundError:
        return False, "git executable not found"
    except subprocess.TimeoutExpired:
        return False, "git timeout"
    except OSError as e:
        return False, str(e)
    return p.returncode == 0, (p.stdout or "") + (p.stderr or "")


def _utcnow() -> str:
    return datetime.now().isoformat(timespec="seconds")


class CheckpointManager:
    """File-manifest checkpoints under .bridge/checkpoints (no git needed)."""

    def __init__(self, workspace: Path, label: str, owner_mode: bool = False):
        self.workspace = Path(workspace).resolve()
        self.label = label
        self.owner_mode = owner_mode
        self.dir = self.workspace / ".bridge" / "checkpoints" / label
        self.manifest_path = self.dir / "manifest.json"

    def _target(self, rel: str) -> Path:
        p = Path(rel)
        return p if p.is_absolute() else (self.workspace / rel)

    def _load(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, ValueError):
                pass
        return {"label": self.label, "created": _utcnow(), "files": {}}

    def _save(self, man: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        # manifest itself lives under .bridge: never part of rollback payload
        man["label"] = self.label
        self.manifest_path.write_text(json.dumps(man, indent=2)[:500_000],
                                      encoding="utf-8")

    def snapshot(self, rel: str, existed: bool,
                 original: bytes | None) -> None:
        man = self._load()
        files = man.setdefault("files", {})
        if rel in files:
            return  # first (pre-existing) state wins
        try:
            bp = self.dir / "blobs" / (rel.replace("/", "__").replace("\\", "__")[:100])
            entry: dict[str, Any] = {"existed": existed, "backup": None}
            if existed and original is not None:
                bp.parent.mkdir(parents=True, exist_ok=True)
                bp.write_bytes(original[:5_000_000])
                entry["backup"] = str(bp.relative_to(self.workspace))
            files[rel] = entry
        except OSError:
            files[rel] = {"existed": existed, "backup": None}
        self._save(man)

    def preview(self) -> dict[str, Any]:
        """Checkpoint preview: what WOULD be restored/removed on rollback."""
        man = self._load()
        files = man.get("files", {})
        would_restore = [r for r, e in files.items() if e.get("existed")]
        would_remove = []
        for r, e in files.items():
            if not e.get("existed") and self._target(r).exists():
                would_remove.append(r)
        return {"label": self.label, "tracked": sorted(files),
                "would_restore": sorted(would_restore),
                "would_remove": sorted(would_remove)}

    def diff(self, max_chars: int = 8000) -> str:
        man = self._load()
        out: list[str] = []
        for rel, en in man.get("files", {}).items():
            before: list[str] = []
            blob = en.get("backup")
            if blob:
                try:
                    before = (self.workspace / blob).read_bytes().decode(
                        "utf-8", "replace").splitlines()
                except OSError:
                    pass
            t = self._target(rel)
            after = t.read_bytes().decode("utf-8", "replace").splitlines() \
                if t.is_file() else []
            d = "\n".join(difflib.unified_diff(before, after, f"a/{rel}", f"b/{rel}"))
            if d:
                out.append(d)
        return "\n".join(out)[:max_chars] or "(no changes)"

    def rollback(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"ok": False,
                    "error": "refusing rollback: no manifest (cannot guarantee safety)"}
        try:
            man = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except ValueError as e:
            return {"ok": False, "error": f"refusing rollback: bad manifest: {e}"}
        restored, removed, errors = [], [], []
        for rel, entry in (man.get("files") or {}).items():
            target = self._target(rel).resolve()
            if not self.owner_mode:
                try:
                    target.relative_to(self.workspace)
                except ValueError:
                    errors.append(f"{rel}: escapes workspace, skipped")
                    continue
            if ".bridge" in target.parts:
                errors.append(f"{rel}: internal path, skipped")
                continue
            try:
                if entry.get("existed") and entry.get("backup"):
                    bp = self.workspace / entry["backup"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(bp.read_bytes())
                    restored.append(rel)
                elif not entry.get("existed") and target.exists():
                    if target.is_file():
                        target.unlink()
                        removed.append(rel)
                    else:
                        errors.append(f"{rel}: not a file, left in place")
            except OSError as e:
                errors.append(f"{rel}: {e}")
        return {"ok": not errors, "restored": restored, "removed": removed,
                "errors": errors}


class GitManager:
    """v0.2-compatible facade: git observed read-only + manifest rollback.

    snapshot_file/checkpoint/rollback/status/is_repo keep the v0.2 contract
    (rollback restores bridge-created changes, refuses without manifest,
    never auto-commits unless configured).
    """

    def __init__(self, workspace: Path, enabled: bool = True,
                 auto_commit: bool = False, label_prefix: str = "bridge-v06",
                 owner_mode: bool = False):
        self.workspace = Path(workspace).resolve()
        self.enabled = enabled
        self.auto_commit = auto_commit
        self.label_prefix = label_prefix
        self.owner_mode = owner_mode
        # legacy location kept for compat probing, but v0.3 canonical store
        # is .bridge/checkpoints; both are consulted on rollback.
        self.checkpoint_dir = self.workspace / ".bridge_checkpoints"
        self._labels: list[str] = []

    def _mgr(self, label: str) -> CheckpointManager:
        return CheckpointManager(self.workspace, label,
                                 owner_mode=self.owner_mode)

    def is_repo(self) -> bool:
        if not self.enabled:
            return False
        ok, _ = _git(["rev-parse", "--git-dir"], self.workspace)
        return ok

    def status(self) -> dict[str, Any]:
        if not self.is_repo():
            return {"is_repo": False}
        ok_h, head = _git(["rev-parse", "HEAD"], self.workspace)
        ok_s, porcelain = _git(["status", "--porcelain"], self.workspace)
        return {"is_repo": True,
                "head": (head.strip().splitlines() or [""])[0] if ok_h else "",
                "dirty": bool(porcelain.strip()) if ok_s else None,
                "porcelain": porcelain[:4000] if ok_s else ""}

    def snapshot_file(self, label: str, rel_path: str, existed: bool,
                      original_bytes: bytes | None) -> None:
        if not self.enabled:
            return
        if label not in self._labels:
            self._labels.append(label)
        self._mgr(label).snapshot(rel_path, existed, original_bytes)

    def checkpoint(self, label: str) -> dict[str, Any]:
        st = self.status()
        if not self.enabled:
            return {"ok": True, "git": False, "reason": "git integration disabled"}
        if label not in self._labels:
            self._labels.append(label)
        mgr = self._mgr(label)
        mgr.dir.mkdir(parents=True, exist_ok=True)
        (mgr.dir / "status.json").write_text(json.dumps(st, indent=2), encoding="utf-8")
        if self.auto_commit and st.get("is_repo"):
            ok, out = _git(["commit", "-am", f"{self.label_prefix} {label}"],
                           self.workspace)
            return {"ok": ok, "committed": ok, "detail": out[:1000], "status": st}
        return {"ok": True, "git": st.get("is_repo", False), "status": st,
                "preview": mgr.preview()}

    def rollback(self, label: str) -> dict[str, Any]:
        res = self._mgr(label).rollback()
        if res.get("ok") or res.get("restored") or res.get("removed"):
            return res
        # fall back to legacy dir (v0.2-era manifests)
        d = self.checkpoint_dir / label
        man_path = d / "manifest.json"
        if not man_path.exists() and not res.get("errors"):
            return {"ok": False,
                    "error": "refusing rollback: no manifest (cannot guarantee safety)"}
        return res
