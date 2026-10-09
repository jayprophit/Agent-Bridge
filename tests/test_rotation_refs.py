"""Credential rotation reference tests (§36).

The important property here is NEGATIVE: nothing in this module can hold a
secret. Tests assert the absence of values as strictly as they assert
presence of references, because the failure mode that matters is a future
edit quietly turning a placeholder into a stored credential.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.prepare_rotation_refs import (
    ROTATION_PENDING,
    STATUS_MISSING_ROTATION,
    VAULT_BASE_PATH,
    build_rotation_references,
    register_rotation_references,
    rotation_status,
)
from security.credential_broker import CredentialBroker


class RotationReferenceTests(unittest.TestCase):
    """§36 — the five affected providers, in the owner's reference form."""

    def test_all_five_providers_registered(self):
        expected = {"CRED-OPENROUTER-PRIMARY", "CRED-GROQ-PRIMARY",
                    "CRED-GEMINI-PRIMARY", "CRED-HUGGINGFACE-PRIMARY",
                    "CRED-DEEPSEEK-PRIMARY"}
        actual = {r.credential_id for r in build_rotation_references()}
        self.assertEqual(actual, expected)

    def test_every_reference_is_missing_rotation(self):
        for ref in build_rotation_references():
            self.assertEqual(ref.status, STATUS_MISSING_ROTATION)

    def test_references_carry_expected_vault_path(self):
        for ref in build_rotation_references():
            self.assertTrue(ref.vault_entry_path.startswith("Aetherius/Cloud/"))
            self.assertIn(ref.service, ref.vault_entry_path)

    def test_vault_path_template_covers_every_service(self):
        for spec in ROTATION_PENDING:
            self.assertIn("{service}", VAULT_BASE_PATH)
            self.assertIn(spec["service"],
                          VAULT_BASE_PATH.format(service=spec["service"]))

    def test_references_are_read_only(self):
        """Cloud spend must not be something a worker can trigger silently."""
        for ref in build_rotation_references():
            self.assertTrue(ref.permissions.get("read"))
            self.assertFalse(ref.permissions.get("write"))

    def test_no_field_holds_a_secret(self):
        """THE KEY ASSERTION.

        A placeholder that could carry a value would eventually carry one.
        """
        forbidden = ("secret", "value", "password", "token", "api_key",
                     "credential_value")
        for ref in build_rotation_references():
            for attr in dir(ref):
                if attr.startswith("_"):
                    continue
                if any(bad in attr.lower() for bad in forbidden):
                    self.fail(f"CredentialReference exposes '{attr}' — "
                              "references must not carry secret material")

    def test_purpose_explains_exposure(self):
        for ref in build_rotation_references():
            self.assertIn("exposed in chat", ref.purpose)


class BrokerRegistrationTests(unittest.TestCase):
    """Registration must work with no vault adapter and no secrets."""

    def test_registration_succeeds_without_a_vault(self):
        broker = CredentialBroker()
        outcome = register_rotation_references(broker)
        self.assertEqual(len(outcome), 5)
        self.assertTrue(all(v == STATUS_MISSING_ROTATION
                            for v in outcome.values()))

    def test_registered_references_are_retrievable(self):
        broker = CredentialBroker()
        register_rotation_references(broker)
        ref = broker._registry["CRED-OPENROUTER-PRIMARY"]
        self.assertEqual(ref.service, "openrouter")

    def test_broker_status_reports_credentials(self):
        broker = CredentialBroker()
        register_rotation_references(broker)
        status = broker.status()
        self.assertEqual(status["registered_credentials"], 5)
        # No adapter means the vault is locked — a missing credential must not
        # look resolvable.
        self.assertEqual(status["broker_status"], "VAULT_LOCKED")

    def test_status_contains_no_secret_material(self):
        status = rotation_status()
        import json
        rendered = json.dumps(status)
        for marker in ("sk-", "ghp_", "AKIA", "Bearer "):
            self.assertNotIn(marker, rendered)


class RotationStatusReportTests(unittest.TestCase):
    """The evidence report must be honest about the blocker."""

    def test_state_is_blocked_owner(self):
        self.assertEqual(rotation_status()["state"], "BLOCKED_OWNER")

    def test_reason_names_the_exposure(self):
        self.assertIn("exposed", rotation_status()["reason"].lower())

    def test_no_values_populated(self):
        self.assertFalse(rotation_status()["values_populated"])

    def test_master_password_is_human_controlled(self):
        report = rotation_status()["master_password_handling"]
        self.assertIn("never in code", report.lower())

    def test_owner_action_requires_direct_entry(self):
        """Rotation happens in the provider console + KeePass, never in chat."""
        action = rotation_status()["owner_action"].lower()
        self.assertIn("directly into keepass", action)


class NoSecretLeakTests(unittest.TestCase):
    """Guards the module file itself against a hardcoded value."""

    def test_module_source_has_no_credential_like_literals(self):
        import scripts.prepare_rotation_refs as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for marker in ("sk-or-", "sk-", "gsk_", "AIza", "hf_", "xoxb-"):
            self.assertNotIn(marker, src,
                             f"module contains credential-like literal '{marker}'")

    def test_no_personal_paths(self):
        import scripts.prepare_rotation_refs as mod
        src = Path(mod.__file__).read_text(encoding="utf-8")
        self.assertNotIn("C:/Users/", src)
        self.assertNotIn("C:\\\\Users\\\\", src)


if __name__ == "__main__":
    unittest.main()
