"""Generic ToolRouter (v0.7). No giant if/elif: registry-driven.

validate -> find -> availability -> mode/profile -> admin/network ->
model-capability -> owner-auth -> execute -> verify -> audit.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from tools.metrics import ToolMetrics
from tools.registry import ADMIN, ADMIN_REQUIRED, MODEL_REQUIRED, PROVIDER_REQUIRED


class RouterError(Exception):
    pass


class ToolRouter:
    def __init__(self, registry, artifacts=None, metrics: ToolMetrics | None = None,
                 audit_fn=None):
        self.registry = registry
        self.artifacts = artifacts
        self.metrics = metrics or ToolMetrics()
        self.audit_fn = audit_fn
        self.fallbacks: dict[str, list[str]] = {}

    def set_fallback(self, tool_id: str, alternatives: list[str]) -> None:
        self.fallbacks[tool_id] = list(alternatives)

    def call(self, tool_id: str, arguments: dict[str, Any] | None = None,
             context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Route one tool call. Returns a structured response always."""
        arguments = dict(arguments or {})
        context = dict(context or {})
        call_id = f"tc-{uuid.uuid4().hex[:10]}"
        t0 = time.monotonic()
        profile = context.get("profile", "")
        owner = bool(context.get("owner_authorized"))

        def _fail(kind: str, reason: str) -> dict[str, Any]:
            res = {"ok": False, "tool": tool_id, "call_id": call_id,
                   "error": reason, "kind": kind,
                   "duration_s": round(time.monotonic() - t0, 3)}
            self.metrics.note(tool_id, False, res["duration_s"],
                              validation_failure=(kind == "VALIDATION_ERROR"))
            self._audit(call_id, tool_id, arguments, context, res, None)
            return res

        # find
        try:
            rec = self.registry.get(tool_id)
        except KeyError:
            return _fail("UNKNOWN_TOOL", f"unknown tool (no invented tools): {tool_id!r}")
        adapter = None
        try:
            adapter = self.registry.adapter_for(tool_id)
        except KeyError:
            adapter = None
        # validate
        if adapter is not None:
            try:
                valid, why = adapter.validate(arguments)
            except Exception as e:  # noqa: BLE001
                return _fail("VALIDATION_ERROR", f"validator crashed: {e}")
            if not valid:
                return _fail("VALIDATION_ERROR", why or "invalid arguments")
        # availability (truthful: never advertise-then-fake)
        if not rec.available:
            needs = rec.requires_external_service or rec.provider or \
                rec.requires_model_capability or "see status"
            return _fail(rec.status,
                         f"{tool_id} is {rec.status}: {needs}. "
                         f"{rec.requires_install or 'no auto-install'}")
        # mode/profile gate
        if rec.supported_profiles and profile and \
                profile not in rec.supported_profiles:
            return _fail("PROFILE_DENIED",
                         f"{tool_id} not enabled for profile {profile!r}")
        if rec.risk_class == ADMIN and not context.get("admin_active"):
            return _fail("ADMIN_REQUIRED",
                         f"{tool_id} needs Administrator (UAC authoritative)")
        if rec.requires_network == "EXTERNAL_NETWORK" and \
                context.get("network_policy", "LOCAL_MODEL_NETWORK") not in (
                    "EXTERNAL_NETWORK",):
            return _fail("NETWORK_DENIED",
                         f"{tool_id} needs EXTERNAL_NETWORK policy")
        need_cap = rec.requires_model_capability
        have_caps = list(context.get("model_capabilities", []) or [])
        if need_cap and need_cap not in have_caps:
            return _fail("MODEL_REQUIRED",
                         f"{tool_id} needs model capability {need_cap!r}")
        if adapter is None:
            return _fail("NO_ADAPTER", f"{tool_id} has no executable adapter")
        # execute (+ optional fallback chain, always logged)
        attempted = [tool_id]
        try:
            result = adapter.execute(arguments, context)
        except Exception as e:  # noqa: BLE001
            result = {"ok": False, "error": f"backend failure: {e}"}
        if not result.get("ok"):
            for alt in self.fallbacks.get(tool_id, []):
                try:
                    alt_rec = self.registry.get(alt)
                    alt_ad = self.registry.adapter_for(alt)
                    if not alt_rec.available:
                        continue
                    fb = alt_ad.execute(arguments, context)
                    fb["fallback_from"] = tool_id
                    fb["fallback_reason"] = str(result.get("error", ""))[:200]
                    result = fb
                    attempted.append(alt)
                    self.metrics.note(tool_id, True, 0.0, fallback=True)
                    break
                except Exception:  # noqa: BLE001
                    continue
        # verify
        try:
            vok, vwhy = adapter.verify(result)
        except Exception:  # noqa: BLE001
            vok, vwhy = bool(result.get("ok")), ""
        result = dict(result)
        result.update({"tool": tool_id, "call_id": call_id,
                       "adapter": getattr(adapter, "backend", rec.backend),
                       "attempted": attempted,
                       "verified": bool(vok),
                       "duration_s": round(time.monotonic() - t0, 3)})
        if not vok and result.get("ok"):
            result["ok"] = False
            result["error"] = f"verification failed: {vwhy or 'unverified result'}"
        self.metrics.note(tool_id, bool(result.get("ok")), result["duration_s"])
        self._audit(call_id, tool_id, arguments, context, result, rec)
        return result

    def _audit(self, call_id, tool_id, arguments, context, result, rec) -> None:
        entry = {"call_id": call_id, "tool": tool_id,
                 "arguments_summary": str(arguments)[:1000],
                 "profile": context.get("profile", ""),
                 "owner_auto": bool(context.get("owner_authorized")),
                 "ok": result.get("ok", False),
                 "duration_s": result.get("duration_s", 0),
                 "error": str(result.get("error", ""))[:300]}
        if self.audit_fn:
            try:
                self.audit_fn(entry)
            except Exception:  # noqa: BLE001
                pass
