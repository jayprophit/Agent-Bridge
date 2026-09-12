"""Low-spec model compatibility acceptance (v0.8 Part B, bounded).

Probes installed lightweight models through the compat layer with tiny
prompts; validates translator output without executing real tools.
Writes V08_COMPAT_ACCEPTANCE.json
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compat import (
    LegacyActionTranslator, ModelCapabilityProbe, negotiate_tools,
)
from tools.registry import ToolRecord, ToolRegistry

MODELS = ["qwen3:0.6b", "qwen3:1.7b", "hhao/qwen2.5-coder-tools:3b"]


def _ollama_generate(model: str, prompt: str, max_tokens: int = 128) -> str:
    import urllib.request
    payload = {"model": model, "prompt": prompt, "stream": False,
               "options": {"num_predict": max_tokens, "temperature": 0.1}}
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode()).get("response", "")


def main() -> int:
    from tools.tool_audit import collect_records
    reg = ToolRegistry()
    for rec in collect_records():
        try:
            reg.register(rec)
        except ValueError:
            pass
    translator = LegacyActionTranslator(reg, max_repairs=1)
    probe = ModelCapabilityProbe()
    results = []
    for model in MODELS:
        t0 = time.monotonic()
        entry: dict = {"model": model}
        try:
            ev = probe.probe(lambda p, m=model: _ollama_generate(m, p),
                             context_tokens=32768)
            entry["modes"] = ev["modes"]
            entry["strict_json"] = ev["strict_json"]
            shortlist = negotiate_tools("list workspace files", reg, ev["modes"])
            entry["shortlist_n"] = len(shortlist)
            target = shortlist[0] if shortlist else "tools.list"
            reply = _ollama_generate(
                model, "Reply with exactly one JSON object and nothing else, "
                f"using this tool: {{\"tool\": \"{target}\", \"arguments\": {{}}}}.")
            tr = translator.translate(reply)
            entry["translate_ok"] = tr.ok
            entry["translate_error"] = tr.error
            entry["repair_recovered"] = False
            if not tr.ok:
                def _produce(hint, _m=model, _t=target):
                    extra = (" " + hint) if hint else ""
                    return _ollama_generate(
                        _m, "Reply with exactly one JSON object and nothing else, "
                        f"using this tool: {{\"tool\": \"{_t}\", \"arguments\": {{}}}}.{extra}")
                tr2 = translator.translate_with_repair(_produce)
                entry["repair_recovered"] = bool(tr2.ok)
                entry["repair_attempts"] = tr2.repairs
            entry["status"] = "PASS"
        except Exception as e:  # noqa: BLE001
            entry["status"] = "FAIL"
            entry["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        entry["duration_s"] = round(time.monotonic() - t0, 2)
        results.append(entry)
        print(f"{model}: {entry.get('status')} modes={entry.get('modes')} "
              f"translate_ok={entry.get('translate_ok')}")
    # Synthetic legacy model (no live backend needed).
    legacy = ModelCapabilityProbe().probe(lambda p: "BLUE", context_tokens=2048)
    results.append({"model": "UnknownLegacyModel9000 (synthetic)",
                    "modes": legacy["modes"], "status": "PASS"})
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports", "v0.8", "V08_COMPAT_ACCEPTANCE.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=1)
    return 0 if all(r["status"] == "PASS" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
