#!/usr/bin/env python3
"""PASS 2 domain-batch enrichment (939 NEW_DOMAIN records).

Reuses the verified project pipeline's machinery (minimal-span anchoring,
utterance typing, topic-pattern register links, repo evidence) and adds
DOMAIN -> COMPONENT -> PROJECT -> REPOSITORY routing per capability
boundaries. DOMAIN != PROJECT != REPOSITORY: project/repo assignment only
on evidence, otherwise staged empty. Threshold 0.90 + strong evidence for
AUTO_VERIFIED; nothing below merges.

Writes only to pass_2_context_enrichment/ (PASS_2_DOMAIN_*). Never touches
Pass-1, project Pass-2 outputs, staged routing, or canonical registries.
"""
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import output_locations as _ol  # noqa: F401  (guard registration side-effect free)
import pass2_context_enrichment as p2

BASE = p2.BASE
OUT = BASE / "pass_2_context_enrichment"
NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

DOMAIN_ORDER = ["AI", "DATA", "ENGINEERING", "SECURITY", "OFFICE"]
EXISTING_PROJECTS = ["GENESIS", "AGENT_BRIDGE", "IDE_WORKSPACE", "MAT",
                     "UNIVERSAL_BRIDGE", "POIETEK", "ATHENA", "AETHERIUS_OS"]
IMPERATIVE_RE = re.compile(r"\b(build|create|add|implement|fix|make|design|develop|deploy|write)\b", re.I)

import json as _json


def load_pass1_domain():
    log = _json.load(open(BASE / "pass_1_fragment_classification" /
                          "UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json", encoding="utf-8"))["records"]
    return [r for r in log if r.get("NEW_DOMAIN")]


def utterance_subtype(utype, frag):
    if utype == "OWNER_PROMPT":
        if p2.INTERROG_RE.search((frag or "").strip()):
            return "OWNER_QUESTION"
        if IMPERATIVE_RE.search(frag or ""):
            return "OWNER_DIRECTIVE"
        return "OWNER_PROMPT_OTHER"
    return utype  # ASSISTANT_REASONING / ASSISTANT_ANSWER / CONTEXT_MISSING


def component_project_repo(rec, domain, utype, win, frag):
    """DOMAIN -> COMPONENT -> PROJECT -> REPOSITORY. PROJECT assigns only on
    item-specific evidence (explicit project mention in fragment/window, or a
    shared-component mapping). Repo keyword affinity is fragment-independent
    (a property of project x domain, not of the item) so it is reported as
    context only and never assigns routing or confidence. Returns
    (component, project, repo, notes, explicit_mention)."""
    notes = []
    shared = rec.get("NEW_SHARED_COMPONENT") or []
    if shared:
        comp = shared[0]
        notes.append(f"shared-foundation component {comp}; project/repo per threshold policy")
        return comp, "", "", notes, False
    text = f"{frag}\n{win or ''}".lower()
    mentioned = ""
    for proj, aliases in p2.PROJECT_DISPLAY.items():
        if any(a in text for a in aliases if len(a.strip()) > 3):
            mentioned = proj
            break
    affinity = []
    for proj in EXISTING_PROJECTS:
        if proj == "ATHENA":
            continue
        ev = p2.repo_evidence(proj, domain)
        if isinstance(ev.get("hits"), int) and ev["hits"] >= 3:
            affinity.append(f"{proj}:{ev['hits']}files")
    if affinity:
        notes.append(f"repo-affinity context only (not routing): {', '.join(affinity[:4])}")
    if mentioned:
        notes.append(f"explicit project mention in item context: {mentioned}")
        return f"{domain}_CAPABILITY_VIA_{mentioned}", mentioned, "", notes, True
    notes.append("no component/project evidence; staged at domain level")
    return f"FUTURE_{domain}_CAPABILITY", "", "", notes, False


def main():
    import importlib.util
    items = load_pass1_domain()
    print(f"domain queue n={len(items)}")
    order = {d: i for i, d in enumerate(DOMAIN_ORDER)}
    items.sort(key=lambda r: (order.get(r["NEW_DOMAIN"], 99), r["NEW_DOMAIN"], r["SHA256_ID"]))

    idx, _ = p2.load_records()
    id_index = p2.build_id_index([
        ("DECISION_LEDGER", p2._load_py("d2", p2.AB / "DECISION_LEDGER.json").KEY_DECISIONS),
        ("SUPERSESSION_REGISTER", p2._load_py("s2", p2.AB / "SUPERSESSION_REGISTER.json").SUPERSESSION_CHAINS),
        ("CONTRADICTION_REGISTER", p2._load_py("c2", p2.AB / "CONTRADICTION_REGISTER.json").CONTRADICTIONS)])

    enriched = []
    for rec in items:
        domain = rec["NEW_DOMAIN"]
        frag = rec["RAW_TEXT"]
        filename = rec.get("SOURCE_DOCUMENT", "") or ""
        model = p2.model_from_filename(filename, (rec.get("SOURCE_LOCATION", "") or "deepseek").lower())
        text = p2.read_source(model, filename) if filename else "__NO_FILENAME__"
        pos, how = (-1, "MISSING") if text.startswith("__") else p2.locate(text, frag)
        utype, win = p2.utterance_type(model, text, pos, frag)
        win_red = p2.redact(win)[:2600] if win else ""
        usub = utterance_subtype(utype, frag)
        links = p2.register_links(frag + "\n" + win_red, id_index) if win else []
        for L in links:
            L["shared_terms"] = []
        sup_live = [L for L in links if L["register"] == "SUPERSESSION_REGISTER" and L["live"]]
        con_live = [L for L in links if L["register"] == "CONTRADICTION_REGISTER" and L["live"]]
        active_links = [L for L in links if L["register"] == "DECISION_LEDGER" and L["live"]]
        rec_info = idx.get((model, filename.lower()), {})
        siblings = [s for s in rec_info.get("requirements", [])
                    if len(p2.content_tokens(s.get("text", "")) & p2.content_tokens(frag)) >= 2]
        tie = "tie" in rec.get("CLASSIFICATION_REASONING", "").lower()

        comp, proj, repo, notes, explicit_proj = component_project_repo(
            rec, domain, utype, win_red, frag)
        ev_for, ev_against, strong = [], [], False
        base = rec["CLASSIFICATION_CONFIDENCE"]
        disp = [a for a in p2.PROJECT_DISPLAY.get(domain, [])]
        if active_links:
            ev_for.append(f"+0.10 ACTIVE decision link {active_links[0]['id']}"); base += 0.10; strong = True
        if len(siblings) >= 2:
            ev_for.append(f"+0.15 {len(siblings)} same-topic siblings"); base += 0.15
        if proj and explicit_proj:
            ev_for.append(f"+0.10 explicit project mention in item context: {proj}"); base += 0.10
        if usub == "OWNER_DIRECTIVE":
            ev_for.append("+0.20 owner directive utterance"); base += 0.20; strong = True
        elif usub == "OWNER_QUESTION":
            ev_against.append("-0.10 owner question, approval unknown"); base -= 0.10
        if utype == "ASSISTANT_REASONING":
            ev_against.append("-0.30 assistant-reasoning provenance"); base -= 0.30
        if tie:
            ev_against.append("-0.20 multiple plausible domains"); base -= 0.20
        if p2.PRONOUN_RE.search(frag) and not any(a in frag.lower() for a in disp):
            if not any(a in win_red.lower() for a in disp if len(a.strip()) > 3):
                ev_against.append("-0.20 pronoun/core-noun unresolved"); base -= 0.20
        if utype.startswith("ASSISTANT") and not rec_info.get("decisions"):
            ev_against.append("-0.15 AI-only, no owner decision in record"); base -= 0.15
        if sup_live or con_live:
            ev_against.append("-0.25 live register signal"); base -= 0.25
        conf = round(max(0.05, min(0.95, base)), 3)

        if sup_live:
            state = "SUPERSEDED"
        elif utype == "ASSISTANT_REASONING" and not strong and not active_links:
            state = "NON_ACTIONABLE"
        elif con_live:
            state = "CONFLICTED"
        elif conf >= 0.90 and strong:
            state = "AUTO_VERIFIED"
        elif conf >= 0.80:
            state = "HIGH_CONFIDENCE_STAGED"
        elif conf >= 0.50 or utype == "OWNER_PROMPT":
            state = "AMBIGUOUS"
        else:
            state = "NON_ACTIONABLE" if utype.startswith("ASSISTANT") else "AMBIGUOUS"

        out = dict(rec)
        out.update({"PASS": "PASS_2_DOMAIN_ENRICHMENT", "RESOLVED_REQUIREMENT": frag,
                    "UTTERANCE_SUBTYPE": usub,
                    "RESOLUTION_EVIDENCE": {"utterance_type": utype, "locate_method": how,
                                            "record_decisions": len(rec_info.get("decisions", [])),
                                            "sibling_support": len(siblings),
                                            "fragment_located": pos >= 0,
                                            "model_source": "FILENAME_PREFIX"},
                    "CONTEXT_WINDOW": win_red, "EVIDENCE_FOR": ev_for,
                    "EVIDENCE_AGAINST": ev_against, "PASS1_CONFIDENCE": rec["CLASSIFICATION_CONFIDENCE"],
                    "ENRICHED_CONFIDENCE": conf, "STRONG_EVIDENCE": strong,
                    "REGISTER_LINKS": links, "COMPONENT_ROUTED": comp,
                    "PROJECT_ROUTED": proj, "REPOSITORY_ROUTED": repo,
                    "ROUTING_NOTES": notes, "IMPLEMENTABLE": state == "AUTO_VERIFIED",
                    "ACCEPTANCE_STATE": state,
                    "OWNER_REVIEW_REQUIRED_P2": state == "CONFLICTED" or (state == "AMBIGUOUS" and conf >= 0.80),
                    "ENRICHED_DATE": NOW})
        enriched.append(out)

    by_state = Counter(e["ACCEPTANCE_STATE"] for e in enriched)
    _json.dump({"generated_at": NOW, "count": len(enriched), "records": enriched},
               open(OUT / "PASS_2_DOMAIN_LOG.json", "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    per_domain = defaultdict(Counter)
    for e in enriched:
        d = e["NEW_DOMAIN"]
        s = e["ACCEPTANCE_STATE"]
        per_domain[d]["INPUT"] += 1
        per_domain[d]["SOURCE_LOCATED"] += 1 if e["RESOLUTION_EVIDENCE"]["fragment_located"] else 0
        per_domain[d]["OWNER_DIRECTIVE"] += 1 if e["UTTERANCE_SUBTYPE"] == "OWNER_DIRECTIVE" else 0
        per_domain[d]["OWNER_QUESTION"] += 1 if e["UTTERANCE_SUBTYPE"] == "OWNER_QUESTION" else 0
        per_domain[d]["ASSISTANT_REASONING"] += 1 if e["RESOLUTION_EVIDENCE"]["utterance_type"] == "ASSISTANT_REASONING" else 0
        per_domain[d][s] += 1
        per_domain[d]["OWNER_REVIEW_REQUIRED"] += 1 if e["OWNER_REVIEW_REQUIRED_P2"] else 0
        per_domain[d]["PROJECT_ROUTED"] += 1 if e["PROJECT_ROUTED"] else 0
        per_domain[d]["COMPONENT_ROUTED"] += 1 if e["COMPONENT_ROUTED"] else 0
        per_domain[d]["REPOSITORY_ROUTED"] += 1 if e["REPOSITORY_ROUTED"] else 0
        per_domain[d]["IMPLEMENTABLE"] += 1 if e["IMPLEMENTABLE"] else 0
    status = {d: dict(c) for d, c in per_domain.items()}
    _json.dump({"generated_at": NOW, "domains": status},
               open(OUT / "PASS_2_DOMAIN_STATUS.json", "w", encoding="utf-8"), indent=1)

    owner_q = sum(1 for e in enriched if e["OWNER_REVIEW_REQUIRED_P2"])
    rep = ["# PASS 2 Domain-Enrichment Report", "", f"Generated: {NOW}",
           f"Input: 939 NEW_DOMAIN records (verified current count; historical 1,032 superseded)", "",
           "## Overall states"]
    for s, c in by_state.most_common():
        rep.append(f"- {s}: {c}")
    rep += [f"", f"OWNER_REVIEW_REQUIRED: {owner_q}",
            f"AUTO_VERIFIED (merged): {by_state.get('AUTO_VERIFIED', 0)}",
            f"IMPLEMENTABLE: {sum(1 for e in enriched if e['IMPLEMENTABLE'])}", "",
            "## Per-domain status"]
    for d in sorted(status, key=lambda x: (order.get(x, 99), x)):
        c = status[d]
        rep.append(f"### {d} (INPUT {c.get('INPUT', 0)})")
        for k in ["SOURCE_LOCATED", "OWNER_DIRECTIVE", "OWNER_QUESTION", "ASSISTANT_REASONING",
                  "AUTO_VERIFIED", "HIGH_CONFIDENCE_STAGED", "AMBIGUOUS", "CONFLICTED",
                  "SUPERSEDED", "NON_ACTIONABLE", "OWNER_REVIEW_REQUIRED",
                  "PROJECT_ROUTED", "COMPONENT_ROUTED", "REPOSITORY_ROUTED", "IMPLEMENTABLE"]:
            if c.get(k):
                rep.append(f"- {k}: {c[k]}")
    (OUT / "PASS_2_DOMAIN_REPORT.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("states:", dict(by_state), "owner_review:", owner_q)


if __name__ == "__main__":
    main()
