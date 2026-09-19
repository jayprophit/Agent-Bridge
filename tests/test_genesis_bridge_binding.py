"""P2-GB: GENESIS <-> AGENT BRIDGE binding v1 pins.

Bridge-side pins are hard assertions. Genesis-side pins resolve the Genesis
repo via AETHERIUS_PROJECTS_ROOT (default ~/Desktop/Projects) and skip when
the checkout is absent (e.g. isolated CI).
"""
import json
import os
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

import protocol  # noqa: E402  (bridge wire protocol, repo root)


def _genesis_root():
    base = os.environ.get("AETHERIUS_PROJECTS_ROOT", "")
    candidates = []
    if base:
        candidates.append(Path(base) / "Genesis")
    candidates.append(Path.home() / "Desktop" / "Projects" / "Genesis")
    for c in candidates:
        if (c / "schemas" / "agent-definition.schema.json").exists():
            return c
    return None


class BindingVersionPins(unittest.TestCase):
    def test_protocol_pin(self):
        self.assertEqual(protocol.PROTOCOL_VERSION, "0.4")

    def test_api_schema_pin(self):
        schema = json.loads(
            (REPO_ROOT / "docs" / "api_schema.json").read_text(
                encoding="utf-8"))
        compat = schema["compat"]
        self.assertEqual(schema["api"], "v1")
        self.assertEqual(compat["protocol"], "0.4")
        self.assertEqual(compat["runtime"], "0.6")
        self.assertEqual(compat["client_sdk"], "0.6")
        self.assertEqual(compat["config_schema"], 2)
        for v in ("0.1", "0.2", "0.3", "0.4"):
            self.assertIn(v, compat["protocol_accepts"])

    def test_execution_states_present(self):
        import execution_contract as ec
        for state in ("RECEIVED", "CONTEXT_RECOVERED", "PLANNED",
                      "READY_TO_EXECUTE", "EXECUTING", "RESULT_CAPTURED",
                      "VERIFYING", "VERIFIED", "FAILED", "REEVALUATING",
                      "CONTINUE_CURRENT_PLAN"):
            self.assertTrue(hasattr(ec, state), state)

    def test_genesis_agent_definition_pin(self):
        root = _genesis_root()
        if root is None:
            self.skipTest("Genesis checkout absent")
        schema = json.loads(
            (root / "schemas" / "agent-definition.schema.json").read_text(
                encoding="utf-8"))
        props = schema["properties"]
        self.assertEqual(props["schemaVersion"], {"const": "1.0"})
        self.assertEqual(props["approvalMode"]["enum"],
                         ["never", "risky_actions", "always"])
        # Envelope fields (request_id … resource_budget) are declared by
        # docs/contracts/GENESIS_AGENT_BRIDGE_v1.md; wire coverage is
        # verified in P5, not against the agent-definition schema.


if __name__ == "__main__":
    unittest.main()
