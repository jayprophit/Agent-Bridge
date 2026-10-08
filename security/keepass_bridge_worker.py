"""KeePass bridge worker — executed by the isolated `.venv-kdbx` interpreter.

Runs OUT OF PROCESS so the Aetherius runtime (python 3.11) never needs
`pykeepass` on its own sys.path, and so a crash inside the crypto stack
cannot take the supervisor down with it.

Protocol (§12, §23):
    stdin  : one JSON object   {"op": ..., "db_path": ..., "password": ..., ...}
    stdout : one JSON object   {"ok": true, ...} | {"ok": false, "error": ...}

SECURITY INVARIANTS
    1. The master password arrives on the stdin PIPE. It is never written
       to disk, never placed in argv (visible in `tasklist` / ps), and
       never echoed to stdout.
    2. stdout NEVER contains a secret value unless op == "read_entry",
       whose whole purpose is to return exactly one requested entry value.
    3. Every op is a single shot: the process exits after one request, so
       no unlocked handle lingers in memory.
"""

import json
import sys

REQUIRED_PY_KEEPASS = "4.2.0"


def _fail(message: str, code: str = "ERROR") -> dict:
    return {"ok": False, "error": message, "error_code": code}


def _entry_view(entry) -> dict:
    """Metadata-only view of an entry — no secret fields (§16).

    `entry.group` is a Group OBJECT, not a string; calling str() on it can
    trigger lazy XML traversal and can blow up JSON serialisation. Every
    field here is coerced to a plain JSON-safe scalar.
    """
    def _s(value) -> str:
        try:
            return str(value) if value is not None else ""
        except Exception:
            return ""

    path_parts = []
    try:
        path_parts = [p.name for p in entry.path]
    except Exception:
        path_parts = []

    return {
        "title": _s(entry.title),
        "username": _s(entry.username),
        "url": _s(entry.url),
        "notes": _s(entry.notes),
        "group": path_parts[-1] if path_parts else "",
        "group_path": "/".join(path_parts),
        "uuid": entry.uuid.hex if getattr(entry, "uuid", None) else "",
        "otp": bool(entry.otp),
    }


def _load(pykeepass_module):
    """Open the database with the supplied password (raises on failure)."""
    return pykeepass_module


def handle(request: dict) -> dict:
    """Dispatch a single bridge request. Returns a JSON-serialisable dict."""
    op = request.get("op", "")
    db_path = request.get("db_path", "")
    password = request.get("password", "")

    if not op:
        return _fail("missing op", "BAD_REQUEST")
    if not db_path:
        return _fail("missing db_path", "BAD_REQUEST")

    try:
        import os

        if not os.path.isfile(db_path):
            return _fail(f"database not found: {db_path}", "DB_NOT_FOUND")

        try:
            import pykeepass
            from pykeepass.exceptions import (
                CredentialsError,
                HeaderChecksumError,
                PayloadChecksumError,
            )
        except ImportError as exc:
            return _fail(f"pykeepass unavailable: {exc}", "NO_PYKEEPASS")

        # ---- ops that need NO master password ----

        if op == "header":
            # Container integrity only: signature + format version.
            import struct

            with open(db_path, "rb") as fh:
                head = fh.read(12)
            if len(head) < 12:
                return _fail("file too small to be a KDBX container", "BAD_CONTAINER")
            sig1, sig2 = head[0:4], head[4:8]
            minor, major = struct.unpack("<HH", head[8:12])
            valid = sig1 == b"\x03\xd9\xa2\x9a" and sig2 == b"\x67\xfb\x4b\xb5"
            if not valid:
                return _fail("not a KDBX container (bad signature)", "BAD_CONTAINER")
            if major not in (3, 4):
                return _fail(f"unsupported KDBX major version {major}", "BAD_CONTAINER")
            return {
                "ok": True,
                "signature_valid": True,
                "major_version": major,
                "minor_version": minor,
                "size_bytes": os.path.getsize(db_path),
                "pykeepass_version": getattr(pykeepass, "__version__", REQUIRED_PY_KEEPASS),
            }

        # ---- every remaining op requires the master password ----

        if not password:
            return _fail("master password required", "AUTH_REQUIRED")

        try:
            kp = pykeepass.PyKeePass(db_path, password=password)
        except CredentialsError:
            return _fail("invalid master password or key file", "AUTH_FAILED")
        except HeaderChecksumError:
            return _fail("header checksum mismatch — corrupt or tampered database",
                         "INTEGRITY_FAILED")
        except PayloadChecksumError:
            return _fail("payload checksum mismatch — corrupt database",
                         "INTEGRITY_FAILED")
        except Exception as exc:  # malformed file, unsupported KDF, ...
            return _fail(f"{type(exc).__name__}: {exc}", "OPEN_FAILED")

        if op == "verify":
            return {
                "ok": True,
                "unlocked": True,
                "entry_count": len(kp.entries),
                "group_count": len(kp.groups),
                "root_group": kp.root_group.name if kp.root_group else "",
                "recycle_bin_configured": kp.recyclebin_group is not None,
            }

        if op == "list_metadata":
            return {"ok": True, "entries": [_entry_view(e) for e in kp.entries]}

        if op == "read_entry":
            title = request.get("title", "")
            matches = kp.find_entries(title=title, first=True) if title else None
            if matches is None:
                return _fail(f"entry not found: {title}", "NOT_FOUND")
            return {
                "ok": True,
                "found": True,
                "title": matches.title,
                "username": matches.username or "",
                "password": matches.password or "",
                "url": matches.url or "",
                "notes": matches.notes or "",
                "otp": matches.otp or "",
            }

        if op == "create_entry":
            title = request.get("title", "")
            secret = request.get("secret", "")
            if not title:
                return _fail("missing title", "BAD_REQUEST")
            group_name = request.get("group", "") or None
            group = kp.find_groups(name=group_name, first=True) if group_name else None
            if group is None:
                group = kp.root_group
            # UPSERT: KeePass rejects a duplicate entry title inside the same
            # group, and Aetherius addresses credentials by a stable reference
            # (§7). Creating must therefore update when the reference already
            # exists, otherwise a re-store or rotation raises on the real vault.
            existing = kp.find_entries(title=title, first=True)
            if existing is not None:
                existing.password = secret
                if request.get("username"):
                    existing.username = request["username"]
                if request.get("url"):
                    existing.url = request["url"]
                if request.get("notes"):
                    existing.notes = request["notes"]
                kp.save()
                return {"ok": True, "created": True, "updated": True,
                        "title": title}
            kp.add_entry(
                destination_group=group,
                title=title,
                username=request.get("username", ""),
                password=secret,
                url=request.get("url", ""),
                notes=request.get("notes", ""),
            )
            kp.save()
            return {"ok": True, "created": True, "updated": False,
                    "title": title}

        if op == "update_entry":
            title = request.get("title", "")
            entry = kp.find_entries(title=title, first=True) if title else None
            if entry is None:
                return _fail(f"entry not found: {title}", "NOT_FOUND")
            new_secret = request.get("secret")
            if new_secret is not None:
                entry.password = new_secret
            if "username" in request:
                entry.username = request["username"]
            if "notes" in request:
                entry.notes = request["notes"]
            if "url" in request:
                entry.url = request["url"]
            kp.save()
            return {"ok": True, "updated": True, "title": title}

        return _fail(f"unsupported op: {op}", "BAD_REQUEST")

    except SystemExit:
        raise
    except Exception as exc:  # never leak a stack trace containing secrets
        return _fail(f"{type(exc).__name__}: {exc}", "INTERNAL")


def main() -> int:
    raw = sys.stdin.read()
    if not raw.strip():
        print(json.dumps(_fail("empty stdin", "BAD_REQUEST")))
        return 2
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps(_fail(f"invalid JSON: {exc}", "BAD_REQUEST")))
        return 2

    result = handle(request)
    sys.stdout.write(json.dumps(result))
    sys.stdout.flush()
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
