"""Legacy action translator (v0.8). Text -> canonical ToolRouter action.

Constrained parser for models without native tool calls. NEVER executes
arbitrary text as shell commands: output must name a registered tool_id,
arguments must validate, and execution stays with ToolRouter + policy.
Malformed output is repaired a bounded number of times, then fails safe.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_TOOL_LINE = re.compile(r"^\s*tool\s*:\s*([A-Za-z0-9_.-]+)\s*$",
                        re.IGNORECASE | re.MULTILINE)


class TranslationResult:
    def __init__(self, ok: bool, tool_id: str = "", arguments: dict | None = None,
                 error: str = "", repairs: int = 0, raw_excerpt: str = ""):
        self.ok = ok
        self.tool_id = tool_id
        self.arguments = arguments or {}
        self.error = error
        self.repairs = repairs
        self.raw_excerpt = raw_excerpt

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "tool_id": self.tool_id,
                "arguments": self.arguments, "error": self.error,
                "repairs": self.repairs}


class LegacyActionTranslator:
    """Parse model text into a validated (tool_id, arguments) pair."""

    def __init__(self, tool_registry, max_repairs: int = 2):
        self.registry = tool_registry
        self.max_repairs = max_repairs

    def translate(self, text: str) -> TranslationResult:
        """Parse once. Use translate_with_repair() for the bounded loop."""
        candidate = self._extract_candidate(text)
        if candidate is None:
            return TranslationResult(False, error="no action found",
                                     raw_excerpt=text[:200])
        tool_id, arguments = candidate
        try:
            self.registry.get(tool_id)
        except KeyError:
            return TranslationResult(False, error=f"unknown tool: {tool_id!r}",
                                     raw_excerpt=text[:200])
        if not isinstance(arguments, dict):
            return TranslationResult(False, tool_id=tool_id,
                                     error="arguments must be an object",
                                     raw_excerpt=text[:200])
        if tool_id == "finish":
            return TranslationResult(True, tool_id=tool_id, arguments=arguments)
        return TranslationResult(True, tool_id=tool_id, arguments=arguments)

    def translate_with_repair(self, produce_text, context: str = "") -> TranslationResult:
        """Call produce_text() for model text; repair bounded times.

        produce_text(hint) -> str. hint is "" first, then an error hint.
        """
        hint, repairs, last = "", 0, None
        while repairs <= self.max_repairs:
            try:
                text = produce_text(hint)
            except Exception as e:  # noqa: BLE001
                return TranslationResult(False, error=f"model error: {e}")
            last = self.translate(text)
            if last.ok:
                last.repairs = repairs
                return last
            repairs += 1
            hint = (f"Your last reply was not a valid tool action ({last.error}). "
                    f"Reply with exactly one JSON object like "
                    f'{{"tool": "<tool_id>", "arguments": {{...}}}}. {context}').strip()
        last.repairs = self.max_repairs
        return last

    def _extract_candidate(self, text: str) -> tuple[str, dict] | None:
        # 1. Fenced JSON blocks.
        for match in _FENCED_JSON.findall(text):
            try:
                obj = json.loads(match)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
                args = obj.get("arguments", {})
                return obj["tool"], args if isinstance(args, dict) else {}
        # 2. Bare JSON object with a "tool" key.
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
            except ValueError:
                obj = None
            if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
                args = obj.get("arguments", {})
                return obj["tool"], args if isinstance(args, dict) else {}
        # 3. "tool: <id>" line + optional following JSON arguments.
        m = _TOOL_LINE.search(text)
        if m:
            rest = text[m.end():].strip()
            args: dict = {}
            if rest.startswith("{"):
                try:
                    maybe = json.loads(rest)
                    if isinstance(maybe, dict):
                        args = maybe
                except ValueError:
                    pass
            return m.group(1), args
        return None
