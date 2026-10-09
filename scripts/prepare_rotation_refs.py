"""Prepare cloud credential rotation references (§36).

WHY THESE EXIST AS PLACEHOLDERS

The five cloud providers below had credentials exposed through chat. Those
values are permanently compromised and must never be reused (§3, §6).

Registering the references NOW, before the replacement secrets exist, means:

  * the wiring is proven while nothing secret is present;
  * when Jonathan rotates a credential he enters it directly into KeePass and
    the reference starts working with no code change;
  * every cloud provider reports an honest MISSING_ROTATION instead of
    silently appearing usable.

NO VALUES ARE POPULATED. There is deliberately no field here that could hold
a secret — this module declares references and their intended vault paths
only. The master password stays human-controlled (§35).
"""

from __future__ import annotations

import sys
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from security.credential_broker import CredentialBroker, CredentialReference

# §36 — the five affected providers, in the reference form the owner specified.
ROTATION_PENDING: list[dict] = [
    {
        "credential_id": "CRED-OPENROUTER-PRIMARY",
        "service": "openrouter",
        "account_label": "jayprophit / primary",
        "purpose": "Free-tier cloud inference provider (was exposed in chat)",
    },
    {
        "credential_id": "CRED-GROQ-PRIMARY",
        "service": "groq",
        "account_label": "jayprophit / primary",
        "purpose": "Free-tier cloud inference provider (was exposed in chat)",
    },
    {
        "credential_id": "CRED-GEMINI-PRIMARY",
        "service": "gemini",
        "account_label": "jayprophit / primary",
        "purpose": "Free-tier cloud inference provider (was exposed in chat)",
    },
    {
        "credential_id": "CRED-HUGGINGFACE-PRIMARY",
        "service": "huggingface",
        "account_label": "jayprophit / primary",
        "purpose": "Model hub / inference access (was exposed in chat)",
    },
    {
        "credential_id": "CRED-DEEPSEEK-PRIMARY",
        "service": "deepseek",
        "account_label": "jayprophit / primary",
        "purpose": "Cloud inference provider (was exposed in chat)",
    },
]

STATUS_MISSING_ROTATION = "MISSING_ROTATION"

# Vault path these entries are expected to occupy once rotated. Recording the
# intended path now means the KeePass structure is agreed before the owner has
# to invent one under time pressure.
VAULT_BASE_PATH = "Aetherius/Cloud/{service}/primary"


def build_rotation_references() -> list[CredentialReference]:
    """Construct the five references. No secret values exist to attach."""
    refs = []
    for spec in ROTATION_PENDING:
        refs.append(CredentialReference(
            credential_id=spec["credential_id"],
            service=spec["service"],
            account_label=spec["account_label"],
            vault_entry_path=VAULT_BASE_PATH.format(service=spec["service"]),
            purpose=spec["purpose"],
            projects=["aetherius-os", "agent-bridge", "hybrid-cloud"],
            # Read-only until the owner confirms a rotated key; cloud spend is
            # not something a worker should be able to incur silently.
            permissions={"read": True, "write": False},
            status=STATUS_MISSING_ROTATION,
        ))
    return refs


def register_rotation_references(
        broker: CredentialBroker) -> dict[str, str]:
    """Register the references on a broker. Returns id -> status."""
    outcome: dict[str, str] = {}
    for ref in build_rotation_references():
        broker.register_credential(ref)
        outcome[ref.credential_id] = ref.status
    return outcome


def rotation_status() -> dict:
    """A report suitable for evidence: what is pending, and why."""
    return OrderedDict([
        ("state", "BLOCKED_OWNER"),
        ("reason", "Credentials were exposed through chat and must not be reused."),
        ("owner_action", "Rotate each provider key in the provider console, then "
                         "enter the new value directly into KeePass."),
        ("expected_vault_paths", {
            spec["service"]: VAULT_BASE_PATH.format(service=spec["service"])
            for spec in ROTATION_PENDING}),
        ("pending", [spec["credential_id"] for spec in ROTATION_PENDING]),
        ("values_populated", False),
        ("master_password_handling", "Human-controlled; never in code, chat, or logs."),
    ])


def main() -> int:
    broker = CredentialBroker()
    outcome = register_rotation_references(broker)
    print("Registered rotation-pending credential references (§36):")
    for cred_id, status in outcome.items():
        print(f"  {cred_id:32s} {status}")
    print()
    print("No secret values were populated. Cloud execution remains BLOCKED_OWNER.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
