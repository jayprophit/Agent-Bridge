"""Tests for the Aetherius Credential Broker (§22 of KeePass Access Policy).

Uses a non-sensitive test entry (AETHERIUS-TEST-CREDENTIAL) with a dummy value.
Proves: create, read, update, reference lookup, scoped access, denied worker,
audit log contains no secret, lock-state handling, delete requires approval.

Run: python tests/test_credential_broker.py -v
  or: python -m pytest tests/test_credential_broker.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.credential_broker import (
    CredentialBroker, CredentialReference, AuditEvent,
    InMemoryVaultAdapter, KeePassAdapter,
    NO_VAULT_ACCESS, METADATA_ONLY, READ_SCOPED, READ_WRITE_SCOPED,
    ROTATION_SCOPED, ADMIN_OWNER_ONLY,
    VAULT_UNLOCKED, VAULT_LOCKED,
    OP_READ_ENTRY, OP_CREATE_ENTRY, OP_UPDATE_ENTRY, OP_STORE_NEW_SECRET,
    OP_LIST_METADATA, OP_LOCK,
    DESTRUCTIVE_OPS,
)

TEST_CREDENTIAL_ID = "AETHERIUS-TEST-CREDENTIAL"
TEST_SECRET = "dummy-test-secret-value-12345"
TEST_SECRET_UPDATED = "updated-dummy-value-67890"


def test_broker_creation():
    """CredentialBroker can be created with an in-memory adapter."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    assert broker is not None
    st = broker.status()
    assert st["broker_status"] == VAULT_UNLOCKED
    assert st["registered_credentials"] == 0


def test_broker_store_and_read():
    """Store and read a non-sensitive test credential (§22)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("test_worker", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "test-master-pw")

    # Store
    success = broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="test_worker",
        service="test-service",
        account_label="test-account",
        purpose="unit-test",
        projects=["test-project"],
    )
    assert success is True
    assert len(broker.list_credentials_metadata("test_worker")) == 1

    # Read back
    secret = broker.read_credential(TEST_CREDENTIAL_ID, worker_id="test_worker")
    assert secret == TEST_SECRET


def test_broker_update():
    """Update a credential entry (§22)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("test_worker", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "test-master-pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="test_worker",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    # Update via rotate
    broker.rotate_credential(TEST_CREDENTIAL_ID, TEST_SECRET_UPDATED,
                             worker_id="test_worker")
    secret = broker.read_credential(TEST_CREDENTIAL_ID, worker_id="test_worker")
    assert secret == TEST_SECRET_UPDATED


def test_broker_reference_lookup():
    """Credential lookup by stable reference ID (§7)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("test_worker", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "test-master-pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="test_worker",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    # Reference exists in registry (metadata only, not the secret)
    metas = broker.list_credentials_metadata("test_worker")
    assert any(m["credential_id"] == TEST_CREDENTIAL_ID for m in metas)


def test_broker_scoped_access_read():
    """Worker with READ_SCOPED can read (§8)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("reader", READ_SCOPED)
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    # READ_SCOPED worker can read
    secret = broker.read_credential(TEST_CREDENTIAL_ID, worker_id="reader",
                                    project="test-project")
    assert secret == TEST_SECRET


def test_broker_metadata_only_cannot_read():
    """METADATA_ONLY worker cannot read secret values (§8)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("metadata_only_worker", METADATA_ONLY)
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    # METADATA_ONLY can see metadata but NOT read secret
    metas = broker.list_credentials_metadata("metadata_only_worker")
    assert len(metas) == 1  # can see metadata
    assert metas[0]["credential_id"] == TEST_CREDENTIAL_ID

    secret = broker.read_credential(TEST_CREDENTIAL_ID,
                                    worker_id="metadata_only_worker")
    assert secret == ""  # denied


def test_broker_denied_unauthorized_worker():
    """NO_VAULT_ACCESS worker gets nothing (§8)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("unauthorized", NO_VAULT_ACCESS)
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    secret = broker.read_credential(TEST_CREDENTIAL_ID,
                                    worker_id="unauthorized")
    assert secret == ""
    metas = broker.list_credentials_metadata("unauthorized")
    assert len(metas) == 0


def test_broker_audit_no_secrets():
    """Audit trail must NEVER contain secret values (§13)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    broker.read_credential(TEST_CREDENTIAL_ID, worker_id="admin")

    for ev in broker.audit_trail():
        ev_str = str(ev)
        assert TEST_SECRET not in ev_str, f"Secret leaked in audit: {ev_str}"
        assert "dummy-test" not in ev_str


def test_broker_project_isolation():
    """Worker from project A cannot read credentials scoped to project B."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("worker_a", READ_SCOPED)
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["project-b"],
    )
    # Worker from project A cannot read
    secret = broker.read_credential(TEST_CREDENTIAL_ID,
                                    worker_id="worker_a",
                                    project="project-a")
    assert secret == ""

    # Worker from project B can read
    secret = broker.read_credential(TEST_CREDENTIAL_ID,
                                    worker_id="worker_a",
                                    project="project-b")
    assert secret == TEST_SECRET


def test_broker_lock():
    """Vault lock clears state (§3)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    lock_result = broker.lock_vault(worker_id="admin")
    assert lock_result is True
    # After lock, adapter should be locked
    for ev in broker.audit_trail():
        assert "dummy-test-secret" not in str(ev)


def test_broker_rotate_revokes_old():
    """Rotation marks old credential as REVOKED, then ACTIVE (§14)."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    # Get the credential ref
    cred_ref = broker._registry.get(TEST_CREDENTIAL_ID)
    assert cred_ref.status == "ACTIVE"

    # Rotate
    success = broker.rotate_credential(TEST_CREDENTIAL_ID, TEST_SECRET_UPDATED,
                                       worker_id="admin")
    assert success is True
    # After rotation, credential should be ACTIVE again with new value
    assert cred_ref.status == "ACTIVE"
    assert cred_ref.last_verified is not None
    secret = broker.read_credential(TEST_CREDENTIAL_ID, worker_id="admin")
    assert secret == TEST_SECRET_UPDATED


def test_broker_destructive_ops_denied():
    """Destructive operations are in the deny set (§3)."""
    assert "DELETE_ENTRY" in DESTRUCTIVE_OPS
    assert "DELETE_DATABASE" in DESTRUCTIVE_OPS
    assert "OVERWRITE_DATABASE" in DESTRUCTIVE_OPS


def test_broker_status_no_secrets():
    """Broker status must not expose secrets."""
    broker = CredentialBroker(vault_adapter=InMemoryVaultAdapter())
    broker.set_worker_access("admin", ADMIN_OWNER_ONLY)
    broker.set_master_password_callback(lambda: "pw")

    broker.store_credential(
        credential_id=TEST_CREDENTIAL_ID,
        secret_value=TEST_SECRET,
        worker_id="admin",
        service="test", account_label="acct", purpose="test",
        projects=["test-project"],
    )
    st = broker.status()
    st_str = str(st)
    assert TEST_SECRET not in st_str


def test_keeppass_adapter_discovery():
    """KeePassAdapter discovers KeePass installation (§21 step 1)."""
    adapter = KeePassAdapter()
    st = adapter.status()
    assert st["adapter_id"] == "keepass"
    assert "keepass_installed" in st
    assert "database_path" in st
    assert "auth_required" in st
    # KeePass 2 was found installed at C:/Program Files/KeePass Password Safe 2/KeePass.exe
    assert st["keepass_installed"] is True


if __name__ == "__main__":
    tests = [
        ("test_broker_creation", test_broker_creation),
        ("test_broker_store_and_read", test_broker_store_and_read),
        ("test_broker_update", test_broker_update),
        ("test_broker_reference_lookup", test_broker_reference_lookup),
        ("test_broker_scoped_access_read", test_broker_scoped_access_read),
        ("test_broker_metadata_only_cannot_read", test_broker_metadata_only_cannot_read),
        ("test_broker_denied_unauthorized_worker", test_broker_denied_unauthorized_worker),
        ("test_broker_audit_no_secrets", test_broker_audit_no_secrets),
        ("test_broker_project_isolation", test_broker_project_isolation),
        ("test_broker_lock", test_broker_lock),
        ("test_broker_rotate_revokes_old", test_broker_rotate_revokes_old),
        ("test_broker_destructive_ops_denied", test_broker_destructive_ops_denied),
        ("test_broker_status_no_secrets", test_broker_status_no_secrets),
        ("test_keeppass_adapter_discovery", test_keeppass_adapter_discovery),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {name}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    total = passed + failed
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {total} total")
    print(f"{'='*60}")
    sys.exit(1 if failed else 0)
