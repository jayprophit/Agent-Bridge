"""Adapter catalog: cross-device node tools (v0.7).

Local node registry/router/delegation operations. Pairing operations are
approval-gated and remain interface-only where network pairing transport is
not configured: they are registered DISABLED with explicit limitations, never
as available capabilities.
"""
from __future__ import annotations

from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.registry import DISABLED, MUTATING_LOCAL, READ_ONLY, ToolRecord


def node_records() -> list[ToolRecord]:
    ro = {"profiles": list(SAFE_PROFILES), "auto": True}
    out = [
        _rec("node.list", "node", "list", "node.list (local registry)",
             "nodes.node_registry", READ_ONLY, profiles=ro["profiles"],
             auto=ro["auto"], tags=("node", "registry"),
             inschema={"type": "object"}),
        _rec("node.describe", "node", "describe", "node.describe (local registry)",
             "nodes.node_registry", READ_ONLY, profiles=ro["profiles"],
             auto=ro["auto"], tags=("node", "registry"),
             inschema={"type": "object",
                       "properties": {"node_id": {"type": "string"}},
                       "required": ["node_id"]}),
        _rec("node.status", "node", "status", "node.status (local registry)",
             "nodes.node_registry", READ_ONLY, profiles=ro["profiles"],
             auto=ro["auto"], tags=("node", "status"),
             inschema={"type": "object",
                       "properties": {"node_id": {"type": "string"}},
                       "required": ["node_id"]}),
        _rec("node.capabilities", "node", "capabilities",
             "node.capabilities (concise advertisement, no full schemas)",
             "nodes.node_server", READ_ONLY, profiles=ro["profiles"],
             auto=ro["auto"], tags=("node", "capabilities"),
             inschema={"type": "object",
                       "properties": {"node_id": {"type": "string"}},
                       "required": ["node_id"]}),
        _rec("node.route", "node", "route", "node.route (routing preview)",
             "nodes.node_router", READ_ONLY, profiles=ro["profiles"],
             auto=ro["auto"], tags=("node", "routing"),
             inschema={"type": "object"}),
        _rec("node.delegate", "node", "delegate", "node.delegate (approval-gated)",
             "nodes.task_delegator", MUTATING_LOCAL, profiles=list(OWNER_ONLY),
             auto=False, tags=("node", "delegation"),
             inschema={"type": "object",
                       "properties": {"task_id": {"type": "string"}},
                       "required": ["task_id"]}),
        _rec("node.cancel", "node", "cancel", "node.cancel",
             "nodes.task_delegator", MUTATING_LOCAL, profiles=list(SAFE_PROFILES),
             auto=True, tags=("node", "delegation"),
             inschema={"type": "object",
                       "properties": {"delegation_id": {"type": "string"}},
                       "required": ["delegation_id"]}),
    ]
    for tid, desc in (
        ("node.pair.request", "node.pair.request (approval-gated, interface-only)"),
        ("node.pair.approve", "node.pair.approve (owner approval required)"),
        ("node.pair.challenge", "node.pair.challenge (interface-only)"),
        ("node.pair.revoke", "node.pair.revoke (owner approval required)"),
    ):
        out.append(_rec(
            tid, "node", tid.split(".")[-1], desc, "nodes.node_transport",
            MUTATING_LOCAL, status=DISABLED, available=False, installed=False,
            profiles=list(OWNER_ONLY), auto=False, tags=("node", "pairing"),
            inschema={"type": "object"},
            limitations="approval-gated: explicit owner approval required; "
                        "network pairing transport interface-only in v0.7",
        ))
    return out
