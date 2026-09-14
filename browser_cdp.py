"""Real browser automation over Chrome DevTools Protocol (v0.6, stdlib only).

No playwright/selenium dependency: a minimal RFC6455 WebSocket client
drives headless Chrome/Edge found on this machine. Every action returns
real evidence (no fake browser abstraction).

Vision: DOM-first extraction. Screenshots are captured for future
vision-capable models; a clean VisionProvider interface exists, and the
default provider honestly reports unavailability (we never pretend the
current Qwen coder can see images).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import select
import shutil
import socket
import ssl
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]


class BrowserError(Exception):
    pass


def find_browser() -> str:
    for cand in _BROWSERS:
        if Path(cand).exists():
            return cand
    for name in ("msedge", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise BrowserError("no supported browser found on this machine")


# -- minimal websocket client -------------------------------------------------
class _WS:
    def __init__(self, url: str, timeout: float = 30.0):
        from urllib.parse import urlparse
        u = urlparse(url)
        host, port = u.hostname or "127.0.0.1", u.port or 80
        use_ssl = u.scheme == "wss"
        raw = socket.create_connection((host, port), timeout=timeout)
        self.sock = ssl.wrap_socket(raw) if use_ssl else raw
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET {u.path or '/'} HTTP/1.1\r\nHost: {host}:{port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise BrowserError("websocket handshake failed")
            head += chunk
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise BrowserError(f"websocket upgrade refused: {head[:120]!r}")
        self._buf = b""
        self._lock = threading.Lock()

    def send_text(self, text: str) -> None:
        data = text.encode("utf-8")
        mask = os.urandom(4)
        hdr = bytes([0x81])
        n = len(data)
        if n < 126:
            hdr += bytes([0x80 | n])
        elif n < 65536:
            hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        with self._lock:
            self.sock.sendall(hdr + mask + masked)

    def _fill(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise BrowserError("websocket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv_text(self, timeout: float = 60.0) -> str:
        self.sock.settimeout(timeout)
        parts: list[bytes] = []
        while True:
            b1, b2 = self._fill(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            masked, ln = (b2 & 0x80) != 0, b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._fill(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._fill(8))[0]
            if masked:
                mask = self._fill(4)
            payload = self._fill(ln)
            if masked:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if opcode == 0x8:
                raise BrowserError("websocket closed by peer")
            if opcode == 0x9:  # ping -> pong
                with self._lock:
                    self.sock.sendall(b"\x8a\x00")
                continue
            if opcode in (0x1, 0x0):
                parts.append(payload)
            if fin:
                break
        return b"".join(parts).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            with self._lock:
                self.sock.sendall(b"\x88\x00")
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


_sessions: list["BrowserSession"] = []
_sessions_lock = threading.Lock()
_OWNED: dict[str, "BrowserSession"] = {}


def stop_all(reason: str = "") -> None:
    with _sessions_lock:
        live = list(_sessions)
    for s in live:
        try:
            s.stop()
        except Exception:
            pass
    _OWNED.clear()


class BrowserSession:
    """One headed/headless browser + one page, driven over CDP."""

    def __init__(self, headless: bool = True, width: int = 1280,
                 height: int = 900,
                 extra_chrome_args: list[str] | None = None):
        self.exe = find_browser()
        self.headless = headless
        self.width, self.height = width, height
        # Optional extra Chromium flags (e.g. test-only --disable-web-security
        # for loopback cross-origin checks). Empty by default: no behavior change.
        self.extra_chrome_args = list(extra_chrome_args or [])
        self.profile = Path(tempfile.mkdtemp(prefix="v06_prof_"))
        self.downloads = Path(tempfile.mkdtemp(prefix="v06_dl_"))
        self.proc: subprocess.Popen | None = None
        self.ws: _WS | None = None
        self.target_id = ""
        self._id = 0
        self._id_lock = threading.Lock()
        self._cancel = {"flag": False}

    # -- lifecycle ------------------------------------------------------------
    def _free_port(self) -> int:
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def launch(self, timeout_s: int = 60) -> dict[str, Any]:
        self.port = self._free_port()
        args = [self.exe, f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.profile}",
                f"--window-size={self.width},{self.height}",
                *self.extra_chrome_args,
                "--no-first-run", "--no-default-browser-check",
                "--disable-gpu", "--disable-dev-shm-usage",
                "--disable-features=Translate", "about:blank"]
        if self.headless:
            args.append("--headless=new")
        try:
            self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL)
        except OSError as e:
            raise BrowserError(f"browser launch failed: {e}")
        url = ""
        end = time.time() + timeout_s
        import urllib.request
        while time.time() < end:
            if self.proc.poll() is not None:
                raise BrowserError("browser exited during launch")
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/json/list",
                        timeout=3) as r:
                    targets = json.loads(r.read().decode())
                pages = [t for t in targets if t.get("type") == "page"]
                if pages:
                    url = pages[0]["webSocketDebuggerUrl"]
                    self.target_id = pages[0]["id"]
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        if not url:
            self.stop()
            raise BrowserError("CDP endpoint never appeared")
        self.ws = _WS(url)
        self._cmd("Page.enable")
        self._cmd("Runtime.enable")
        self._cmd("Browser.setDownloadBehavior",
                  {"behavior": "allow", "downloadPath": str(self.downloads)})
        with _sessions_lock:
            _sessions.append(self)
        return {"ok": True, "pid": self.proc.pid if self.proc else None,
                "exe": self.exe, "headless": self.headless}

    def stop(self) -> dict[str, Any]:
        with _sessions_lock:
            if self in _sessions:
                _sessions.remove(self)
        try:
            if self.ws:
                try:
                    self._cmd("Browser.close", timeout=5)
                except Exception:  # noqa: BLE001
                    pass
                self.ws.close()
        finally:
            self.ws = None
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                try:
                    self.proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        import shutil as _sh
        _sh.rmtree(self.profile, ignore_errors=True)
        return {"ok": True, "stopped": True}

    def cancel(self) -> None:
        self._cancel["flag"] = True

    # -- CDP plumbing -----------------------------------------------------------
    def _cmd(self, method: str, params: dict | None = None,
             timeout: float = 45.0) -> dict[str, Any]:
        if not self.ws:
            raise BrowserError("no page connection")
        with self._id_lock:
            self._id += 1
            mid = self._id
        self.ws.send_text(json.dumps({"id": mid, "method": method,
                                      "params": params or {}}))
        end = time.time() + timeout
        while time.time() < end:
            if self._cancel.get("flag"):
                raise BrowserError("cancelled")
            try:
                msg = json.loads(self.ws.recv_text(timeout=max(1.0, end - time.time())))
            except BrowserError:
                raise
            except Exception as e:  # noqa: BLE001
                raise BrowserError(f"CDP read failed: {e}")
            if msg.get("id") == mid:
                if "error" in msg:
                    raise BrowserError(f"CDP {method}: {msg['error'].get('message', msg['error'])}")
                return msg.get("result", {})
        raise BrowserError(f"CDP {method}: timeout")

    def _eval(self, js: str, timeout: float = 30.0) -> Any:
        res = self._cmd("Runtime.evaluate",
                        {"expression": js, "returnByValue": True,
                         "awaitPromise": True}, timeout)
        if res.get("exceptionDetails"):
            raise BrowserError(f"page JS failed: {res['exceptionDetails'].get('text', '')[:300]}")
        return (res.get("result") or {}).get("value")

    # -- navigation / tabs --------------------------------------------------------
    def open_url(self, url: str, timeout_s: int = 60) -> dict[str, Any]:
        t0 = time.monotonic()
        self._cmd("Page.navigate", {"url": url}, timeout_s)
        end = time.time() + timeout_s
        while time.time() < end:
            state = self._eval(
                "document.readyState", timeout=10)
            if state in ("interactive", "complete"):
                break
            time.sleep(0.5)
        return {"ok": True, "url": self.current_url(),
                "title": self.title(),
                "duration_s": round(time.monotonic() - t0, 3)}

    def new_tab(self, url: str = "about:blank") -> dict[str, Any]:
        import urllib.request
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/json/new?{url}",
            method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                info = json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            raise BrowserError(f"new tab failed: {e}")
        return {"ok": True, "target_id": info.get("id", "")}

    def back(self) -> dict[str, Any]:
        hist = self._cmd("Page.getNavigationHistory")
        idx, entries = hist.get("currentIndex", 0), hist.get("entries", [])
        if idx <= 0:
            return {"ok": False, "error": "no back history"}
        self._cmd("Page.navigateToHistoryEntry", {"entryId": entries[idx - 1]["id"]})
        return {"ok": True, "url": self.current_url()}

    def forward(self) -> dict[str, Any]:
        hist = self._cmd("Page.getNavigationHistory")
        idx, entries = hist.get("currentIndex", 0), hist.get("entries", [])
        if idx + 1 >= len(entries):
            return {"ok": False, "error": "no forward history"}
        self._cmd("Page.navigateToHistoryEntry", {"entryId": entries[idx + 1]["id"]})
        return {"ok": True, "url": self.current_url()}

    def reload(self) -> dict[str, Any]:
        self._cmd("Page.reload")
        time.sleep(1.5)
        return {"ok": True, "url": self.current_url(), "title": self.title()}

    # -- interaction -----------------------------------------------------------------
    def _node_id(self, selector: str) -> int:
        doc = self._cmd("DOM.getDocument", {"depth": 0})
        res = self._cmd("DOM.querySelector",
                        {"nodeId": doc["root"]["nodeId"], "selector": selector})
        nid = res.get("nodeId", 0)
        if not nid:
            raise BrowserError(f"no such element: {selector!r}")
        return nid

    def click(self, selector: str) -> dict[str, Any]:
        # prefer real input events; fall back to DOM click
        try:
            nid = self._node_id(selector)
            box = self._cmd("DOM.getBoxModel", {"nodeId": nid}).get("model", {})
            quad = box.get("content", [0, 0, 0, 0, 0, 0, 0, 0])
            x = sum(quad[0::2]) / 4
            y = sum(quad[1::2]) / 4
            for kind in ("mousePressed", "mouseReleased"):
                self._cmd("Input.dispatchMouseEvent",
                          {"type": kind, "x": x, "y": y, "button": "left",
                           "clickCount": 1})
            time.sleep(0.8)
            return {"ok": True, "selector": selector, "x": x, "y": y}
        except BrowserError:
            clicked = self._eval(
                f"(()=>{{const el=document.querySelector({json.dumps(selector)});"
                f"if(!el) return false; el.click(); return true;}})()")
            if not clicked:
                raise BrowserError(f"no such element: {selector!r}")
            time.sleep(0.8)
            return {"ok": True, "selector": selector, "via": "dom-click"}

    def type_text(self, selector: str, text: str) -> dict[str, Any]:
        nid = self._node_id(selector)
        self._cmd("DOM.focus", {"nodeId": nid})
        for ch in text:
            self._cmd("Input.insertText", {"text": ch})
        return {"ok": True, "selector": selector, "chars": len(text)}

    def keyboard(self, key: str) -> dict[str, Any]:
        self._cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": key})
        self._cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
        return {"ok": True, "key": key}

    def select_option(self, selector: str, value: str) -> dict[str, Any]:
        ok = self._eval(
            f"(()=>{{const el=document.querySelector({json.dumps(selector)});"
            f"if(!el) return false; el.value={json.dumps(value)};"
            f"el.dispatchEvent(new Event('change',{{bubbles:true}})); return true;}})()")
        if not ok:
            raise BrowserError(f"no such select: {selector!r}")
        return {"ok": True, "selector": selector, "value": value}

    def scroll(self, dy: int = 800) -> dict[str, Any]:
        height = self._eval(
            "(document.scrollingElement||document.body).scrollHeight")
        self._eval(f"window.scrollBy(0,{int(dy)})")
        time.sleep(0.6)
        return {"ok": True, "scrolled_by": dy, "page_height": height,
                "y": self._eval("window.scrollY")}

    def wait_for(self, selector: str, timeout_s: int = 20) -> dict[str, Any]:
        end = time.time() + timeout_s
        while time.time() < end:
            found = self._eval(
                f"!!document.querySelector({json.dumps(selector)})")
            if found:
                return {"ok": True, "selector": selector}
            time.sleep(0.5)
        return {"ok": False, "error": f"wait timed out: {selector!r}"}

    def wait_network_idle(self, timeout_s: int = 20) -> dict[str, Any]:
        # DOM-quiescence heuristic: readyState complete + stable body size
        end = time.time() + timeout_s
        last = -1
        stable = 0
        while time.time() < end:
            size = self._eval("document.documentElement.outerHTML.length")
            if size == last:
                stable += 1
                if stable >= 3:
                    return {"ok": True}
            else:
                stable = 0
            last = size
            time.sleep(1.0)
        return {"ok": False, "error": "network/DOM never settled"}

    # -- extraction ----------------------------------------------------------------------
    def title(self) -> str:
        return str(self._eval("document.title") or "")

    def current_url(self) -> str:
        return str(self._eval("location.href") or "")

    def dom_text(self, selector: str = "body", max_chars: int = 20000) -> dict[str, Any]:
        text = self._eval(
            f"(()=>{{const el=document.querySelector({json.dumps(selector)});"
            f"return el ? el.innerText : '';}})()")
        return {"ok": True, "selector": selector,
                "text": str(text or "")[:max_chars]}

    def links(self, max_items: int = 200) -> dict[str, Any]:
        items = self._eval(
            f"Array.from(document.links).slice(0,{int(max_items)}).map(a=>"
            f"({{text:(a.innerText||'').trim().slice(0,120),href:a.href}}))")
        return {"ok": True, "links": items or []}

    def screenshot(self, dest: str | Path) -> dict[str, Any]:
        data = self._cmd("Page.captureScreenshot", {"format": "png"})
        raw = base64.b64decode(data.get("data", ""))
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        if not dest.exists():
            return {"ok": False, "error": "screenshot claimed but file missing"}
        return {"ok": True, "path": str(dest), "bytes": dest.stat().st_size}

    def cookies(self) -> dict[str, Any]:
        try:
            res = self._cmd("Storage.getCookies")
            names = [c.get("name", "") for c in res.get("cookies", [])]
        except BrowserError:
            names = []
        return {"ok": True, "cookie_names": names,
                "note": "values never leave the browser profile"}

    def upload(self, selector: str, file_path: str) -> dict[str, Any]:
        nid = self._node_id(selector)
        self._cmd("DOM.setFileInputFiles",
                  {"nodeId": nid, "files": [str(file_path)]})
        return {"ok": True, "selector": selector, "file": str(file_path)}

    # -- pagination primitives ----------------------------------------------------------------
    def paginate(self, next_selector: str = 'a[rel="next"]',
                 max_pages: int = 20,
                 item_selector: str = "",
                 seen: set[str] | None = None) -> dict[str, Any]:
        """NEXT/load-more pagination with checkpoint/resume shape."""
        seen = seen if seen is not None else set()
        pages, items_total, notes = 0, 0, []
        while pages < max_pages:
            if self._cancel.get("flag"):
                notes.append("cancelled")
                break
            pages += 1
            if item_selector:
                items = self._eval(
                    f"Array.from(document.querySelectorAll("
                    f"{json.dumps(item_selector)})).map(e=>e.innerText.trim())")
                fresh = [t for t in (items or []) if t and t not in seen]
                seen.update(fresh)
                items_total += len(fresh)
                notes.append(f"page {pages}: {len(fresh)} new item(s)")
            else:
                notes.append(f"page {pages} captured")
            nxt = self._eval(
                f"(()=>{{const el=document.querySelector({json.dumps(next_selector)});"
                f"if(!el) return null;"
                f"return {{text:(el.innerText||'').trim(), disabled:el.disabled||"
                f"el.getAttribute('aria-disabled')==='true'}};}})()")
            if not nxt or nxt.get("disabled"):
                notes.append("no further pages")
                break
            self.click(next_selector)
            self.wait_network_idle(10)
        return {"ok": True, "pages": pages, "items": items_total,
                "notes": notes, "checkpoint": {"pages_done": pages}}

    def infinite_scroll(self, max_rounds: int = 15,
                        item_selector: str = "",
                        seen: set[str] | None = None) -> dict[str, Any]:
        seen = seen if seen is not None else set()
        rounds, total = 0, 0
        while rounds < max_rounds:
            if self._cancel.get("flag"):
                break
            before = self._eval(
                "(document.scrollingElement||document.body).scrollHeight")
            self._eval("window.scrollTo(0,document.body.scrollHeight)")
            time.sleep(1.5)
            after = self._eval(
                "(document.scrollingElement||document.body).scrollHeight")
            rounds += 1
            if item_selector:
                items = self._eval(
                    f"Array.from(document.querySelectorAll("
                    f"{json.dumps(item_selector)})).map(e=>e.innerText.trim())")
                fresh = [t for t in (items or []) if t and t not in seen]
                seen.update(fresh)
                total += len(fresh)
                if not fresh and after == before:
                    break
            elif after == before:
                break
        return {"ok": True, "rounds": rounds, "items": total,
                "checkpoint": {"rounds_done": rounds}}


class VisionProvider:
    kind = "base"

    def describe(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        raise NotImplementedError


class UnavailableVision(VisionProvider):
    """Honest default: no vision-capable model is configured, so image
    understanding is reported unavailable instead of hallucinated."""
    kind = "unavailable"

    def describe(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        return {"ok": False, "available": False,
                "error": "no vision-capable model configured; "
                         "DOM extraction must be used instead"}


def vision_provider(kind: str = "unavailable", **kw: Any) -> VisionProvider:
    if kind == "unavailable":
        return UnavailableVision()
    raise BrowserError(f"unknown vision provider {kind!r}")
