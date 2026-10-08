"""Tests for the Aetherius Data Service Registry + Policy Engine (§33, §34, §35, §60, §61).

Covers:
- Data Service Registry: register, query, state management, data class indexing
- Default registry: all §53 services pre-registered with accurate states
- Data Service Adapter: LocalFileAdapter (read/write/search/backup/restore)
- Data Policy Engine: default policies, DENY precedence, cloud restrictions
- DataClass enum: all categories from §34
- AppState enum: all states from §6
- Test data only — no real secrets (§47)

Run: python tests/test_data_service_registry.py -v
"""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_fabric.data_service_registry import (
    DataServiceRegistry, DataServiceEntry,
    AppState, SourceModel, SourceType, DataClass,
)
from data_fabric.default_registry import build_default_registry
from data_fabric.data_service_adapter import (
    DataServiceAdapter, LocalFileAdapter, DataServiceAdapterRegistry,
)
from data_fabric.data_policy_engine import (
    DataPolicyEngine, DataPolicyRule,
    DataAction, ExecutionLocation, AccessDecision,
)
from security.vault_adapters import ProtonPassAdapter, BitwardenAdapter
from security.credential_broker import InMemoryVaultAdapter, KeePassAdapter

from security.credential_broker import VAULT_UNLOCKED, VAULT_LOCKED

# === Data Service Registry tests (§33) ===

def test_registry_create_register():
    """Registry can register a service (§33)."""
    reg = DataServiceRegistry()
    entry = DataServiceEntry(
        service_id="test-svc",
        name="Test Service",
        category="test",
        source_model=SourceModel.LOCAL,
        source_type=SourceType.OPEN_SOURCE,
        pricing="free",
        state=AppState.EVALUATION,
        data_classes=[DataClass.NOTES.value],
    )
    reg.register(entry)
    assert reg.get("test-svc") is not None
    assert reg.get("test-svc").name == "Test Service"


def test_registry_state_transitions():
    """Service states transition correctly (§6)."""
    reg = DataServiceRegistry()
    entry = DataServiceEntry(
        service_id="svc-1", name="Svc1", category="test",
        source_model=SourceModel.LOCAL,
        source_type=SourceType.OPEN_SOURCE,
        pricing="free",
        state=AppState.NOT_INSTALLED,
        data_classes=[DataClass.FILES.value],
    )
    reg.register(entry)

    # NOT_INSTALLED -> INSTALLED
    reg.set_state("svc-1", AppState.INSTALLED,
                  installed_version="1.0.0",
                  installation_path="/opt/svc1")
    assert reg.get("svc-1").state == AppState.INSTALLED

    # INSTALLED -> VERIFIED
    reg.set_state("svc-1", AppState.VERIFIED)
    assert reg.get("svc-1").state == AppState.VERIFIED
    assert reg.get("svc-1").last_verified is not None
    assert reg.get("svc-1").health == "HEALTHY"


def test_registry_data_class_index():
    """Services are indexed by data class (§33, §45)."""
    reg = DataServiceRegistry()
    reg.register(DataServiceEntry(
        service_id="svc-a", name="A", category="pw",
        source_model=SourceModel.LOCAL, source_type=SourceType.OPEN_SOURCE,
        pricing="free", state=AppState.PRIMARY,
        data_classes=[DataClass.CREDENTIALS.value, DataClass.TWO_FACTOR.value],
    ))
    reg.register(DataServiceEntry(
        service_id="svc-b", name="B", category="pw",
        source_model=SourceModel.HOSTED, source_type=SourceType.OPEN_SOURCE,
        pricing="freemium", state=AppState.SECONDARY,
        data_classes=[DataClass.CREDENTIALS.value],
    ))

    cred_services = reg.services_by_class(DataClass.CREDENTIALS.value)
    assert len(cred_services) == 2

    primary = reg.primary_for_class(DataClass.CREDENTIALS.value)
    assert primary.service_id == "svc-a"
    assert primary.state == AppState.PRIMARY


def test_registry_add_credential_ref():
    """Registry can link services to credential references (§8, §42)."""
    reg = DataServiceRegistry()
    entry = DataServiceEntry(
        service_id="svc-1", name="Svc1", category="test",
        source_model=SourceModel.LOCAL, source_type=SourceType.OPEN_SOURCE,
        pricing="free", state=AppState.NOT_INSTALLED,
        data_classes=[DataClass.CREDENTIALS.value],
    )
    reg.register(entry)
    reg.add_credential_ref("svc-1", "CRED-OPENROUTER-PRIMARY")
    assert "CRED-OPENROUTER-PRIMARY" in reg.get("svc-1").credential_refs


def test_registry_summary_no_secrets():
    """Registry summary contains no secrets (§33)."""
    reg = DataServiceRegistry()
    entry = DataServiceEntry(
        service_id="svc-1", name="Svc1", category="test",
        source_model=SourceModel.LOCAL, source_type=SourceType.OPEN_SOURCE,
        pricing="free", state=AppState.INSTALLED,
        data_classes=[DataClass.CREDENTIALS.value],
        credential_refs=["CRED-TEST"],
    )
    reg.register(entry)
    summary = reg.summary()
    summary_str = str(summary)
    # Credential refs should not contain actual secret values
    assert "CRED-TEST" in summary_str  # ref ID is OK
    assert "secret" not in summary_str.lower()


def test_default_registry_all_services():
    """Default registry contains all §53 service categories (§53)."""
    reg = build_default_registry()
    services = reg.all_services()
    assert len(services) >= 20  # At least the core services from §53

    # Check KeePass is PRIMARY
    keepass = reg.get("keepass-canonical")
    assert keepass is not None
    assert keepass.state == AppState.PRIMARY

    # Check cloud providers are NOT_INSTALLED or EVALUATION
    bitwarden = reg.get("bitwarden")
    assert bitwarden is not None
    assert bitwarden.state in [AppState.EVALUATION, AppState.NOT_INSTALLED]


def test_default_registry_states_accurate():
    """Default registry states reflect live inventory (§4, §56)."""
    reg = build_default_registry()

    # KeePass is installed and PRIMARY (verified by live inventory)
    keepass = reg.get("keepass-canonical")
    assert keepass.state == AppState.PRIMARY
    assert keepass.health == "VERIFIED_LIVE"

    # Docker is installed and VERIFIED
    docker = reg.get("docker")
    assert docker.state == AppState.VERIFIED

    # Proton Pass is NOT INSTALLED
    proton = reg.get("proton-pass")
    assert proton.state == AppState.NOT_INSTALLED

    # GitHub requires owner account action
    gh = reg.get("github")
    assert gh.account_state == "VERIFIED_LIVE"


def test_default_registry_data_classes():
    """Data classes from §34 are represented (§34)."""
    reg = build_default_registry()
    all_classes = set()
    for s in reg.all_services():
        all_classes.update(s.data_classes)

    expected_classes = {
        DataClass.CREDENTIALS.value,
        DataClass.TWO_FACTOR.value,
        DataClass.EMAIL.value,
        DataClass.CALENDAR.value,
        DataClass.CONTACTS.value,
        DataClass.FILES.value,
        DataClass.DOCUMENTS.value,
        DataClass.NOTES.value,
        DataClass.FINANCE.value,
        DataClass.BUSINESS.value,
        DataClass.MESSAGING.value,
        DataClass.IDENTITY.value,
        DataClass.LEGAL.value,
        DataClass.PHOTOS.value,
        DataClass.BACKUPS.value,
        DataClass.SOURCE_CODE.value,
    }
    assert expected_classes.issubset(all_classes)


def test_registry_export_import():
    """Registry can export/import without secrets (§57, §40)."""
    reg = build_default_registry()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    try:
        reg.to_json(path)
        reg2 = DataServiceRegistry.from_json(path)
        assert len(reg2.all_services()) == len(reg.all_services())
        # Verify no secret values in export
        with open(path) as f:
            content = f.read()
        assert "secret_value" not in content
        assert "actual_password" not in content
    finally:
        os.unlink(path)


def test_registry_category_index():
    """Services indexed by category."""
    reg = build_default_registry()
    pw_services = reg.services_by_category("password_manager")
    assert len(pw_services) >= 3  # KeePass, KeePassXC, Bitwarden, Proton Pass

    email_services = reg.services_by_category("email")
    assert len(email_services) >= 2  # Proton Mail, Tuta


# === Data Service Adapter tests (§60) ===

def test_local_file_adapter_read_write():
    """LocalFileAdapter can read/write files (§60, §47 test data only)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalFileAdapter("test-svc", tmpdir)
        assert adapter.write("test_file.txt", "dummy test content")
        content = adapter.read("test_file.txt")
        assert content == "dummy test content"


def test_local_file_adapter_search():
    """LocalFileAdapter can search files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalFileAdapter("test-svc", tmpdir)
        adapter.write("file1.txt", "hello world")
        adapter.write("file2.txt", "goodbye world")
        results = adapter.search("world")
        assert len(results) == 2


def test_local_file_adapter_backup_restore():
    """LocalFileAdapter backup/restore with hash verification (§48)."""
    with tempfile.TemporaryDirectory() as tmpdir, \
         tempfile.TemporaryDirectory() as backup_dir:
        adapter = LocalFileAdapter("test-svc", tmpdir)
        adapter.write("data.txt", "important test data")

        # Backup
        assert adapter.backup(backup_dir)
        assert os.path.isfile(os.path.join(backup_dir, "backup_hash.json"))

        # Delete original and restore
        os.remove(os.path.join(tmpdir, "data.txt"))
        assert not os.path.isfile(os.path.join(tmpdir, "data.txt"))
        assert adapter.restore(backup_dir)
        assert os.path.isfile(os.path.join(tmpdir, "data.txt"))
        assert adapter.read("data.txt") == "important test data"


def test_local_file_adapter_health():
    """LocalFileAdapter health check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalFileAdapter("test-svc", tmpdir)
        h = adapter.health()
        assert h["health"] == "HEALTHY"
        assert h["exists"] is True


def test_adapter_registry():
    """DataServiceAdapterRegistry registers and retrieves adapters (§60)."""
    reg = DataServiceAdapterRegistry()
    with tempfile.TemporaryDirectory() as tmpdir:
        adapter = LocalFileAdapter("svc-1", tmpdir)
        reg.register("svc-1", adapter, [DataClass.FILES.value])
        assert reg.get("svc-1") is not None
        file_adapters = reg.adapters_for_class(DataClass.FILES.value)
        assert len(file_adapters) >= 1


# === Data Policy Engine tests (§61) ===

def test_policy_engine_credentials_broker_only():
    """Credentials policy: BROKER_ONLY (§8, §42)."""
    engine = DataPolicyEngine()
    engine.apply_defaults()

    # Any role accessing credentials -> BROKER_ONLY
    decision = engine.evaluate(DataClass.CREDENTIALS.value,
                               "general_worker", DataAction.READ.value)
    assert decision == AccessDecision.BROKER_ONLY


def test_policy_engine_finance_deny_by_default():
    """Finance policy: DENY by default (§17, §43)."""
    engine = DataPolicyEngine()
    engine.apply_defaults()

    # General worker cannot read finance
    decision = engine.evaluate(DataClass.FINANCE.value,
                               "general_coding_agent", DataAction.READ.value)
    assert decision == AccessDecision.DENY

    # Finance specialist can read (scoped)
    decision = engine.evaluate(DataClass.FINANCE.value,
                               "finance_specialist", DataAction.READ.value)
    assert decision == AccessDecision.READ_SCOPED


def test_policy_engine_identity_no_cloud():
    """Identity/legal/health data denied to cloud (§24, §43)."""
    engine = DataPolicyEngine()
    engine.apply_defaults()

    # Identity data to cloud worker -> DENY
    decision = engine.evaluate(DataClass.IDENTITY.value,
                               "identity_specialist", DataAction.READ.value,
                               location="cloud")
    assert decision == AccessDecision.DENY

    # Identity data local -> READ_SCOPED for identity_specialist
    decision = engine.evaluate(DataClass.IDENTITY.value,
                               "identity_specialist", DataAction.READ.value,
                               location="local")
    assert decision == AccessDecision.READ_SCOPED


def test_policy_engine_files_no_cloud():
    """Raw files denied to cloud (§12)."""
    engine = DataPolicyEngine()
    engine.apply_defaults()

    decision = engine.evaluate(DataClass.FILES.value,
                               "coding_worker", DataAction.READ.value,
                               location="cloud")
    assert decision == AccessDecision.DENY


def test_policy_engine_custom_rule():
    """Custom rules can be added (§61)."""
    engine = DataPolicyEngine()
    engine.add_rule(DataPolicyRule(
        data_class=DataClass.RESEARCH.value,
        role="research_worker",
        action=DataAction.READ.value,
        location="local",
        decision=AccessDecision.READ_SCOPED.value,
        justification="Research workers can read research data locally",
    ))
    decision = engine.evaluate(DataClass.RESEARCH.value,
                               "research_worker", DataAction.READ.value,
                               location="local")
    assert decision == AccessDecision.READ_SCOPED


def test_policy_engine_deny_precedence():
    """DENY takes precedence over other rules (default-deny)."""
    engine = DataPolicyEngine()
    engine.add_rule(DataPolicyRule(
        data_class=DataClass.FINANCE.value,
        role="*",
        action="*",
        location="*",
        decision=AccessDecision.ALLOW.value,
    ))
    engine.add_rule(DataPolicyRule(
        data_class=DataClass.FINANCE.value,
        role="finance_specialist",
        action=DataAction.WRITE.value,
        location="cloud",
        decision=AccessDecision.DENY.value,
        justification="Finance writes never go to cloud",
    ))
    # Finance write to cloud -> DENY
    decision = engine.evaluate(DataClass.FINANCE.value,
                               "finance_specialist", DataAction.WRITE.value,
                               location="cloud")
    assert decision == AccessDecision.DENY


def test_policy_engine_audit_log():
    """Policy decisions are auditable (§13, §16)."""
    engine = DataPolicyEngine()
    engine.apply_defaults()
    engine.evaluate(DataClass.FINANCE.value, "general_worker",
                    DataAction.READ.value)
    engine.evaluate(DataClass.CREDENTIALS.value, "broker",
                    DataAction.READ.value)
    log = engine.decision_log()
    assert len(log) == 2
    for entry in log:
        assert "timestamp" in entry
        assert "data_class" in entry
        assert "role" in entry
        assert "decision" in entry
        assert "justification" in entry


def test_policy_engine_no_secret_in_log():
    """Policy audit log never contains secret values."""
    engine = DataPolicyEngine()
    engine.apply_defaults()
    engine.evaluate(DataClass.CREDENTIALS.value, "test",
                    DataAction.READ.value,
                    project="CRED-SECRET-API-KEY-12345")
    for entry in engine.decision_log():
        assert "CRED-SECRET-API-KEY-12345" not in str(entry)


# === Vault adapter tests (§8) ===

def test_proton_pass_adapter_status():
    """ProtonPassAdapter reports correct status."""
    adapter = ProtonPassAdapter()
    st = adapter.status()
    assert st["adapter_id"] == "proton_pass"
    assert "cli_available" in st
    assert "auth_required" in st
    assert "account_required" in st
    # Proton CLI likely not installed
    assert st["cli_available"] in [True, False]


def test_bitwarden_adapter_status():
    """BitwardenAdapter reports correct status."""
    adapter = BitwardenAdapter()
    st = adapter.status()
    assert st["adapter_id"] == "bitwarden"
    assert "cli_available" in st
    assert "auth_required" in st


def test_vault_adapters_implement_protocol():
    """Vault adapters implement VaultAdapter interface (§2, §8)."""
    proton = ProtonPassAdapter()
    bw = BitwardenAdapter()
    mem = InMemoryVaultAdapter()

    for adapter in [proton, bw, mem]:
        assert hasattr(adapter, "adapter_id")
        assert hasattr(adapter, "status")
        assert hasattr(adapter, "list_metadata")
        assert hasattr(adapter, "read_entry")
        assert hasattr(adapter, "create_entry")
        assert hasattr(adapter, "update_entry")
        assert hasattr(adapter, "lock")


def test_vault_adapters_lock_clears_state():
    """Locking a vault clears sensitive state (§3)."""
    bw = BitwardenAdapter()
    bw.set_session("fake-session-token")
    assert bw.status()["vault_state"] == VAULT_UNLOCKED
    bw.lock()
    assert bw.status()["vault_state"] == VAULT_LOCKED


def test_data_class_enum_complete():
    """DataClass enum has all §34 categories."""
    names = {dc.name for dc in DataClass}
    expected = {
        "CREDENTIALS", "TWO_FACTOR", "EMAIL", "CALENDAR", "CONTACTS",
        "FILES", "DOCUMENTS", "NOTES", "FINANCE", "BUSINESS",
        "SOCIAL", "MESSAGING", "PHOTOS", "VIDEO", "AUDIO",
        "IDENTITY", "LEGAL", "HEALTH", "PROJECTS", "SOURCE_CODE",
        "BACKUPS", "RESEARCH", "OTHER_PERSONAL",
    }
    assert expected.issubset(names)


def test_app_state_enum_complete():
    """AppState enum has all §6 states."""
    values = {s.value for s in AppState}
    expected = {
        "PRIMARY", "SECONDARY", "FALLBACK", "MIRROR",
        "SELF_HOSTED", "DECENTRALISED", "EVALUATION", "OPTIONAL",
        "PAID_DISABLED", "INCOMPATIBLE", "REJECTED", "SUPERSEDED",
        "OWNER_ACTION_REQUIRED", "NOT_INSTALLED", "INSTALLED",
        "CONFIGURED", "VERIFIED",
    }
    assert expected.issubset(values)


def test_source_model_and_type():
    """SourceModel and SourceType have all §5, §6 options."""
    model_values = {s.value for s in SourceModel}
    assert {"local", "hosted", "self_hosted", "federated", "peer_to_peer"}.issubset(model_values)

    type_values = {s.value for s in SourceType}
    assert {"open_source", "source_available", "closed_source"}.issubset(type_values)


if __name__ == "__main__":
    tests = [
        ("test_registry_create_register", test_registry_create_register),
        ("test_registry_state_transitions", test_registry_state_transitions),
        ("test_registry_data_class_index", test_registry_data_class_index),
        ("test_registry_add_credential_ref", test_registry_add_credential_ref),
        ("test_registry_summary_no_secrets", test_registry_summary_no_secrets),
        ("test_default_registry_all_services", test_default_registry_all_services),
        ("test_default_registry_states_accurate", test_default_registry_states_accurate),
        ("test_default_registry_data_classes", test_default_registry_data_classes),
        ("test_registry_export_import", test_registry_export_import),
        ("test_registry_category_index", test_registry_category_index),
        ("test_local_file_adapter_read_write", test_local_file_adapter_read_write),
        ("test_local_file_adapter_search", test_local_file_adapter_search),
        ("test_local_file_adapter_backup_restore", test_local_file_adapter_backup_restore),
        ("test_local_file_adapter_health", test_local_file_adapter_health),
        ("test_adapter_registry", test_adapter_registry),
        ("test_policy_engine_credentials_broker_only", test_policy_engine_credentials_broker_only),
        ("test_policy_engine_finance_deny_by_default", test_policy_engine_finance_deny_by_default),
        ("test_policy_engine_identity_no_cloud", test_policy_engine_identity_no_cloud),
        ("test_policy_engine_files_no_cloud", test_policy_engine_files_no_cloud),
        ("test_policy_engine_custom_rule", test_policy_engine_custom_rule),
        ("test_policy_engine_deny_precedence", test_policy_engine_deny_precedence),
        ("test_policy_engine_audit_log", test_policy_engine_audit_log),
        ("test_policy_engine_no_secret_in_log", test_policy_engine_no_secret_in_log),
        ("test_proton_pass_adapter_status", test_proton_pass_adapter_status),
        ("test_bitwarden_adapter_status", test_bitwarden_adapter_status),
        ("test_vault_adapters_implement_protocol", test_vault_adapters_implement_protocol),
        ("test_vault_adapters_lock_clears_state", test_vault_adapters_lock_clears_state),
        ("test_data_class_enum_complete", test_data_class_enum_complete),
        ("test_app_state_enum_complete", test_app_state_enum_complete),
        ("test_source_model_and_type", test_source_model_and_type),
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
