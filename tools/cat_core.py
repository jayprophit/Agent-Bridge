"""Adapter catalog, batch 1: filesystem/shell/code/test/git/http/browser/
process/package/system. Real backends (v0.6 modules), honest probes."""
from __future__ import annotations

from typing import Any

from tools.adapter import ToolAdapter
from tools.registry import (ADMIN, ADMIN_REQUIRED, AVAILABLE, DESTRUCTIVE,
                            INSTALL, MODEL_REQUIRED, MUTATING_LOCAL, NETWORK,
                            NOT_INSTALLED, PROVIDER_REQUIRED, READ_ONLY,
                            SAFE_LOCAL, UNAVAILABLE, UNKNOWN,
                            UNSUPPORTED_PLATFORM, ToolRecord)

SAFE_PROFILES = ["SAFE_EXPLORATION", "ASSISTED_BUILD", "AUTONOMOUS_SANDBOX",
                 "PRECIOUS_PROJECT", "OWNER_FULL_ACCESS"]
READ_PROFILES = SAFE_PROFILES
OWNER_ONLY = ["OWNER_FULL_ACCESS"]


def _rec(tool_id, family, display, desc, backend, risk, status=AVAILABLE,
         available=True, installed=True, profiles=None, tags=(),
         inschema=None, auto=False, cancel=False, rollback=False,
         audit=True, requires_network="", requires_admin=False,
         requires_model="", needs_install="", limitations="", provider="",
         streaming=False, progress=False):
    return ToolRecord(
        tool_id=tool_id, tool_family=family, display_name=display,
        description=desc, status=status, backend=backend, provider=provider,
        available=available, installed=installed,
        requires_install=needs_install, requires_admin=requires_admin,
        requires_network=requires_network,
        requires_model_capability=requires_model,
        input_schema=inschema or {"type": "object", "properties": {}},
        output_schema={"type": "object"},
        risk_class=risk, supported_profiles=profiles if profiles is not None
        else list(SAFE_PROFILES),
        supports_auto_approve=auto, supports_cancel=cancel,
        supports_rollback=rollback, supports_audit=audit,
        supports_streaming=streaming, supports_progress=progress,
        capability_tags=list(tags), limitations=limitations)


class _ExecAdapter(ToolAdapter):
    """Base: delegates to a live v0.6 Executor supplied via context."""

    def __init__(self, ctx: dict):
        self.ctx = ctx

    @property
    def ex(self):
        return self.ctx["executor"]

    def _run_action(self, action: dict) -> dict:
        res = self.ex.dispatch(dict(action))
        ok, why = self.verify(res)
        res["verified"] = ok
        if not ok:
            res["verify_note"] = why
        return res


# -- filesystem ---------------------------------------------------------------
class FsAdapter(_ExecAdapter):
    MAP = {"filesystem.list": "list", "filesystem.read": "read",
           "filesystem.search": "search", "filesystem.stat": "stat",
           "filesystem.exists": "exists", "filesystem.mkdir": "mkdir",
           "filesystem.write": "write", "filesystem.edit": "edit",
           "filesystem.patch": "patch", "filesystem.copy": "copy",
           "filesystem.move": "move", "filesystem.rename": "move",
           "filesystem.recycle": "delete", "filesystem.delete": "delete",
           "filesystem.restore": "restore", "filesystem.diff": "diff"}

    def __init__(self, ctx, tool_id):
        super().__init__(ctx)
        self.tool_id = tool_id

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "executor filesystem backend present"}

    def validate(self, arguments):
        if not isinstance(arguments, dict):
            return False, "arguments must be an object"
        return True, ""

    def execute(self, arguments, context=None):
        act = dict(arguments)
        act["action"] = self.MAP[self.tool_id]
        if self.tool_id == "filesystem.recycle":
            act["action"] = "delete"
        return self._run_action(act)


def fs_records() -> list[ToolRecord]:
    ro = dict(profiles=list(READ_PROFILES), auto=True)
    mut = dict(profiles=list(SAFE_PROFILES), auto=True, rollback=True)
    items = [
        ("filesystem.list", "read a directory", {"path": {"type": "string"}},
         READ_ONLY, ro),
        ("filesystem.read", "read a text file",
         {"path": {"type": "string"}}, READ_ONLY, ro),
        ("filesystem.search", "regex search inside workspace",
         {"pattern": {"type": "string"}, "path": {"type": "string"}}, READ_ONLY, ro),
        ("filesystem.stat", "file metadata",
         {"path": {"type": "string"}}, READ_ONLY, ro),
        ("filesystem.exists", "existence check",
         {"path": {"type": "string"}}, READ_ONLY, ro),
        ("filesystem.mkdir", "create directories",
         {"path": {"type": "string"}}, MUTATING_LOCAL, mut),
        ("filesystem.write", "create/overwrite a text file",
         {"path": {"type": "string"}, "content": {"type": "string"}},
         MUTATING_LOCAL, mut),
        ("filesystem.edit", "exact-text replacement",
         {"path": {"type": "string"}, "old": {"type": "string"},
          "new": {"type": "string"}}, MUTATING_LOCAL, mut),
        ("filesystem.patch", "multi-hunk patch with dry-run",
         {"path": {"type": "string"}, "edits": {"type": "array"}},
         MUTATING_LOCAL, mut),
        ("filesystem.copy", "copy a file",
         {"src": {"type": "string"}, "dest": {"type": "string"}},
         MUTATING_LOCAL, mut),
        ("filesystem.move", "move a file",
         {"src": {"type": "string"}, "dest": {"type": "string"}},
         MUTATING_LOCAL, mut),
        ("filesystem.rename", "rename (move) a file",
         {"src": {"type": "string"}, "dest": {"type": "string"}},
         MUTATING_LOCAL, mut),
        ("filesystem.recycle", "safe delete to recycle area",
         {"path": {"type": "string"}}, MUTATING_LOCAL, mut),
        ("filesystem.delete", "delete (recycles by default)",
         {"path": {"type": "string"}}, MUTATING_LOCAL, mut),
        ("filesystem.restore", "restore recycled content",
         {"restore_id": {"type": "string"}}, MUTATING_LOCAL, mut),
        ("filesystem.diff", "unified diff (file/session/checkpoint)",
         {"target": {"type": "string"}}, READ_ONLY, ro),
    ]
    out = []
    for tid, desc, props, risk, kw in items:
        out.append(_rec(tid, "filesystem", tid.split(".")[1].replace("_", " "),
                        desc, "executor", risk, tags=("file", "fs"),
                        inschema={"type": "object", "properties": props}, **kw))
    # hash/compare/watch: real via executor-adjacent helpers
    out.append(_rec("filesystem.hash", "filesystem", "hash",
                    "SHA-256 hash of a file", "executor", READ_ONLY,
                    tags=("file", "integrity"),
                    inschema={"type": "object",
                              "properties": {"path": {"type": "string"}}},
                    **ro))
    out.append(_rec("filesystem.compare", "filesystem", "compare",
                    "byte-compare two files", "executor", READ_ONLY,
                    tags=("file", "integrity"),
                    inschema={"type": "object",
                              "properties": {"a": {"type": "string"},
                                             "b": {"type": "string"}}},
                    **ro))
    out.append(_rec("filesystem.watch", "filesystem", "watch",
                    "one-shot directory snapshot for change detection",
                    "executor", READ_ONLY, tags=("file", "watch"),
                    inschema={"type": "object",
                              "properties": {"path": {"type": "string"}}},
                    **ro))
    return out


# -- shell ----------------------------------------------------------------------
class ShellAdapter(_ExecAdapter):
    def __init__(self, ctx, tool_id):
        super().__init__(ctx)
        self.tool_id = tool_id

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "executor shell backend present"}

    def validate(self, arguments):
        if not isinstance(arguments, dict) or \
                not str(arguments.get("command", "")).strip():
            return False, "shell needs a non-empty 'command'"
        return True, ""

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".")[1]
        if sub in ("powershell", "cmd", "bash", "script"):
            runners = {"powershell": "powershell -NoProfile -Command ",
                       "cmd": "cmd /c ", "bash": "bash -lc ",
                       "script": "", "run": ""}
            cmd = runners[sub] + str(arguments.get("command", ""))
            return self._run_action({"action": "shell", "command": cmd})
        if sub == "environment":
            import os
            safe = {k: v for k, v in os.environ.items()
                    if "key" not in k.lower() and "secret" not in k.lower()
                    and "token" not in k.lower() and "password" not in k.lower()}
            return {"ok": True, "vars": sorted(safe)[:200],
                    "note": "values redacted broadly"}
        if sub == "which":
            import shutil
            name = str(arguments.get("command", "") or arguments.get("name", ""))
            found = shutil.which(name)
            return {"ok": bool(found), "name": name, "path": found or ""}
        if sub == "cwd":
            return {"ok": True, "cwd": str(self.ex.workspace)}
        return {"ok": False, "error": f"unknown shell subtool: {sub!r}"}


def shell_records(owner: bool = False) -> list[ToolRecord]:
    profs = list(SAFE_PROFILES)
    items = [
        ("shell.run", "run a command with exit/stdout/stderr evidence",
         SAFE_LOCAL if not owner else MUTATING_LOCAL),
        ("shell.powershell", "run PowerShell", MUTATING_LOCAL),
        ("shell.cmd", "run cmd.exe", MUTATING_LOCAL),
        ("shell.bash", "run bash where available", MUTATING_LOCAL),
        ("shell.script", "run a script file", MUTATING_LOCAL),
        ("shell.environment", "list safe environment names", READ_ONLY),
        ("shell.which", "locate an executable", READ_ONLY),
        ("shell.cwd", "current working directory", READ_ONLY),
    ]
    out = []
    for tid, desc, risk in items:
        out.append(_rec(tid, "shell", tid.split(".")[1], desc, "executor",
                        risk, profiles=profs, auto=True, cancel=True,
                        tags=("command", "run"),
                        inschema={"type": "object",
                                  "properties": {"command": {"type": "string"}}}))
    return out


# -- code / test ------------------------------------------------------------------
class CodeAdapter(_ExecAdapter):
    def __init__(self, ctx, tool_id):
        super().__init__(ctx)
        self.tool_id = tool_id

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "executor + local model backends present"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("read", "edit", "patch"):
            act = {"read": "read", "edit": "edit",
                   "patch": "patch"}[sub]
            return self._run_action({"action": act, **arguments})
        if sub == "generate":
            provider = (context or {}).get("provider")
            if provider is None:
                return {"ok": False,
                        "error": "MODEL_REQUIRED: code.generate needs a model"}
            prompt = str(arguments.get("prompt", ""))
            if not prompt:
                return {"ok": False, "error": "code.generate needs 'prompt'"}
            try:
                text = provider.chat(
                    [{"role": "system", "content": "Emit only the requested code."},
                     {"role": "user", "content": prompt}])
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"generation failed: {e}"}
            return {"ok": True, "code": text[:8000],
                    "note": "model-generated; not executed or verified"}
        if sub in ("debug", "explain"):
            return {"ok": False,
                    "error": "MODEL_REQUIRED: route via coder role instead"}
        if sub in ("format", "lint", "typecheck", "compile"):
            tool = {"format": "black", "lint": "ruff",
                    "typecheck": "mypy", "compile": "python"}[sub]
            import shutil
            if sub == "compile":
                target = str(arguments.get("path", ""))
                if not target:
                    return {"ok": False, "error": "compile needs 'path'"}
                return self._run_action(
                    {"action": "shell",
                     "command": f"python -m py_compile {target}"})
            exe = shutil.which(tool)
            if not exe:
                return {"ok": False, "status": NOT_INSTALLED,
                        "error": f"{tool} not installed"}
            target = str(arguments.get("path", ""))
            flag = {"format": "--check", "lint": "check",
                    "typecheck": ""}[sub]
            return self._run_action(
                {"action": "shell",
                 "command": f"{exe} {flag} {target}".strip()})
        if sub == "run":
            target = str(arguments.get("path", ""))
            if not target:
                return {"ok": False, "error": "code.run needs 'path'"}
            return self._run_action({"action": "shell",
                                     "command": f"python {target}"})
        if sub in ("dependencies", "project_detect"):
            from pathlib import Path
            ws = Path(str((context or {}).get("workspace", ".")
                          or self.ex.workspace))
            found = {"requirements": (ws / "requirements.txt").exists(),
                     "pyproject": (ws / "pyproject.toml").exists(),
                     "package_json": (ws / "package.json").exists()}
            if sub == "project_detect":
                kinds = [k for k, v in found.items() if v]
                return {"ok": True, "detected": kinds or ["none"]}
            req = ws / "requirements.txt"
            if req.exists():
                try:
                    return {"ok": True,
                            "dependencies": req.read_text()[:2000].splitlines()}
                except OSError as e:
                    return {"ok": False, "error": str(e)}
            return {"ok": True, "dependencies": []}
        if sub == "refactor":
            return {"ok": False,
                    "error": "MODEL_REQUIRED: refactor via coder role + patch tool"}
        return {"ok": False, "error": f"unknown code subtool: {sub!r}"}


def code_records() -> list[ToolRecord]:
    impl = {"code.generate", "code.read", "code.edit", "code.patch",
            "code.run", "code.dependencies", "code.project_detect"}
    out = []
    for tid in ("code.generate", "code.read", "code.edit", "code.patch",
                "code.refactor", "code.debug", "code.explain", "code.format",
                "code.lint", "code.typecheck", "code.compile", "code.run",
                "code.dependencies", "code.project_detect"):
        risk = MUTATING_LOCAL if tid in (
            "code.generate", "code.edit", "code.patch", "code.refactor",
            "code.run") else (SAFE_LOCAL if tid in (
                "code.compile", "code.lint", "code.typecheck") else READ_ONLY)
        out.append(_rec(tid, "code", tid.split(".")[1], tid, "executor+model",
                        risk, tags=("code",),
                        inschema={"type": "object",
                                  "properties": {"prompt": {"type": "string"},
                                                 "path": {"type": "string"}}}))
    return out


def detect_test_runner(workspace) -> dict[str, Any]:
    """Detect project test configuration (v0.8.1).

    Order: explicit project config first, then installed runners, then
    stdlib unittest discovery. Never installs anything; a configured-but-
    missing pytest is reported as a dependency requirement.
    """
    import shutil
    from pathlib import Path
    ws = Path(str(workspace or "."))
    has_pytest_cfg = (ws / "pytest.ini").exists() or (
        (ws / "pyproject.toml").exists() and "[tool.pytest" in
        (ws / "pyproject.toml").read_text(
            encoding="utf-8", errors="replace")[:4000]) or (
        (ws / "setup.cfg").exists() and "[tool:pytest]" in
        (ws / "setup.cfg").read_text(
            encoding="utf-8", errors="replace")[:2000])
    has_unittest = any(ws.glob("test_*.py")) or any(ws.glob("tests/test_*.py"))
    pytest = shutil.which("pytest")
    package_json = ws / "package.json"
    if has_pytest_cfg:
        if pytest:
            return {"runner": "pytest", "command": "python -m pytest",
                    "reason": "project configures pytest and it is installed"}
        return {"runner": "pytest", "command": "",
                "reason": "project configures pytest but it is not installed",
                "dependency": "pytest"}
    if package_json.exists():
        return {"runner": "npm", "command": "npm test",
                "reason": "package.json present (node runner; not auto-installed)"}
    if has_unittest:
        return {"runner": "unittest", "command": "python -m unittest",
                "reason": "unittest-style tests found; stdlib runner"}
    if pytest:
        return {"runner": "pytest", "command": "python -m pytest",
                "reason": "pytest installed, no contrary config"}
    return {"runner": "unittest", "command": "python -m unittest",
            "reason": "stdlib fallback"}


class TestAdapter(_ExecAdapter):
    def __init__(self, ctx, tool_id):
        super().__init__(ctx)
        self.tool_id = tool_id

    def probe(self):
        import shutil
        have_pytest = bool(shutil.which("pytest"))
        return {"available": True, "status": AVAILABLE,
                "reason": "executor test backend present",
                "pytest": have_pytest}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        mapping = {"detect": None, "run": "test", "unit": "test",
                   "integration": "test", "e2e": "test", "regression": "test",
                   "lint": "shell", "typecheck": "shell", "build": "shell",
                   "benchmark": "shell", "coverage": "shell"}
        if sub == "detect":
            from pathlib import Path
            ws = self.ex.workspace
            found = [str(p.relative_to(ws)) for p in ws.rglob("test_*.py")]
            found += [str(p.relative_to(ws)) for p in ws.rglob("*_test.py")]
            return {"ok": True, "tests": found[:100]}
        cmd = str(arguments.get("command", ""))
        if not cmd:
            if sub in ("run", "unit", "integration", "e2e", "regression"):
                detected = detect_test_runner(self.ex.workspace)
                if detected.get("dependency") and not detected.get("command"):
                    return {"ok": False, "status": NOT_INSTALLED,
                            "error": f"test runner required but missing: "
                                     f"{detected['dependency']} "
                                     f"({detected['reason']})",
                            "detected": detected}
                cmd = {"run": detected["command"],
                       "unit": detected["command"],
                       "integration": detected["command"] + " -m integration"
                       if detected["runner"] == "pytest" else detected["command"],
                       "e2e": detected["command"] + " -m e2e"
                       if detected["runner"] == "pytest" else detected["command"],
                       "regression": detected["command"] + " -m regression"
                       if detected["runner"] == "pytest" else detected["command"]}[sub]
            else:
                defaults = {"lint": "ruff check .", "typecheck": "mypy .",
                            "build": "python -m build",
                            "benchmark": "python -m pytest --benchmark-only",
                            "coverage": "python -m pytest --cov=."}
                cmd = defaults[sub]
        kind = mapping[sub]
        res = self._run_action({"action": kind, "command": cmd})
        if kind == "shell" and "not installed" in str(res.get("error", "")):
            res["status"] = NOT_INSTALLED
        return res


def test_records() -> list[ToolRecord]:
    out = []
    for tid in ("test.detect", "test.run", "test.unit", "test.integration",
                "test.e2e", "test.regression", "test.lint", "test.typecheck",
                "test.build", "test.benchmark", "test.coverage"):
        risk = READ_ONLY if tid == "test.detect" else SAFE_LOCAL
        out.append(_rec(tid, "test", tid.split(".")[1], tid, "executor",
                        risk, tags=("test",),
                        inschema={"type": "object",
                                  "properties": {"command": {"type": "string"}}}))
    return out
