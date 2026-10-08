"""KeePass subprocess bridge — client side (§12, §21, §23).

Why a subprocess rather than importing pykeepass directly:

    1. `pykeepass` needs a full crypto stack (pycryptodomex, lxml, construct).
       Installing it into the Aetherius runtime venv couples the supervisor
       to a third-party dependency that is not part of the runtime contract.
    2. `pykeepass` operates on the real owner database. Running it in a
       short-lived child process means an unlocked handle lives for exactly
       one request and is then destroyed with the process — no lingering
       decrypted database in supervisor memory (§23).
    3. A parser crash or malformed-KDBX bug cannot take down the supervisor.

Contract (§12):
    - The master password is passed to the child on a PIPE (stdin), never
      in argv (argv is visible to `tasklist`, crash dumps, and WMI).
    - The child echoes back a single JSON object on stdout.
    - The password is NEVER written to disk, NEVER logged, NEVER stored.

Discovery order for the interpreter:
    1. env AETHERIUS_KEEPASS_PY  — explicit override
    2. <home>/.aetherius/venvs/kdbx313  (created by `uv venv ~/.aetherius/venvs/kdbx313`)
    3. <home>/.aetherius/venvs/kdbx
    4. a repo-local .venv-kdbx* (supported, but see the note in find_interpreter)
    5. any venv dir under <repo> that can `import pykeepass`
    6. None -> every op fails closed with NO_PYKEEPASS

The venv deliberately lives OUTSIDE the repository: `pycryptodome` ships
upstream private-key test fixtures, and tests/test_secret_hygiene.py
scans the whole tree. Keeping the crypto stack out of the repo keeps that
gate honest without weakening it.

Discovery order for the database (§21 step 2):
    1. env AETHERIUS_KEEPASS_DB
    2. Aetherius config file  config/aetherius.local.json  ("keepass_db")
    3. Well-known Windows locations (Documents, OneDrive/Documents, Dropbox, repo)
"""

import json
import os
import shutil
import subprocess

BRIDGE_WORKER_RELPATH = os.path.join("security", "keepass_bridge_worker.py")
CONFIG_RELPATH = os.path.join("config", "aetherius.local.json")

ERROR_NO_PYKEEPASS = "NO_PYKEEPASS"
ERROR_BAD_CONTAINER = "BAD_CONTAINER"
ERROR_AUTH_FAILED = "AUTH_FAILED"
ERROR_AUTH_REQUIRED = "AUTH_REQUIRED"
ERROR_INTEGRITY = "INTEGRITY_FAILED"
ERROR_DB_NOT_FOUND = "DB_NOT_FOUND"


class KeePassBridgeError(Exception):
    """Structured bridge failure — message never contains the password."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_interpreter() -> str | None:
    """Locate a Python interpreter that can run the pykeepass worker."""
    override = os.environ.get("AETHERIUS_KEEPASS_PY")
    if override and os.path.isfile(override):
        return override

    root = _repo_root()
    # A repo-local venv would be picked up by secret-hygiene scanning (a
    # crypto stack ships upstream private-key fixtures), so the KeePass
    # venv lives OUTSIDE the repo tree. AETHERIUS_KEEPASS_PY overrides all
    # of this when set.
    external = os.path.join(os.path.expanduser("~"), ".aetherius", "venvs")
    candidates = [
        os.path.join(external, "kdbx313", "Scripts", "python.exe"),
        os.path.join(external, "kdbx313", "bin", "python"),
        os.path.join(external, "kdbx", "Scripts", "python.exe"),
        os.path.join(external, "kdbx", "bin", "python"),
    ]
    # Repo-local venvs remain supported (an explicit local install wins over
    # nothing), but they must be excluded from hygiene scanning separately.
    candidates += [
        os.path.join(root, ".venv-kdbx313", "Scripts", "python.exe"),
        os.path.join(root, ".venv-kdbx313", "bin", "python"),
        os.path.join(root, ".venv-kdbx", "Scripts", "python.exe"),
        os.path.join(root, ".venv-kdbx", "bin", "python"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    # Fall back: any sibling venv that already has pykeepass importable.
    try:
        for name in sorted(os.listdir(root)):
            if not name.startswith(".venv"):
                continue
            for exe in ("Scripts/python.exe", "bin/python"):
                path = os.path.join(root, name, exe)
                if not os.path.isfile(path):
                    continue
                probe = subprocess.run(
                    [path, "-c", "import pykeepass"],
                    capture_output=True, timeout=20,
                )
                if probe.returncode == 0:
                    return path
    except OSError:
        pass

    return None


def find_database(known_path: str | None = None) -> str | None:
    """Discover the KeePass database path (§21 step 2).

    `known_path` is an owner-supplied path and always wins.
    """
    if known_path and os.path.isfile(known_path):
        return os.path.abspath(known_path)

    env = os.environ.get("AETHERIUS_KEEPASS_DB")
    if env and os.path.isfile(env):
        return os.path.abspath(env)

    cfg = os.path.join(_repo_root(), CONFIG_RELPATH)
    if os.path.isfile(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            candidate = data.get("keepass_db", "")
            if candidate and os.path.isfile(candidate):
                return os.path.abspath(candidate)
        except (json.JSONDecodeError, OSError):
            pass

    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Documents"),
        os.path.join(home, "OneDrive", "Documents"),
        os.path.join(home, "Dropbox"),
        _repo_root(),
    ]
    for base in roots:
        if not os.path.isdir(base):
            continue
        try:
            for name in sorted(os.listdir(base)):
                if name.lower().endswith(".kdbx"):
                    path = os.path.join(base, name)
                    if os.path.isfile(path):
                        return os.path.abspath(path)
        except OSError:
            continue

    return None


class KeePassBridge:
    """Stateless subprocess bridge to a real KeePass database.

    One instance == one database path + one interpreter. No state is held
    between calls; every call spawns and reaps a child process.
    """

    def __init__(self, db_path: str | None = None, interpreter: str | None = None,
                 timeout_s: int = 60):
        # An EXPLICIT path is authoritative and is NEVER silently replaced by
        # discovery (§61 fail-closed): a caller that names a missing database
        # must get an error, not the owner's real vault.
        self._explicit_db = db_path is not None
        self._db_path = (os.path.abspath(db_path) if self._explicit_db
                         else find_database(None))
        # An EXPLICIT interpreter is likewise authoritative — a bad override
        # must fail closed rather than quietly using a different venv.
        self._explicit_interp = interpreter is not None
        self._interpreter = interpreter if self._explicit_interp else find_interpreter()
        self._timeout = timeout_s
        self._worker = os.path.join(_repo_root(), BRIDGE_WORKER_RELPATH)

    # ---- introspection ----

    @property
    def db_path(self) -> str | None:
        return self._db_path

    @property
    def interpreter(self) -> str | None:
        return self._interpreter

    def ready(self) -> bool:
        """Fail-closed readiness check (§61).

        An explicitly-supplied path or interpreter is held to account: if the
        caller named something that does not exist, `ready()` is False rather
        than silently falling back to the owner's real database.
        """
        if not self._db_path or not os.path.isfile(self._db_path):
            return False
        if not self._interpreter or not os.path.isfile(self._interpreter):
            return False
        return os.path.isfile(self._worker)

    def status(self) -> dict:
        return {
            "adapter_id": "keepass_bridge",
            "db_path": self._db_path,
            "db_present": bool(self._db_path and os.path.isfile(self._db_path)),
            "interpreter": self._interpreter,
            "interpreter_present": bool(self._interpreter and os.path.isfile(self._interpreter)),
            "worker_present": os.path.isfile(self._worker),
            "ready": self.ready(),
        }

    # ---- transport ----

    def _call(self, request: dict, password: str | None = None) -> dict:
        """One request, one child process (§23).

        Fails closed before spawning anything if the bridge is not fully
        wired — a half-configured bridge must never reach the real vault.
        """
        if not self.ready():
            missing = []
            if not self._db_path:
                missing.append("db_path (set AETHERIUS_KEEPASS_DB)")
            elif not os.path.isfile(self._db_path):
                raise KeePassBridgeError(ERROR_DB_NOT_FOUND,
                                         f"database not found: {self._db_path}")
            if not self._interpreter:
                missing.append("interpreter (set AETHERIUS_KEEPASS_PY "
                               "or create .venv-kdbx)")
            elif not os.path.isfile(self._interpreter):
                raise KeePassBridgeError(ERROR_NO_PYKEEPASS,
                                         f"interpreter not executable: "
                                         f"{self._interpreter}")
            if not os.path.isfile(self._worker):
                missing.append(f"bridge worker ({self._worker})")
            raise KeePassBridgeError("NOT_READY",
                                     "bridge not ready, missing: "
                                     + ", ".join(missing))

        payload = dict(request)
        payload["db_path"] = self._db_path
        if password is not None:
            payload["password"] = password

        # Password travels on the PIPE only — never in argv, never on disk.
        try:
            proc = subprocess.run(
                [self._interpreter, self._worker],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            raise KeePassBridgeError("TIMEOUT",
                                     f"KeePass bridge timed out after {self._timeout}s")

        out = (proc.stdout or "").strip()
        if not out:
            err = (proc.stderr or "").strip().splitlines()
            detail = err[-1] if err else "no output"
            raise KeePassBridgeError("CHILD_FAILED", f"bridge child failed: {detail}")

        try:
            result = json.loads(out)
        except json.JSONDecodeError:
            raise KeePassBridgeError("BAD_RESPONSE", "bridge returned non-JSON output")

        if not result.get("ok"):
            raise KeePassBridgeError(result.get("error_code", "ERROR"),
                                     result.get("error", "unknown error"))
        return result

    # ---- operations ----

    def header(self) -> dict:
        """Container check that needs NO master password."""
        return self._call({"op": "header"})

    def verify(self, password: str) -> dict:
        """Unlock and report entry/group counts. Proves the password works."""
        return self._call({"op": "verify"}, password=password)

    def list_metadata(self, password: str) -> list:
        """Entry metadata only — no secret values (§16)."""
        return self._call({"op": "list_metadata"}, password=password).get("entries", [])

    def read_entry(self, title: str, password: str) -> dict:
        """Read ONE entry by title. This is the only op returning a secret."""
        return self._call({"op": "read_entry", "title": title}, password=password)

    def create_entry(self, title: str, secret: str, password: str,
                     username: str = "", url: str = "", notes: str = "",
                     group: str = "") -> dict:
        return self._call({
            "op": "create_entry", "title": title, "secret": secret,
            "username": username, "url": url, "notes": notes, "group": group,
        }, password=password)

    def update_entry(self, title: str, password: str,
                     secret: str | None = None, username: str | None = None,
                     notes: str | None = None, url: str | None = None) -> dict:
        payload = {"op": "update_entry", "title": title}
        if secret is not None:
            payload["secret"] = secret
        if username is not None:
            payload["username"] = username
        if notes is not None:
            payload["notes"] = notes
        if url is not None:
            payload["url"] = url
        return self._call(payload, password=password)
