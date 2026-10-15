"""H08 portability & disaster recovery tests (AT-28)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from compute.portability import (
    STATE_CATEGORIES,
    AetheriusStatePackage,
    OffboardingPlan,
    OffboardingStep,
    StateSection,
    scrub_provider_ids,
)


class TestStatePackage:
    def test_export_import_roundtrip(self, tmp_path):
        """Export then import preserves all data with integrity."""
        pkg = AetheriusStatePackage()
        pkg.add_section("canonical_tasks", {"task-1": {"status": "done"}})
        pkg.add_section("agent_ids", {"hermes": {"role": "supervisor"}})

        path = pkg.export(tmp_path / "state.json")
        assert path.exists()

        imported = AetheriusStatePackage.import_package(path)
        assert imported.version == "1.0.0"
        tasks = imported.get_section("canonical_tasks")
        assert tasks is not None
        assert tasks.data["task-1"]["status"] == "done"

    def test_integrity_verification(self):
        """§3: every section has a hash; tampering is detected."""
        sec = StateSection(category="policies", data={"invariant": "B04"})
        assert sec.verify_integrity()
        # Tamper with data
        sec.data["invariant"] = "TAMPERED"
        assert not sec.verify_integrity()

    def test_corrupt_import_rejected(self, tmp_path):
        """§5: corrupt package is rejected, not silently accepted."""
        pkg = AetheriusStatePackage()
        pkg.add_section("policies", {"x": 1})
        path = pkg.export(tmp_path / "state.json")

        # Corrupt the file
        data = json.loads(path.read_text())
        data["sections"]["policies"]["data"]["x"] = 999  # tampered
        path.write_text(json.dumps(data))

        with pytest.raises(ValueError, match="integrity"):
            AetheriusStatePackage.import_package(path)

    def test_unknown_category_rejected(self):
        with pytest.raises(ValueError, match="unknown state category"):
            StateSection(category="not_a_category", data={})

    def test_missing_categories_reported(self):
        """Honest: summary reports what's NOT in the package."""
        pkg = AetheriusStatePackage()
        pkg.add_section("canonical_tasks", {"t1": {}})
        s = pkg.summary()
        assert "agent_ids" in s["missing_categories"]
        assert len(s["missing_categories"]) == len(STATE_CATEGORIES) - 1

    def test_no_credentials_in_export(self):
        """§5: export contains NO plaintext credentials."""
        pkg = AetheriusStatePackage()
        pkg.add_section("provider_metadata", {
            "providers": {"nous": {"model": "solar-pro", "api_mode": "chat"}},
        })
        exported = json.dumps({cat: sec.to_dict()
                               for cat, sec in pkg.sections.items()})
        # Credentials should never appear
        assert "sk-" not in exported
        assert "api_key" not in exported.lower()
        assert "password" not in exported.lower()

    def test_scrub_provider_ids(self):
        """§3: provider-specific IDs are scrubbed from exports."""
        data = {
            "agent_id": "hermes-supervisor",  # Aetherius-owned: keep
            "openai_org_id": "org-abc123",     # provider-specific: drop
            "nested": {
                "provider_session_id": "sess-xyz",  # drop
                "aetherius_task_id": "AB-001",       # keep
            },
        }
        cleaned = scrub_provider_ids(data)
        assert cleaned["agent_id"] == "hermes-supervisor"
        assert "openai_org_id" not in cleaned
        assert "provider_session_id" not in cleaned["nested"]
        assert cleaned["nested"]["aetherius_task_id"] == "AB-001"


class TestOffboardingPlan:
    def test_default_plan_has_all_steps(self):
        """§4: offboarding covers export, disable, revoke, remove, confirm."""
        plan = OffboardingPlan(provider="groq")
        assert len(plan.steps) == 6
        step_ids = [s.step_id for s in plan.steps]
        assert "export-state" in step_ids
        assert "revoke-keys" in step_ids
        assert "remove-resources" in step_ids
        assert "confirm-deletion" in step_ids
        assert "test-restore" in step_ids

    def test_plan_is_not_complete_initially(self):
        plan = OffboardingPlan(provider="openai")
        assert not plan.is_complete()
        assert len(plan.remaining_steps()) == 6

    def test_complete_steps_track_progress(self):
        plan = OffboardingPlan(provider="test-provider")
        plan.complete_step("export-state", evidence="exported 3 sectors")
        plan.complete_step("disable-remote-workers", evidence="2 workers disabled")
        assert len(plan.remaining_steps()) == 4
        assert not plan.is_complete()

        # Complete all
        for s in plan.steps:
            if not s.completed:
                plan.complete_step(s.step_id, evidence="done")
        assert plan.is_complete()

    def test_unknown_step_returns_false(self):
        plan = OffboardingPlan()
        assert plan.complete_step("nonexistent") is False

    def test_reversible_by_default(self):
        """§4: offboarding is REVERSIBLE."""
        plan = OffboardingPlan(provider="test")
        assert all(s.reversible for s in plan.steps)

    def test_summary(self):
        plan = OffboardingPlan(provider="groq")
        plan.complete_step("export-state", "exported")
        s = plan.summary()
        assert s["provider"] == "groq"
        assert s["total_steps"] == 6
        assert s["completed_steps"] == 1
        assert not s["is_complete"]
        assert "revoke-keys" in s["remaining"]
