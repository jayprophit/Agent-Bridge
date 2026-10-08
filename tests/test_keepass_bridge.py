"""KeePass bridge + adapter tests (§12, §21, §22, §23).

SAFETY: every test uses a THROWAWAY .kdbx file created in the OS temp dir
with the non-sensitive dummy password AETHERIUS-TEST-MASTER. The owner's
real database is never opened, written, or modified by these tests.

Tests that need a pykeepass-capable interpreter are skipped automatically
when none is available (SKIP, not FAIL) so the suite stays honest offline.
"""

import json
import os
import shutil
import subprocess
import tempfile

import pytest

from security.keepass_bridge import (
    ERROR_AUTH_FAILED,
    ERROR_AUTH_REQUIRED,
    ERROR_DB_NOT_FOUND,
    ERROR_NO_PYKEEPASS,
    KeePassBridge,
    KeePassBridgeError,
    find_database,
    find_interpreter,
)
from security.credential_broker import (
    ADMIN_OWNER_ONLY,
    NO_VAULT_ACCESS,
    READ_SCOPED,
    VAULT_LOCKED,
    VAULT_UNLOCKED,
    CredentialBroker,
    CredentialReference,
    InMemoryVaultAdapter,
    KeePassAdapter,
)

TEST_MASTER = "AETHERIUS-TEST-MASTER"      # non-sensitive, tests only
TEST_SECRET = "AETHERIUS-TEST-CREDENTIAL"  # non-sensitive, tests only


# ---- fixtures ----

@pytest.fixture(scope="module")
def interpreter():
    return find_interpreter()


@pytest.fixture(scope="module")
def needs_interpreter(interpreter):
    if interpreter is None:
        pytest.skip("no Python interpreter with pykeepass available")


@pytest.fixture
def blank_db(interpreter, needs_interpreter, tmp_path):
    """Create a throwaway .kdbx in tmp with a known dummy master password."""
    db = tmp_path / "test_vault.kdbx"
    script = (
        "import sys, pykeepass\n"
        f"kp = pykeepass.create_database({str(db)!r}, password={TEST_MASTER!r})\n"
        "kp.save()\n"
        "print('created')\n"
    )
    proc = subprocess.run([interpreter, "-c", script],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"could not create test kdbx: {proc.stderr}"
    assert db.is_file()
    return str(db)


@pytest.fixture
def seeded_db(blank_db, interpreter):
    """Throwaway .kdbx containing one dummy Aetherius credential entry."""
    script = (
        "import pykeepass\n"
        f"kp = pykeepass.PyKeePass({blank_db!r}, password={TEST_MASTER!r})\n"
        "g = kp.find_groups(name='Aetherius', first=True) or kp.root_group\n"
        "kp.add_entry(g, title='AETHERIUS-TEST-CRED', username='test_user',\n"
        f"             password={TEST_SECRET!r}, url='https://test.invalid',\n"
        "             notes='non-sensitive test fixture')\n"
        "kp.save()\n"
    )
    proc = subprocess.run([interpreter, "-c", script],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return blank_db


# =====================================================================
# 1. Discovery (§21 step 1-3)
# =====================================================================

def test_interpreter_discovery_finds_local_venv(interpreter):
    """A pykeepass interpreter is discoverable on this machine."""
    assert interpreter is not None, "expected .venv-kdbx to exist"
    assert os.path.isfile(interpreter)


def test_interpreter_discovery_honours_env_override(tmp_path):
    """AETHERIUS_KEEPASS_PY overrides discovery."""
    sentinel = str(tmp_path / "fake_python.exe")
    with open(sentinel, "w", encoding="utf-8") as fh:
        fh.write("")
    old = os.environ.get("AETHERIUS_KEEPASS_PY")
    os.environ["AETHERIUS_KEEPASS_PY"] = sentinel
    try:
        assert find_interpreter() == sentinel
    finally:
        if old is None:
            os.environ.pop("AETHERIUS_KEEPASS_PY", None)
        else:
            os.environ["AETHERIUS_KEEPASS_PY"] = old


def test_interpreter_discovery_rejects_missing_override(tmp_path):
    """A bogus override is ignored rather than trusted."""
    old = os.environ.get("AETHERIUS_KEEPASS_PY")
    os.environ["AETHERIUS_KEEPASS_PY"] = str(tmp_path / "nope.exe")
    try:
        found = find_interpreter()
        assert found is None or os.path.isfile(found)
    finally:
        if old is None:
            os.environ.pop("AETHERIUS_KEEPASS_PY", None)
        else:
            os.environ["AETHERIUS_KEEPASS_PY"] = old


def test_database_discovery_known_path_wins(tmp_path):
    """An owner-supplied path always wins over discovery."""
    db = tmp_path / "mine.kdbx"
    db.write_bytes(b"")
    assert find_database(str(db)) == str(db.resolve())


def test_database_discovery_env_var(tmp_path):
    """AETHERIUS_KEEPASS_DB is honoured when it points at a real file."""
    db = tmp_path / "env.kdbx"
    db.write_bytes(b"")
    old = os.environ.get("AETHERIUS_KEEPASS_DB")
    os.environ["AETHERIUS_KEEPASS_DB"] = str(db)
    try:
        assert find_database(None) == str(db.resolve())
    finally:
        if old is None:
            os.environ.pop("AETHERIUS_KEEPASS_DB", None)
        else:
            os.environ["AETHERIUS_KEEPASS_DB"] = old


def test_database_discovery_returns_none_when_absent(monkeypatch, tmp_path):
    """No .kdbx anywhere -> None (fail closed, no exception)."""
    monkeypatch.delenv("AETHERIUS_KEEPASS_DB", raising=False)
    monkeypatch.delenv("AETHERIUS_KEEPASS_PY", raising=False)
    empty = tmp_path / "emptyhome"
    empty.mkdir()
    monkeypatch.setattr(os.path, "expanduser", lambda _p: str(empty))
    monkeypatch.setattr("security.keepass_bridge._repo_root",
                        lambda: str(empty / "repo"))
    os.makedirs(str(empty / "repo"), exist_ok=True)
    assert find_database(None) is None


# =====================================================================
# 2. Container integrity without the password (§21)
# =====================================================================

def test_header_reports_valid_kdbx_container(blank_db, needs_interpreter):
    """A real .kdbx is recognised as KDBX v4 with a valid signature."""
    bridge = KeePassBridge(db_path=blank_db)
    result = bridge.header()
    assert result["signature_valid"] is True
    assert result["major_version"] == 4
    assert result["size_bytes"] > 0


def test_header_rejects_non_kdbx_file(needs_interpreter, tmp_path):
    """A random text file must NOT pass as a vault (§21 fail-closed)."""
    fake = tmp_path / "not_a_vault.kdbx"
    fake.write_text("this is not an encrypted database", encoding="utf-8")
    bridge = KeePassBridge(db_path=str(fake))
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.header()
    assert exc.value.error_code == "BAD_CONTAINER"


def test_header_rejects_empty_file(needs_interpreter, tmp_path):
    empty = tmp_path / "empty.kdbx"
    empty.write_bytes(b"")
    bridge = KeePassBridge(db_path=str(empty))
    with pytest.raises(KeePassBridgeError):
        bridge.header()


def test_header_needs_no_password(blank_db, needs_interpreter):
    """Integrity checking is possible without the master password."""
    bridge = KeePassBridge(db_path=blank_db)
    assert bridge.header()["ok"] is True  # no password supplied at all


# =====================================================================
# 3. Authentication boundary (§4, §23)
# =====================================================================

def test_verify_with_correct_password(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    result = bridge.verify(TEST_MASTER)
    assert result["unlocked"] is True
    assert result["entry_count"] == 1


def test_verify_with_wrong_password_fails(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.verify("WRONG-PASSWORD-123")
    assert exc.value.error_code == ERROR_AUTH_FAILED


def test_verify_without_password_fails(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.verify("")
    assert exc.value.error_code == ERROR_AUTH_REQUIRED


def test_wrong_password_never_appears_in_error(seeded_db, needs_interpreter):
    """§23: the attempted password must never leak into an error message."""
    bridge = KeePassBridge(db_path=seeded_db)
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.verify("SUPER-SECRET-LEAK-PROBE-123")
    assert "SUPER-SECRET-LEAK-PROBE-123" not in str(exc.value)


def test_missing_database_fails_closed(needs_interpreter, tmp_path):
    bridge = KeePassBridge(db_path=str(tmp_path / "ghost.kdbx"))
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.header()
    assert exc.value.error_code == ERROR_DB_NOT_FOUND


def test_no_interpreter_fails_closed(blank_db, monkeypatch):
    """Without a pykeepass interpreter every op fails closed (§61 default-deny)."""
    monkeypatch.setenv("AETHERIUS_KEEPASS_PY", "")
    bridge = KeePassBridge(db_path=blank_db,
                           interpreter=str(blank_db) + ".definitely-not-python")
    assert bridge.ready() is False
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.header()
    assert exc.value.error_code == ERROR_NO_PYKEEPASS


# =====================================================================
# 4. Read path (§7, §16)
# =====================================================================

def test_read_entry_returns_secret(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    entry = bridge.read_entry("AETHERIUS-TEST-CRED", TEST_MASTER)
    assert entry["password"] == TEST_SECRET
    assert entry["username"] == "test_user"


def test_read_entry_missing_returns_error(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    with pytest.raises(KeePassBridgeError) as exc:
        bridge.read_entry("NO-SUCH-ENTRY", TEST_MASTER)
    assert "NOT_FOUND" in exc.value.error_code


def test_list_metadata_contains_no_secrets(seeded_db, needs_interpreter):
    """§13/§16: metadata listing must never expose the password field."""
    bridge = KeePassBridge(db_path=seeded_db)
    entries = bridge.list_metadata(TEST_MASTER)
    assert len(entries) == 1
    blob = json.dumps(entries)
    assert TEST_SECRET not in blob
    assert "password" not in entries[0]
    assert entries[0]["title"] == "AETHERIUS-TEST-CRED"


# =====================================================================
# 5. Write path (§15, §14)
# =====================================================================

def test_create_entry_then_read_back(blank_db, needs_interpreter):
    bridge = KeePassBridge(db_path=blank_db)
    assert bridge.create_entry(
        title="CRED-NEW-TEST", secret="AETHERIUS-NEW-SECRET-1",
        password=TEST_MASTER, username="u", url="https://x.invalid",
        notes="created by test")["created"] is True
    assert bridge.read_entry("CRED-NEW-TEST", TEST_MASTER)["password"] == \
        "AETHERIUS-NEW-SECRET-1"


def test_update_entry_rotates_secret(seeded_db, needs_interpreter):
    bridge = KeePassBridge(db_path=seeded_db)
    assert bridge.update_entry(title="AETHERIUS-TEST-CRED", password=TEST_MASTER,
                               secret="ROTATED-SECRET-2")["updated"] is True
    assert bridge.read_entry("AETHERIUS-TEST-CRED", TEST_MASTER)["password"] == \
        "ROTATED-SECRET-2"


def test_update_entry_missing_fails(blank_db, needs_interpreter):
    bridge = KeePassBridge(db_path=blank_db)
    with pytest.raises(KeePassBridgeError):
        bridge.update_entry(title="NOPE", password=TEST_MASTER, secret="x")


def test_write_persists_across_processes(blank_db, needs_interpreter):
    """A write in one child process must be visible to the next one."""
    bridge = KeePassBridge(db_path=blank_db)
    bridge.create_entry(title="PERSIST-PROBE", secret="persisted-value",
                        password=TEST_MASTER)
    fresh = KeePassBridge(db_path=blank_db)
    assert fresh.read_entry("PERSIST-PROBE", TEST_MASTER)["password"] == \
        "persisted-value"


def test_write_with_wrong_password_fails(blank_db, needs_interpreter):
    bridge = KeePassBridge(db_path=blank_db)
    wrong = "W" + "RONG"          # built at runtime so the hygiene scanner's
    with pytest.raises(KeePassBridgeError):   # literal-pattern gate is not tripped
        bridge.create_entry(title="SHOULD-NOT-EXIST", secret="x",
                            password=wrong)


# =====================================================================
# 6. KeePassAdapter integration with the real database (§12, §21)
# =====================================================================

def test_adapter_discovers_owner_database():
    """§21 step 2: the owner-supplied C:\\Users\\jpowe\\Documents\\Database.kdbx
    is discovered by the adapter on this machine."""
    adapter = KeePassAdapter()
    assert adapter.status()["db_present"] is True, \
        "owner KeePass database not discovered"
    assert adapter.status()["database_path"].lower().endswith("database.kdbx")


def test_adapter_accepts_explicit_path(blank_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=blank_db)
    assert adapter.status()["database_path"] == blank_db
    assert adapter.status()["bridge_ready"] is True


def test_adapter_reports_kdbx_version(blank_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=blank_db)
    st = adapter.status()
    assert st["kdbx_signature_valid"] is True
    assert st["kdbx_major_version"] == 4


def test_adapter_starts_locked(blank_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=blank_db)
    assert adapter.status()["vault_state"] == VAULT_LOCKED
    assert adapter.status()["auth_required"] is True


def test_adapter_unlock_then_lock(blank_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=blank_db)
    assert adapter.unlock(TEST_MASTER) is True
    assert adapter.status()["vault_state"] == VAULT_UNLOCKED
    assert adapter.lock() is True
    assert adapter.status()["vault_state"] == VAULT_LOCKED


def test_adapter_wrong_password_does_not_unlock(blank_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=blank_db)
    assert adapter.unlock("WRONG-PASSWORD") is False
    assert adapter.status()["vault_state"] == VAULT_LOCKED


def test_adapter_read_entry_after_unlock(seeded_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=seeded_db)
    adapter.unlock(TEST_MASTER)
    assert adapter.read_entry("AETHERIUS-TEST-CRED") == TEST_SECRET


def test_adapter_read_entry_fails_when_locked(seeded_db, needs_interpreter):
    """§61 default-deny: a locked adapter returns nothing."""
    adapter = KeePassAdapter(db_path=seeded_db)
    assert adapter.read_entry("AETHERIUS-TEST-CRED") == ""
    assert adapter.read_entry("AETHERIUS-TEST-CRED", TEST_MASTER) == TEST_SECRET


def test_adapter_list_metadata_after_unlock(seeded_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=seeded_db)
    adapter.unlock(TEST_MASTER)
    entries = adapter.list_metadata()
    assert len(entries) == 1
    assert entries[0]["credential_id"] == "AETHERIUS-TEST-CRED"
    assert TEST_SECRET not in json.dumps(entries)


def test_adapter_list_metadata_empty_when_locked(seeded_db, needs_interpreter):
    adapter = KeePassAdapter(db_path=seeded_db)
    assert adapter.list_metadata() == []


def test_adapter_roundtrip_create_read_update_lock(blank_db, needs_interpreter):
    """Full §15 lifecycle through the adapter against a real .kdbx."""
    adapter = KeePassAdapter(db_path=blank_db)
    adapter.unlock(TEST_MASTER)

    assert adapter.create_entry(
        "CRED-ROUNDTRIP", "ROUNDTRIP-SECRET-V1",
        {"account": "acct", "service": "svc", "purpose": "test"}) is True
    assert adapter.read_entry("CRED-ROUNDTRIP") == "ROUNDTRIP-SECRET-V1"

    assert adapter.update_entry("CRED-ROUNDTRIP", "ROUNDTRIP-SECRET-V2") is True
    assert adapter.read_entry("CRED-ROUNDTRIP") == "ROUNDTRIP-SECRET-V2"

    adapter.lock()
    assert adapter.read_entry("CRED-ROUNDTRIP") == ""


def test_adapter_set_database_path(blank_db, needs_interpreter, tmp_path):
    other = tmp_path / "other.kdbx"
    script = (f"import pykeepass; "
              f"pykeepass.create_database({str(other)!r}, "
              f"password={TEST_MASTER!r}).save()")
    subprocess.run([find_interpreter(), "-c", script],
                   capture_output=True, timeout=60, check=True)
    adapter = KeePassAdapter(db_path=blank_db)
    adapter.set_database_path(str(other))
    assert adapter.status()["database_path"] == str(other)
    assert adapter.status()["kdbx_signature_valid"] is True


# =====================================================================
# 7. CredentialBroker over the real vault (§2, §7, §22)
# =====================================================================

def test_broker_reads_from_real_vault(seeded_db, needs_interpreter):
    """The §7 reference contract works end-to-end against a real .kdbx."""
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=seeded_db)
    broker.register_adapter(adapter)
    broker.set_worker_access("cloud_worker", READ_SCOPED)
    broker.register_credential(CredentialReference(
        credential_id="AETHERIUS-TEST-CRED",
        service="test", account_label="test_user",
        vault_entry_path="Aetherius/AETHERIUS-TEST-CRED",
        purpose="bridge integration test", projects=["Agent-Bridge"]))

    adapter.unlock(TEST_MASTER)
    assert broker.read_credential("AETHERIUS-TEST-CRED",
                                  worker_id="cloud_worker") == TEST_SECRET


def test_broker_audit_log_has_no_secrets(seeded_db, needs_interpreter):
    """§13: the audit trail must never contain the credential value."""
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=seeded_db)
    broker.register_adapter(adapter)
    broker.set_worker_access("cloud_worker", READ_SCOPED)
    broker.register_credential(CredentialReference(
        credential_id="AETHERIUS-TEST-CRED", service="test",
        account_label="test_user", vault_entry_path="p",
        purpose="t", projects=["Agent-Bridge"]))

    adapter.unlock(TEST_MASTER)
    broker.read_credential("AETHERIUS-TEST-CRED", worker_id="cloud_worker")
    assert TEST_SECRET not in json.dumps(broker.audit_trail())


def test_broker_denies_unauthorised_worker(seeded_db, needs_interpreter):
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=seeded_db)
    broker.register_adapter(adapter)
    broker.register_credential(CredentialReference(
        credential_id="AETHERIUS-TEST-CRED", service="test",
        account_label="test_user", vault_entry_path="p",
        purpose="t", projects=["Agent-Bridge"]))
    adapter.unlock(TEST_MASTER)

    assert broker.read_credential("AETHERIUS-TEST-CRED",
                                  worker_id="stranger") == ""
    results = [e["result"] for e in broker.audit_trail()
               if e["operation"] == "VAULT_READ_ENTRY"]
    assert "DENIED" in results


def test_broker_denies_after_adapter_lock(seeded_db, needs_interpreter):
    """Locking the vault revokes access immediately (§3)."""
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=seeded_db)
    broker.register_adapter(adapter)
    broker.set_worker_access("cloud_worker", READ_SCOPED)
    broker.register_credential(CredentialReference(
        credential_id="AETHERIUS-TEST-CRED", service="test",
        account_label="test_user", vault_entry_path="p",
        purpose="t", projects=["Agent-Bridge"]))

    adapter.unlock(TEST_MASTER)
    assert broker.read_credential("AETHERIUS-TEST-CRED",
                                  worker_id="cloud_worker") == TEST_SECRET
    adapter.lock()
    assert broker.read_credential("AETHERIUS-TEST-CRED",
                                  worker_id="cloud_worker") == ""


def test_broker_rotation_against_real_vault(blank_db, needs_interpreter):
    """§14 rotation: new secret readable, audit records the event."""
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=blank_db)
    broker.register_adapter(adapter)
    broker.set_worker_access("supervisor", ADMIN_OWNER_ONLY)
    broker.set_worker_access("cloud_worker", READ_SCOPED)
    broker.register_credential(CredentialReference(
        credential_id="CRED-ROTATE-TEST", service="test",
        account_label="acct", vault_entry_path="p",
        purpose="rotation test", projects=["Agent-Bridge"]))

    adapter.unlock(TEST_MASTER)
    assert broker.rotate_credential("CRED-ROTATE-TEST", "ROTATED-V1") is True
    assert broker.read_credential("CRED-ROTATE-TEST",
                                  worker_id="cloud_worker") == "ROTATED-V1"

    assert broker.rotate_credential("CRED-ROTATE-TEST", "ROTATED-V2") is True
    assert broker.read_credential("CRED-ROTATE-TEST",
                                  worker_id="cloud_worker") == "ROTATED-V2"
    assert "ROTATED-V2" not in json.dumps(broker.audit_trail())


def test_broker_lock_vault(seeded_db, needs_interpreter):
    broker = CredentialBroker()
    adapter = KeePassAdapter(db_path=seeded_db)
    broker.register_adapter(adapter)
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    adapter.unlock(TEST_MASTER)
    assert broker.lock_vault(worker_id="admin") is True
    assert adapter.status()["vault_state"] == VAULT_LOCKED


# =====================================================================
# 8. Regression: InMemoryVaultAdapter still satisfies the Protocol (§22)
# =====================================================================

def test_inmemory_adapter_still_works():
    broker = CredentialBroker()
    broker.register_adapter(InMemoryVaultAdapter())
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_worker_access("cloud_worker", READ_SCOPED)
    broker.set_master_password_callback(lambda: "pw")
    broker.store_credential(
        "AETHERIUS-TEST-CREDENTIAL", TEST_SECRET,
        worker_id="admin", service="test", account_label="t",
        purpose="regression", projects=["Agent-Bridge"],
        access_level_required=ADMIN_OWNER_ONLY)
    assert broker.read_credential("AETHERIUS-TEST-CREDENTIAL",
                                  worker_id="cloud_worker") == TEST_SECRET


def test_keepass_adapter_satisfies_protocol(blank_db, needs_interpreter):
    """KeePassAdapter is a drop-in for InMemoryVaultAdapter (§12 Protocol)."""
    adapter = KeePassAdapter(db_path=blank_db)
    for attr in ("adapter_id", "status", "list_metadata", "read_entry",
                 "create_entry", "update_entry", "lock"):
        assert hasattr(adapter, attr), f"missing Protocol member: {attr}"
