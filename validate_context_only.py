#!/usr/bin/env python3
"""Section 14: stratified validation of Pass-1 CONTEXT_ONLY classifications.

Samples 60 CONTEXT_ONLY items across model x record doc_type, re-examines
each in source context (Pass-2 utterance typing), and records accuracy.
A high false-negative rate would trigger full enrichment of CONTEXT_ONLY;
a strong accuracy leaves them non-actionable.
"""
import importlib.util
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from output_locations import area as _area, assert_not_desktop as _guard

BASE = _area("CONVERSATION_ANALYSIS")
_guard(BASE)  # programme outputs must not target the Desktop
OUT = BASE / "pass_2_context_enrichment"
NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

spec = importlib.util.spec_from_file_location(
    "p2", str(Path(__file__).resolve().parent / "pass2_context_enrichment.py"))
p2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p2)

log = json.load(open(BASE / "pass_1_fragment_classification" /
                     "UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json", encoding="utf-8"))["records"]
pool = [r for r in log if r["CLASSIFICATION"] == "CONTEXT_ONLY"]
print(f"CONTEXT_ONLY pool: {len(pool)}")

idx, _ = p2.load_records()

strata = defaultdict(list)
for r in pool:
    fn = r.get("SOURCE_DOCUMENT", "") or ""
    model = p2.model_from_filename(fn, "deepseek")
    rec = idx.get((model, fn.lower()), {})
    strata[(model, rec.get("doc_type", "?"))].append(r)

# Proportional allocation, min 2 per stratum, total 60, deterministic order.
sample = []
quota = {k: max(2, round(60 * len(v) / len(pool))) for k, v in strata.items()}
scale = 60 / sum(quota.values())
for key in sorted(strata):
    members = sorted(strata[key], key=lambda r: r["SHA256_ID"])
    n = max(1, round(quota[key] * scale))
    step = max(1, len(members) / n)
    i = 0
    while len([s for s in sample if s[0] == key]) < n and i < len(members):
        sample.append((key, members[int(i)]))
        i += step
sample = sample[:60]
print(f"strata: {len(strata)}, sampled: {len(sample)}")

results, correct = [], 0
for (model, doc_type), r in sample:
    fn = r.get("SOURCE_DOCUMENT", "") or ""
    text = p2.read_source(model, fn) if fn else "__NO_FILENAME__"
    if text.startswith("__"):
        verdict, utype, reason = "UNVERIFIABLE", "CONTEXT_MISSING", "source unreadable"
    else:
        pos, how = p2.locate(text, r["RAW_TEXT"])
        utype, win = p2.utterance_type(model, text, pos, r["RAW_TEXT"])
        # Same bar as the main pipeline: a routing verb alone is assistant
        # prose ("you can use X for Y"); it counts only with a project name.
        aliases = [a for names in p2.PROJECT_DISPLAY.values() for a in names]
        proj_mentioned = bool(win) and any(a in win.lower() for a in aliases if len(a.strip()) > 3)
        has_owner_signal = (utype == "OWNER_PROMPT" or
                            (bool(win) and p2.OWNER_VERBS.search(win) and proj_mentioned))
        if utype == "CONTEXT_MISSING":
            verdict, reason = "UNVERIFIABLE", "fragment not locatable"
        elif has_owner_signal:
            verdict, reason = "FALSE_NEGATIVE", f"owner signal present ({utype})"
        else:
            # Assistant reasoning AND assistant answers are both non-owner
            # content; without owner signals the item is correctly non-actionable.
            verdict, reason = "CORRECT", f"assistant-side text ({utype}), no owner signal"
    if verdict == "CORRECT":
        correct += 1
    results.append({"capability": r["SHA256_ID"], "model": model, "doc_type": doc_type,
                    "utterance": utype, "verdict": verdict, "reason": reason,
                    "fragment": r["RAW_TEXT"][:160]})

verifiable = [x for x in results if x["verdict"] != "UNVERIFIABLE"]
acc = correct / len(verifiable) if verifiable else 0.0
fnr = 1 - acc
print(f"accuracy={acc:.2%} over {len(verifiable)} verifiable "
      f"({len(results) - len(verifiable)} unverifiable); false-negative rate={fnr:.2%}")

(OUT / "CONTEXT_ONLY_VALIDATION.json").write_text(json.dumps(
    {"generated_at": NOW, "pool": len(pool), "sampled": len(sample),
     "verifiable": len(verifiable), "correct": correct, "accuracy": round(acc, 4),
     "false_negative_rate": round(fnr, 4),
     "decision": ("ENRICH_CONTEXT_ONLY" if fnr > 0.10
                  else "LEAVE_NON_ACTIONABLE"),
     "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
print("wrote CONTEXT_ONLY_VALIDATION.json")
