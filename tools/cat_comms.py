"""Adapter catalog: email/communication tools (v0.8).

Draft generation is local and low-risk (artifact-backed). Sending is an
EXTERNAL side effect: approval-gated, owner-only, and denied without a
configured provider. No credentials live in the tree.
"""
from __future__ import annotations

from tools.cat_core import OWNER_ONLY, SAFE_PROFILES, _rec
from tools.adapter import ToolAdapter
from tools.registry import (
    AVAILABLE, DISABLED, EXTERNAL_ACCOUNT, MUTATING_LOCAL, PROVIDER_REQUIRED,
    READ_ONLY, SAFE_LOCAL, ToolRecord,
)


class EmailAdapter(ToolAdapter):
    """Local email drafts (artifact-backed). Sending stays provider-gated."""

    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "local draft backend present"}

    def validate(self, arguments):
        if not isinstance(arguments, dict):
            return False, "arguments must be an object"
        return True, ""

    def execute(self, arguments, context=None):
        from tools.artifacts import ArtifactRegistry
        import json
        import os
        import tempfile
        import uuid
        sub = self.tool_id.split(".", 1)[1]
        if sub not in ("compose", "draft", "reply"):
            return {"ok": False, "status": PROVIDER_REQUIRED,
                    "error": f"email.{sub} needs a configured provider"}
        workspace = (self.ctx.get("workspace")
                     if isinstance(self.ctx, dict) else "") or \
            os.path.join(tempfile.gettempdir(), "ab_email_drafts")
        os.makedirs(workspace, exist_ok=True)
        draft = {"to": arguments.get("to", ""), "subject": arguments.get("subject", ""),
                 "body": arguments.get("body", ""),
                 "in_reply_to": arguments.get("in_reply_to", "")}
        path = os.path.join(workspace, f"draft-{uuid.uuid4().hex[:8]}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(draft, f, indent=1)
        try:
            artifacts = (self.ctx.get("artifacts")
                         if isinstance(self.ctx, dict) else None)
            ref = artifacts.register(
                "email_draft", path, creator_tool=self.tool_id,
                provenance="local-compose") if artifacts else {"ref": path}
        except Exception:
            ref = {"ref": path}
        return {"ok": True, "draft_ref": ref.get("ref", path)
                if isinstance(ref, dict) else path, "verified": True}


class TelephoneAdapter(ToolAdapter):
    """Local/mock telephony operations (never touches PSTN)."""

    def __init__(self, ctx, tool_id):
        self.ctx = ctx
        self.tool_id = tool_id

    @property
    def _provider(self):
        from comms.telephone import LoopbackCallProvider
        if isinstance(self.ctx, dict):
            return self.ctx.setdefault("telephone_provider", LoopbackCallProvider())
        return LoopbackCallProvider()

    def probe(self):
        return {"available": True, "status": AVAILABLE,
                "reason": "local/mock telephony backend present"}

    def validate(self, arguments):
        return (True, "") if isinstance(arguments, dict) else \
            (False, "arguments must be an object")

    def execute(self, arguments, context=None):
        sub = self.tool_id.split(".", 1)[1]
        provider = self._provider
        if sub == "answer_policy":
            return {"ok": True, "policy": arguments.get("policy", "MANUAL_ANSWER"),
                    "verified": True}
        if sub == "call_state":
            calls = getattr(provider, "calls", {})
            call_id = arguments.get("call_id", "")
            if call_id not in calls:
                return {"ok": False, "error": f"unknown call: {call_id!r}"}
            return {"ok": True, "call_id": call_id,
                    "state": calls[call_id].get("state"), "verified": True}
        if sub == "hangup":
            return provider.hangup(arguments.get("call_id", ""))
        if sub == "transcript":
            return {"ok": True, "transcript": [], "verified": True,
                    "note": "transcripts accrue on call sessions with consent"}
        return {"ok": False, "status": PROVIDER_REQUIRED,
                "error": f"telephone.{sub} needs a configured provider"}


def email_records() -> list[ToolRecord]:
    ro = {"profiles": list(SAFE_PROFILES), "auto": True}
    out = [
        _rec("email.compose", "email", "compose", "email.compose (local draft)",
             "artifacts", SAFE_LOCAL, profiles=ro["profiles"], auto=ro["auto"],
             tags=("email", "draft"),
             inschema={"type": "object",
                       "properties": {"to": {"type": "string"},
                                      "subject": {"type": "string"},
                                      "body": {"type": "string"}}}),
        _rec("email.draft", "email", "draft", "email.draft (local artifact)",
             "artifacts", SAFE_LOCAL, profiles=ro["profiles"], auto=ro["auto"],
             tags=("email", "draft"),
             inschema={"type": "object",
                       "properties": {"to": {"type": "string"},
                                      "subject": {"type": "string"},
                                      "body": {"type": "string"}}}),
        _rec("email.read", "email", "read", "email.read (configured provider)",
             "none", EXTERNAL_ACCOUNT, status=PROVIDER_REQUIRED,
             available=False, installed=False, provider="email provider (unconfigured)",
             tags=("email", "remote"), inschema={"type": "object"},
             needs_install="configured email provider (SMTP/IMAP/OAuth/plugin)"),
        _rec("email.search", "email", "search", "email.search (configured provider)",
             "none", EXTERNAL_ACCOUNT, status=PROVIDER_REQUIRED,
             available=False, installed=False, provider="email provider (unconfigured)",
             tags=("email", "remote"), inschema={"type": "object"},
             needs_install="configured email provider (SMTP/IMAP/OAuth/plugin)"),
        _rec("email.reply", "email", "reply", "email.reply (draft; send is gated)",
             "artifacts", MUTATING_LOCAL, profiles=list(OWNER_ONLY),
             auto=False, tags=("email", "draft"),
             inschema={"type": "object",
                       "properties": {"to": {"type": "string"},
                                      "subject": {"type": "string"},
                                      "body": {"type": "string"},
                                      "in_reply_to": {"type": "string"}}}),
        _rec("email.send", "email", "send",
             "email.send (EXTERNAL side effect; approval required; no credentials in tree)",
             "none", EXTERNAL_ACCOUNT, status=PROVIDER_REQUIRED,
             available=False, installed=False, profiles=list(OWNER_ONLY),
             auto=False, provider="email provider (unconfigured)",
             tags=("email", "send", "external"),
             inschema={"type": "object",
                       "properties": {"draft_ref": {"type": "string"}}},
             needs_install="configured email provider + explicit owner approval",
             limitations="never sends during automated testing without an explicitly "
                         "configured provider"),
    ]
    return out


def telephone_records() -> list[ToolRecord]:
    out = []
    for tid, desc in (
        ("telephone.answer_policy", "telephone answer-policy (local config)"),
        ("telephone.call_state", "telephone call-state query (local)"),
        ("telephone.hangup", "telephone hangup (local/mock provider)"),
        ("telephone.transcript", "telephone transcript artifact (local)"),
    ):
        out.append(_rec(tid, "telephone", tid.split(".")[1], desc,
                        "comms.telephone", READ_ONLY, tags=("telephone", "call"),
                        inschema={"type": "object"}))
    for tid, desc in (
        ("telephone.answer", "telephone answer (policy-gated)"),
        ("telephone.reject", "telephone reject (policy-gated)"),
        ("telephone.call", "telephone outbound call (approval required; PSTN needs provider)"),
    ):
        out.append(_rec(tid, "telephone", tid.split(".")[1], desc + " [interface]",
                        "none", EXTERNAL_ACCOUNT, status=PROVIDER_REQUIRED,
                        available=False, installed=False,
                        provider="telephony provider (unconfigured)",
                        tags=("telephone", "call", "external"),
                        inschema={"type": "object"},
                        needs_install="configured telephony provider (SIP/WebRTC/Twilio-style)"))
    for tid in ("telephone.pairing",):
        out.append(_rec(tid, "telephone", "pairing",
                        tid + " (approval-gated, interface-only)", "none",
                        MUTATING_LOCAL, status=DISABLED, available=False,
                        installed=False, profiles=list(OWNER_ONLY), auto=False,
                        tags=("telephone", "pairing"), inschema={"type": "object"},
                        limitations="approval-gated; no PSTN access in v0.8"))
    return out
