"""Adapter catalog, batch 1b: git/github/http/browser/process/package/system."""
from __future__ import annotations

from typing import Any

from tools.adapter import ToolAdapter
from tools.cat_core import (OWNER_ONLY, READ_PROFILES, SAFE_PROFILES, _rec)
from tools.registry import (ADMIN, AVAILABLE, DEGRADED, EXTERNAL_ACCOUNT,
                            INSTALL, MODEL_REQUIRED, MUTATING_LOCAL, NETWORK,
                            NOT_INSTALLED, PROVIDER_REQUIRED, READ_ONLY,
                            SAFE_LOCAL, UNAVAILABLE, UNKNOWN, ToolRecord)


class GitAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def ex(self):
        return self.ctx["executor"]

    def probe(self):
        import shutil
        ok = bool(shutil.which("git"))
        return {"available": ok, "status": AVAILABLE if ok else NOT_INSTALLED,
                "reason": "git binary present" if ok else "git not installed"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        opmap = {"status": "status", "diff": "diff", "log": "log",
                 "branch": "branch", "checkout": "checkout", "add": "add",
                 "commit": "commit", "fetch": "fetch", "pull": "pull",
                 "push": "push", "merge": "merge", "rebase": "rebase",
                 "tag": "tag", "stash": "stash", "remote": "remote"}
        if sub not in opmap:
            return {"ok": False, "error": f"unknown git subtool: {sub!r}"}
        action = {"action": "git", "op": opmap[sub]}
        for f in ("repo", "message"):
            if f in arguments:
                action[f] = arguments[f]
        if "args" in arguments:
            action["args"] = arguments["args"]
        res = self.ex.dispatch(action)
        ok, why = self.verify(res)
        res["verified"] = ok
        return res


def git_records() -> list[ToolRecord]:
    mut = {"tag", "checkout", "add", "commit", "fetch", "pull", "push",
           "merge", "rebase", "stash"}
    out = []
    for tid in ("git.status", "git.diff", "git.log", "git.branch",
                "git.checkout", "git.add", "git.commit", "git.fetch",
                "git.pull", "git.push", "git.merge", "git.rebase",
                "git.tag", "git.stash", "git.remote"):
        sub = tid.split(".")[1]
        risk = MUTATING_LOCAL if sub in mut else READ_ONLY
        out.append(_rec(tid, "git", sub, tid, "gitops", risk,
                        tags=("git", "vcs"),
                        inschema={"type": "object",
                                  "properties": {"repo": {"type": "string"},
                                                 "message": {"type": "string"},
                                                 "args": {"type": "array"}}}))
    return out


class GithubAdapter(ToolAdapter):
    """Interfaces only: no authenticated backend in v0.7."""

    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    def probe(self):
        return {"available": False, "status": PROVIDER_REQUIRED,
                "reason": "no authenticated GitHub backend configured"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        return {"ok": False, "status": PROVIDER_REQUIRED,
                "error": f"{self.tool_id} needs an authenticated GitHub backend"}


def github_records() -> list[ToolRecord]:
    out = []
    for tid in ("github.repo", "github.clone", "github.issue",
                "github.pull_request", "github.release", "github.actions",
                "github.search", "github.upload", "github.download"):
        out.append(_rec(tid, "github", tid.split(".")[1], tid + " (interface)",
                        "none", EXTERNAL_ACCOUNT, status=PROVIDER_REQUIRED,
                        available=False, installed=False,
                        provider="github (unconfigured)",
                        tags=("github", "remote"),
                        inschema={"type": "object"},
                        needs_install="authenticated GitHub backend"))
    return out


class HttpAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def ex(self):
        return self.ctx["executor"]

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "stdlib urllib backend present"}

    def validate(self, arguments):
        if not isinstance(arguments, dict) or \
                not str(arguments.get("url", "")).strip():
            return False, "http tools need a non-empty 'url'"
        return True, ""

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("fetch", "search", "monitor"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"http.{sub} needs a configured provider "
                             "(external search/monitor unavailable)"}
        opmap = {"get": "get", "download": "download", "head": "get",
                 "post": "get", "put": "get", "patch": "get", "delete": "get",
                 "upload": "download"}
        op = opmap.get(sub, "get")
        if sub in ("post", "put", "patch", "delete", "upload", "head"):
            return {"ok": False,
                    "error": f"http.{sub} not implemented; only get/download "
                             "have verified backends"}
        action = {"action": "net", "op": op, "url": arguments["url"]}
        if "dest" in arguments:
            action["dest"] = arguments["dest"]
        res = self.ex.dispatch(action)
        ok, why = self.verify(res)
        res["verified"] = ok
        return res


def http_records() -> list[ToolRecord]:
    out = []
    for tid, real in (("http.get", True), ("http.download", True),
                      ("http.head", False), ("http.post", False),
                      ("http.put", False), ("http.patch", False),
                      ("http.delete", False), ("http.upload", False),
                      ("web.fetch", False), ("web.search", False),
                      ("web.monitor", False)):
        if real:
            out.append(_rec(tid, "http", tid.split(".")[1], tid, "net",
                            NETWORK, tags=("http", "network"),
                            inschema={"type": "object",
                                      "properties": {"url": {"type": "string"},
                                                     "dest": {"type": "string"}}}))
        else:
            out.append(_rec(tid, "http", tid.split(".")[1],
                            tid + " (interface)", "none", NETWORK,
                            status=PROVIDER_REQUIRED, available=False,
                            installed=False, provider="external http provider",
                            tags=("http",),
                            inschema={"type": "object"},
                            needs_install="verified HTTP provider"))
    return out


class BrowserAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def ex(self):
        return self.ctx["executor"]

    def probe(self):
        try:
            import browser_cdp
            exe = browser_cdp.find_browser()
            return {"available": True, "status": AVAILABLE,
                    "reason": f"browser present: {exe}"}
        except Exception as e:  # noqa: BLE001
            return {"available": False, "status": NOT_INSTALLED,
                    "reason": str(e)[:200]}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        opmap = {"launch": None, "close": "close", "navigate": "open",
                 "back": "back", "forward": "forward", "reload": "reload",
                 "click": "click", "type": "type", "keyboard": "keyboard",
                 "select": "select", "scroll": "scroll", "wait": "wait",
                 "extract_text": "text", "extract_links": "links",
                 "title": "title", "url": "url", "screenshot": "screenshot",
                 "cookies": "cookies", "download": "download_page",
                 "upload": "upload", "pagination": "paginate",
                 "infinite_scroll": "infinite", "load_more": "paginate",
                 "checkpoint": "status", "resume": "status", "tabs": "tabs"}
        if sub == "launch":
            import browser_cdp
            try:
                sess = browser_cdp.BrowserSession()
                res = sess.launch()
                browser_cdp._OWNED[f"tool-{id(self)}"] = sess
                return {"ok": True, "pid": res.get("pid"),
                        "session": f"tool-{id(self)}", "verified": True}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "error": f"browser launch failed: {e}"}
        op = opmap.get(sub)
        if op is None:
            return {"ok": False, "error": f"unknown browser subtool: {sub!r}"}
        action = {"action": "browser", "op": op}
        for f in ("url", "selector", "text", "value", "key", "path", "dest",
                  "pattern", "max_pages", "max_rounds", "timeout_s", "dy",
                  "max_items"):
            if f in arguments:
                action[f] = arguments[f]
        res = self.ex.dispatch(action)
        ok, why = self.verify(res)
        res["verified"] = ok
        return res


def browser_records() -> list[ToolRecord]:
    out = []
    for tid in ("browser.launch", "browser.close", "browser.navigate",
                "browser.back", "browser.forward", "browser.reload",
                "browser.click", "browser.type", "browser.keyboard",
                "browser.select", "browser.scroll", "browser.wait",
                "browser.extract_text", "browser.extract_links",
                "browser.title", "browser.url", "browser.screenshot",
                "browser.cookies", "browser.download", "browser.upload",
                "browser.pagination", "browser.infinite_scroll",
                "browser.load_more", "browser.checkpoint", "browser.resume",
                "browser.tabs"):
        out.append(_rec(tid, "browser", tid.split(".")[1], tid, "browser_cdp",
                        NETWORK, profiles=list(OWNER_ONLY), auto=True,
                        cancel=True, tags=("browser", "web"),
                        inschema={"type": "object",
                                  "properties": {"url": {"type": "string"},
                                                 "selector": {"type": "string"},
                                                 "text": {"type": "string"}}}))
    return out


class ProcAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def ex(self):
        return self.ctx["executor"]

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "stdlib process backend present"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        if sub == "application.launch":
            return self.ex.dispatch({"action": "proc", "op": "spawn",
                                     "command": arguments.get("command", "")})
        if sub == "application.close":
            return self.ex.dispatch({"action": "proc", "op": "kill",
                                     "pid": arguments.get("pid", -1)})
        if sub == "application.status":
            return self.ex.dispatch({"action": "proc", "op": "status",
                                     "pid": arguments.get("pid", -1)})
        opmap = {"list": "list", "launch": "launch", "status": "status",
                 "wait": "wait", "kill": "kill"}
        action = {"action": "proc", "op": opmap[sub]}
        for f in ("command", "pid"):
            if f in arguments:
                action[f] = arguments[f]
        res = self.ex.dispatch(action)
        ok, why = self.verify(res)
        res["verified"] = ok
        return res


def proc_records() -> list[ToolRecord]:
    out = []
    for tid, risk in (("process.list", READ_ONLY), ("process.launch", MUTATING_LOCAL),
                      ("process.status", READ_ONLY), ("process.wait", SAFE_LOCAL),
                      ("process.kill", MUTATING_LOCAL),
                      ("application.launch", MUTATING_LOCAL),
                      ("application.close", MUTATING_LOCAL),
                      ("application.status", READ_ONLY)):
        out.append(_rec(tid, tid.split(".")[0], tid.split(".")[1], tid,
                        "proc", risk, profiles=list(OWNER_ONLY), auto=True,
                        cancel=True, tags=("process",),
                        inschema={"type": "object",
                                  "properties": {"command": {"type": "string"},
                                                 "pid": {"type": "integer"}}}))
    return out


class PackageAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    def probe(self):
        import installs
        ms = installs.probe()["managers"]
        present = [k for k, v in ms.items() if v.get("present")]
        return {"available": bool(present), "status": AVAILABLE if present
                else NOT_INSTALLED, "reason": f"managers: {present}"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        import installs
        sub = self.tool_id.split(".", 1)[1]
        if sub == "list":
            return {"ok": True, "managers": installs.probe()["managers"]}
        if sub == "search":
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": "package.search needs a registry provider"}
        mgr = str(arguments.get("manager", "") or "").lower()
        name = str(arguments.get("package", "") or "")
        if sub in ("install", "update", "remove") and (not mgr or not name):
            return {"ok": False,
                    "error": "package install/update/remove need manager+package"}
        table = {
            ("pip", "install"): "install", ("pip", "update"): "install --upgrade",
            ("pip", "remove"): "uninstall -y",
            ("npm", "install"): "install", ("npm", "update"): "update",
            ("npm", "remove"): "uninstall",
            ("winget", "install"): "install", ("winget", "update"): "upgrade",
            ("winget", "remove"): "uninstall",
            ("choco", "install"): "install", ("choco", "update"): "upgrade",
            ("choco", "remove"): "uninstall",
        }
        verb = table.get((mgr, sub))
        if not verb:
            return {"ok": False,
                    "error": f"unsupported manager/action: {mgr}/{sub}"}
        return installs.run_install(f"{mgr} {verb} {name}")


def package_records() -> list[ToolRecord]:
    out = []
    for tid in ("package.list", "package.search", "package.install",
                "package.update", "package.remove"):
        risk = READ_ONLY if tid in ("package.list", "package.search") else INSTALL
        out.append(_rec(tid, "package", tid.split(".")[1], tid, "installs",
                        risk, tags=("package",),
                        inschema={"type": "object",
                                  "properties": {"manager": {"type": "string"},
                                                 "package": {"type": "string"}}}))
    return out


class SystemAdapter(ToolAdapter):
    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "sysinfo backend present"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        import sysinfo
        sub = self.tool_id.split(".", 1)[1]
        if sub in ("info", "os", "cpu", "gpu", "ram", "drives", "resources"):
            inv = sysinfo.inventory()
            if sub == "info":
                return {"ok": True, **inv}
            key = {"os": "windows", "cpu": "cpu", "gpu": "gpu",
                   "ram": "ram_mb", "drives": "drives",
                   "resources": "ram_mb"}[sub]
            return {"ok": True, key: inv.get(key)}
        if sub == "admin":
            from owner import admin_state
            return {"ok": True, "admin": admin_state()}
        if sub == "time":
            import datetime
            return {"ok": True, "now": datetime.datetime.now().isoformat()}
        if sub == "temp":
            import tempfile
            return {"ok": True, "tempdir": tempfile.gettempdir()}
        if sub == "env":
            import os
            names = sorted(k for k in os.environ
                           if "key" not in k.lower()
                           and "secret" not in k.lower()
                           and "token" not in k.lower()
                           and "password" not in k.lower())
            return {"ok": True, "names": names[:200],
                    "note": "names only; values never exposed broadly"}
        return {"ok": False, "error": f"unknown system subtool: {sub!r}"}


def system_records() -> list[ToolRecord]:
    out = []
    for tid in ("system.info", "system.os", "system.cpu", "system.gpu",
                "system.ram", "system.drives", "system.env", "system.admin",
                "system.time", "system.temp", "system.resources"):
        out.append(_rec(tid, "system", tid.split(".")[1], tid, "sysinfo",
                        READ_ONLY, tags=("system",),
                        inschema={"type": "object"}))
    return out
