"""Outbound HTTP/HTTPS for OWNER_FULL_ACCESS (EXTERNAL_NETWORK).

Timeouts, download caps, real status reporting, cancellation support,
logging, safe filenames. Never sends runtime secrets. Safe profiles keep
their own restrictions (this module is only invoked from owner paths).
"""
from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT_S = 30
DEFAULT_MAX_BYTES = 50_000_000


class NetError(Exception):
    pass


def _clean_headers(extra: dict[str, str] | None) -> dict[str, str]:
    banned = ("authorization", "cookie", "proxy-authorization", "x-api-key")
    out = {}
    for k, v in (extra or {}).items():
        if k.lower() in banned:
            raise NetError(f"refused header {k!r}: secrets never leave the runtime")
        out[k] = v
    return out


def http_get(url: str, timeout_s: int = DEFAULT_TIMEOUT_S,
             max_bytes: int = DEFAULT_MAX_BYTES,
             headers: dict[str, str] | None = None,
             cancel: dict | None = None) -> dict[str, Any]:
    parts = urllib.parse.urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise NetError(f"refused non-HTTP(S) URL: {url!r}")
    req = urllib.request.Request(url, headers={
        "User-Agent": "AgentRuntime/0.6 (owner-mode)", **_clean_headers(headers)})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = resp.status
            ctype = resp.headers.get("Content-Type", "")
            chunks: list[bytes] = []
            remaining = max_bytes
            while remaining > 0:
                if cancel is not None and cancel.get("flag"):
                    raise NetError("cancelled")
                buf = resp.read(min(65536, remaining))
                if not buf:
                    break
                chunks.append(buf)
                remaining -= len(buf)
            body = b"".join(chunks)
            truncated = remaining <= 0
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "url": url,
                "error": f"HTTP {e.code}", "duration_s": round(time.monotonic() - t0, 3)}
    except urllib.error.URLError as e:
        raise NetError(f"network error: {e.reason}")
    except TimeoutError:
        raise NetError("timeout")
    return {"ok": 200 <= status < 300, "status": status, "url": url,
            "content_type": ctype, "bytes": len(body),
            "text": body.decode("utf-8", "replace")[:20000],
            "_raw": body,
            "truncated": truncated,
            "duration_s": round(time.monotonic() - t0, 3)}


def safe_filename(url: str, content_type: str = "") -> str:
    name = Path(urllib.parse.urlparse(url).path).name or "download"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "download"
    return name


def download(url: str, dest_dir: Path, timeout_s: int = DEFAULT_TIMEOUT_S,
             max_bytes: int = DEFAULT_MAX_BYTES,
             cancel: dict | None = None) -> dict[str, Any]:
    res = http_get(url, timeout_s, max_bytes, cancel=cancel)
    if not res.get("ok") and "status" in res and res.get("status", 0) >= 400:
        return {**res, "destination": ""}
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_filename(url, res.get("content_type", ""))
    # body text was decoded; re-fetch raw? keep simple: store decoded text
    # for text types, else report without storing binary precisely.
    try:
        dest.write_bytes(res.get("_raw", b"") or b"")
    except OSError as e:
        raise NetError(f"cannot write download: {e}")
    if not dest.exists():
        return {"ok": False, "error": "download claimed but file missing"}
    return {"ok": True, "source_url": url, "destination": str(dest),
            "size": dest.stat().st_size, "status": res.get("status", 0),
            "content_type": res.get("content_type", "")}
