#!/usr/bin/env python3
"""PASS 2 — context-enriched reconciliation (PASS_2_CONTEXT_ENRICHMENT).

Enriches Pass-1 project-routed fragments with source-conversation context:
record-level signals (analysis records), window-level utterance typing
(OWNER_PROMPT vs ASSISTANT_REASONING/ANSWER), register cross-references
(decision/supersession/contradiction), and repository file-level evidence.

Safe: reads Pass-1 outputs + corpus; writes only to pass_2_context_enrichment/.
Never overwrites Pass-1, staged routing, or canonical registry files.
"""
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from output_locations import area as _area, assert_not_desktop as _guard

BASE = _area("CONVERSATION_ANALYSIS")
_guard(BASE)  # programme outputs must not target the Desktop
PASS1_LOG = BASE / "pass_1_fragment_classification" / "UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json"
OUT = BASE / "pass_2_context_enrichment"
OUT.mkdir(exist_ok=True)
ANALYSIS_DIRS = {"deepseek": BASE / "deepseek_analysis",
                 "chatgpt": BASE / "chatgpt_analysis",
                 "claude": BASE / "claude_analysis"}
CORPUS_DIRS = {"deepseek": Path("E:/external drive/ai chat conversations/deepseek"),
               "chatgpt": Path("E:/external drive/ai chat conversations/chatgpt"),
               "claude": Path("E:/external drive/ai chat conversations/claude")}
NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
AB = Path(__file__).resolve().parent
# Canonical project repos live on the Desktop per owner directive; resolve via
# home directory so no personal absolute path is hardcoded.
_DESK = Path.home() / "Desktop"


def _load_py(name, path):
    # .json-suffixed Python modules need an explicit source loader.
    from importlib.machinery import SourceFileLoader
    loader = SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


reconciler = _load_py("reconciler_p2", AB / "reconcile_unknown_requirements.py")
KW_MATCHERS = reconciler.KW_MATCHERS

PROJECT_DISPLAY = {"GENESIS": ["genesis"], "AGENT_BRIDGE": ["agent bridge"],
                   "IDE_WORKSPACE": ["aetherius ide", "ide workspace", "workspace"],
                   "MAT": ["materials atlas", "atlas table", "mat "],
                   "UNIVERSAL_BRIDGE": ["universal bridge"],
                   "POIETEK": ["poietek"], "ATHENA": ["athena", "atheena"],
                   "AETHERIUS_OS": ["aetherius os"]}
PROJECT_DIRS = {"GENESIS": _DESK / "Genesis",
                "AGENT_BRIDGE": AB,
                "IDE_WORKSPACE": _DESK / "IDE-Workspace",
                "MAT": _DESK / "Materials-Atlas-Table-Codex---MAT",
                "UNIVERSAL_BRIDGE": _DESK / "Universal-Bridge",
                   "POIETEK": _DESK / "Poietek",
                   "ATHENA": None,
                "AETHERIUS_OS": _DESK / "Aetherius-OS"}

REASONING_RES = [re.compile(p, re.I) for p in
                 [r"^hmm[,!]", r"^read \d+ web pages",
                  r"the user (is asking|previously asked|wants|needs|is looking|is trying|'s question)",
                  r"\bi (need to|will|could|should|would|shall) (provide|reference|organize|use|start|begin|focus|structure)",
                  r"\bi can see\b", r"\bsearch results\b"]]
OWNER_VERBS = re.compile(r"\b(belongs? in|should go in|put .* in|use \w+ for|must be in|assign .* to)\b", re.I)
PRONOUN_RE = re.compile(r"\b(it|this|that|they|them)\b", re.I)
INTERROG_RE = re.compile(r"\?\s*$|^(what|how|why|when|which|who|where|can|should|is|are|do|does)\b", re.I)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PASSWORD_RE = re.compile(r"password\s*[:=*]?\s*[\"']?\S+", re.I)
STOP = set("the and for with that this from have were will would there their what when which while about into over after also your youre they them then than such only just can could should shall may might must will these those".split())


def redact(s):
    s = EMAIL_RE.sub("[REDACTED-EMAIL]", s)
    return PASSWORD_RE.sub("password: [REDACTED]", s)


def content_tokens(s):
    return {t for t in re.findall(r"[a-z]{5,}", s.lower()) if t not in STOP}


def load_records():
    idx, cat_dist = {}, Counter()
    for model, d in ANALYSIS_DIRS.items():
        for f in sorted(d.glob("*_record_*.json")):
            try:
                r = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
            fn = (r.get("filename") or "").lower()
            if fn:
                idx[(model, fn)] = r
                cat_dist[(model, r.get("owner_statement_category", "?"))] += 1
    return idx, cat_dist


_file_cache = {}


def read_source(model, filename):
    key = (model, filename)
    if key not in _file_cache:
        p = CORPUS_DIRS[model] / filename
        try:
            _file_cache[key] = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            _file_cache[key] = f"__UNREADABLE__: {e}"
    return _file_cache[key]


def first_block_end(text):
    m = re.search(r"\n\s*\n", text)
    return m.start() if m else min(600, len(text))


def model_from_filename(filename, fallback="deepseek"):
    """Ground-truth corpus from filename prefix (BUG-002: stored model labels
    were hardcoded deepseek for chatgpt/claude items before 2026-09-16)."""
    f = (filename or "").lower()
    if f.startswith("chatgpt -") or f.startswith("chatgpt_"):
        return "chatgpt"
    if f.startswith("claude -") or f.startswith("claude_"):
        return "claude"
    if f.startswith("deepseek") or f.startswith("deeseek"):
        return "deepseek"
    return fallback if fallback in CORPUS_DIRS else "deepseek"


def locate(text, fragment):
    """Minimal-span ordered distinctive-token anchoring on raw-lowercased text.
    Greedy first-match anchoring fails on long repetitive documents (first
    'specific' + next 'hardware' may be unrelated occurrences 4k chars apart),
    so every tok[0] occurrence is tried and the tightest span wins. Returned
    offsets are valid raw coordinates for windowing and first-block tests."""
    import bisect
    raw = text.lower()
    toks = [t for t in re.findall(r"[a-z0-9]{6,}", fragment.lower()) if t not in STOP][:6]
    if len(toks) == 1 and len(toks[0]) >= 12:
        # Single very distinctive token (e.g. interoperability): first occurrence
        # is topically indicative but positionally weaker.
        i = raw.find(toks[0])
        return (i, "SINGLE_DISTINCTIVE") if i >= 0 else (-1, "MISSING")
    if len(toks) < 2:
        return -1, "MISSING"
    occ = []
    for t in toks:
        lst, s = [], 0
        while len(lst) < 300:
            i = raw.find(t, s)
            if i < 0:
                break
            lst.append(i)
            s = i + 1
        if not lst:
            return -1, "MISSING"
        occ.append(lst)
    best = None
    for p0 in occ[0]:
        prev, last, ok = p0, p0, True
        for lst in occ[1:]:
            j = bisect.bisect_left(lst, prev)
            if j >= len(lst):
                ok = False
                break
            last = lst[j]
            prev = last
        if ok:
            span = last - p0
            if best is None or span < best[0]:
                best = (span, p0)
                if span <= len(fragment):
                    break
    if best is None or best[0] > 600:
        return -1, "MISSING"
    span, p0 = best
    return p0, ("EXACT" if span <= len(fragment) + 100 else "FUZZY_SPAN")


def window(text, char_pos, frag_len_chars=200, span=1200):
    start = max(0, char_pos - span)
    end = min(len(text), char_pos + frag_len_chars + span)
    # Snap to paragraph boundaries.
    ps = text.rfind("\n\n", 0, start + 2)
    start = ps + 2 if ps != -1 else start
    pe = text.find("\n\n", end)
    end = pe if pe != -1 else end
    return text[start:end]


def utterance_type(model, text, frag_pos, frag):
    if frag_pos < 0:
        return "CONTEXT_MISSING", ""
    w = window(text, frag_pos)
    if model in ("chatgpt", "claude") and frag_pos < first_block_end(text):
        return "OWNER_PROMPT", w
    if any(p.search(w) for p in REASONING_RES):
        return "ASSISTANT_REASONING", w
    if model == "deepseek":
        return "ASSISTANT_ANSWER", w
    return "ASSISTANT_ANSWER", w


_repo_cache = {}


def repo_evidence(project, target):
    if project in _repo_cache:
        return _repo_cache[project]
    d = PROJECT_DIRS.get(project)
    if d is None:
        return _repo_cache.setdefault(project, {"files": [], "hits": 0, "note": "NO_LOCAL_DIR"})
    if not d.exists():
        return _repo_cache.setdefault(project, {"files": [], "hits": 0, "note": "DIR_MISSING"})
    matchers = KW_MATCHERS.get(target, []) + KW_MATCHERS.get(project, [])
    hits = []
    n = 0
    for p in sorted(d.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".py", ".md", ".json", ".cpp", ".hpp", ".txt"):
            continue
        try:
            if p.stat().st_size > 200_000:
                continue
        except OSError:
            continue
        n += 1
        if n > 300:
            break
        try:
            t = p.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if any(pat.search(t) for _, pat in matchers):
            hits.append(str(p.relative_to(d)))
            if len(hits) >= 10:
                pass
    ev = {"files": hits[:5], "hits": len(hits), "files_scanned": n, "note": "FILE_LEVEL_GREP"}
    _repo_cache[project] = ev
    return ev


# Precise topic patterns per register entry. Generic tech vocabulary must NOT
# link (bag-of-words overlap between a 2.6k-char window and short register texts
# matches everything). Each pattern below names the entry's distinctive subject.
# Format: (register, entry_id, live, [regex], min_hits).
REGISTER_TOPICS = [
    ("DECISION_LEDGER", "DEC-000001", True, [r"f drive", r"f: drive", r"\bpartition\b"], 1),
    ("DECISION_LEDGER", "DEC-000002", True, [r"owner.testable", r"jonathan opens"], 1),
    ("DECISION_LEDGER", "DEC-000003", True, [r"atheena", r"canonical project name",
                                             r"canonical.{0,40}athena|athena.{0,40}canonical"], 1),
    ("DECISION_LEDGER", "DEC-000004", True, [r"unknown.{0,40}not.{0,20}repositor",
                                             r"4,066|4066"], 1),
    ("DECISION_LEDGER", "DEC-000005", True, [r"monorepo", r"own repositor|per.component repositor"], 1),
    ("DECISION_LEDGER", "DEC-000006", True, [r"visibility.{0,30}private|private.{0,30}visibility",
                                             r"public release.{0,20}approv|owner gate"], 1),
    ("DECISION_LEDGER", "DEC-000007", True, [r"16/17|32/32|76/76",
                                             r"c\+\+.{0,25}(ctest|test).{0,25}(fail|pass)",
                                             r"owner.accepted"], 1),
    ("DECISION_LEDGER", "DEC-000008", True, [r"24.{0,30}(shared|foundation)",
                                             r"14.{0,25}24|verified.shared"], 1),
    ("DECISION_LEDGER", "DEC-000009", True, [r"independently maintainable", r"repo.?threshold"], 1),
    ("DECISION_LEDGER", "DEC-000010", True, [r"jayprophit.{0,25}inventor|github inventor",
                                             r"no.?deletion|do not delete"], 1),
    ("CONTRADICTION_REGISTER", "CON-000001", False, [r"14.{0,25}24|24.{0,25}14",
                                                     r"verified.shared.{0,30}14"], 1),
    ("CONTRADICTION_REGISTER", "CON-000002", False, [r"atheena", r"athena.{0,40}canonical"], 1),
    ("CONTRADICTION_REGISTER", "CON-000003", False, [r"f drive|f: drive", r"\bpartition\b"], 1),
    ("CONTRADICTION_REGISTER", "CON-000004", True, [r"16/17|32/32|76/76",
                                                    r"c\+\+.{0,25}(test|ctest).{0,25}(fail|pass)",
                                                    r"owner.accepted|auto.accept"], 1),
    ("CONTRADICTION_REGISTER", "CON-000005", False, [r"unknown.{0,40}repositor.{0,20}(candidat|creation)",
                                                     r"4,066|4066"], 1),
    ("CONTRADICTION_REGISTER", "CON-000006", False, [r"monorepo"], 1),
    ("CONTRADICTION_REGISTER", "CON-000007", False, [r"visibility.{0,30}(private|public)"], 1),
    ("CONTRADICTION_REGISTER", "CON-000008", False, [r"unknown.{0,40}project.{0,20}repositor"], 1),
    ("CONTRADICTION_REGISTER", "CON-000009", True, [r"16/17|32/32|76/76",
                                                    r"owner.accepted|auto.accept|do not auto"], 1),
    ("CONTRADICTION_REGISTER", "CON-000010", False, [r"athena"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000001", True, [r"atheena", r"athena.{0,40}(canonical|correction)",
                                                   r"REQ-ATHENA-001|REQ-ATHEENA-001"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000002", False, [r"REQ-SHARED-14-ONLY|REQ-SHARED-24-TOTAL"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000003", False, [r"REQ-REPO-ALL-COMPONENTS|REQ-REPO-THRESHOLD"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000004", False, [r"REQ-F-DRIVE-PARTITION|REQ-F-DRIVE-SKIPPED",
                                                    r"f drive.{0,30}skip|skip.{0,30}f drive"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000005", True, [r"16/17|32/32|76/76", r"REQ-GENESIS-ALL-PASS",
                                                   r"c\+\+.{0,25}(fail|ctest)"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000006", False, [r"REQ-REPO-PUBLIC-DEFAULT|REQ-REPO-PRIVATE-DEFAULT"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000007", False, [r"REQ-MONOREPO-ALLOWED|REQ-REPO-PER-COMPONENT"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000008", False, [r"REQ-SHARED-14-VERIFIED|REQ-SHARED-24-TOTAL-FOUNDATION"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000009", True, [r"atheena", r"REQ-ATHENA-HISTORICAL|REQ-ATHEENA-CURRENT",
                                                   r"historical.{0,25}athena|athena.{0,25}provenance"], 1),
    ("SUPERSESSION_REGISTER", "SUP-000010", False, [r"REQ-ALL-352-CANDIDATES|REQ-290-CANDIDATES"], 1),
]
REGISTER_RES = [(reg, iid, live, [re.compile(p, re.I) for p in pats], need)
                for reg, iid, live, pats, need in REGISTER_TOPICS]
ID_MENTION_RE = re.compile(r"\b(DEC-\d+|CON-\d+|SUP-\d+|REQ-[A-Z0-9-]+)\b")


def register_links(text, id_index):
    """Topic-pattern + explicit ID-mention linking. Returns list of link dicts."""
    links = []
    for reg, iid, live, pats, need in REGISTER_RES:
        if sum(1 for p in pats if p.search(text)) >= need:
            links.append({"register": reg, "id": iid, "live": live,
                          "method": "TOPIC_PATTERN"})
    for mention in set(ID_MENTION_RE.findall(text)):
        if mention in id_index and not any(L["id"] == mention for L in links):
            reg, live = id_index[mention]
            links.append({"register": reg, "id": mention, "live": live,
                          "method": "ID_MENTION"})
    return links[:8]


def build_id_index(registers):
    idx = {}
    for reg_name, items in registers:
        for it in items:
            if not isinstance(it, dict):
                continue
            iid = it.get("DECISION_ID") or it.get("CONTRADICTION_ID") or it.get("SUPERSESSION_ID", "")
            if not iid:
                continue
            if reg_name == "DECISION_LEDGER":
                live = it.get("STATUS", "") == "ACTIVE"
            elif reg_name == "CONTRADICTION_REGISTER":
                live = it.get("STATUS", "") in ("NEEDS_OWNER", "UNRESOLVED")
            else:
                live = it.get("MIGRATION_STATUS", "") not in ("COMPLETE", "")
            idx[iid] = (reg_name, live)
            for extra in (it.get("AFFECTED_DECISIONS", []) + it.get("AFFECTED_REQUIREMENTS", []) +
                          it.get("AFFECTED_TASKS", [])):
                if isinstance(extra, str) and re.fullmatch(r"(DEC|CON|SUP|REQ|TASK)-[A-Z0-9-]+", extra):
                    idx.setdefault(extra, (reg_name, live))
    return idx


def main():
    queue = sys.argv[1] if len(sys.argv) > 1 else "project"
    log = json.load(open(PASS1_LOG, encoding="utf-8"))["records"]
    if queue == "project":
        items = [r for r in log if r["NEW_PROJECT"]]
    else:
        items = [r for r in log if r["STATUS"] == "UNCLASSIFIED"]
    print(f"Pass-2 queue={queue} n={len(items)}")

    idx, cat_dist = load_records()
    print(f"analysis records indexed: {len(idx)}")
    print("category distribution:", dict(cat_dist))

    registers = []
    for reg_name, path, attr in [("DECISION_LEDGER", AB / "DECISION_LEDGER.json", "KEY_DECISIONS"),
                                 ("SUPERSESSION_REGISTER", AB / "SUPERSESSION_REGISTER.json", "SUPERSESSION_CHAINS"),
                                 ("CONTRADICTION_REGISTER", AB / "CONTRADICTION_REGISTER.json", "CONTRADICTIONS")]:
        try:
            mod = _load_py("reg_" + attr.lower(), path)
            registers.append((reg_name, getattr(mod, attr, [])))
        except Exception as e:
            print(f"  WARN: register {reg_name} unloadable ({e}); continuing without it")
            registers.append((reg_name, []))
    print("register sizes:", [(n, len(v)) for n, v in registers])
    id_index = build_id_index(registers)

    enriched, dec_links_all = [], []
    for rec in items:
        # Pass-1 schema: SOURCE_LOCATION = model, SOURCE_DOCUMENT = source filename.
        filename = rec.get("SOURCE_DOCUMENT", "") or ""
        model = model_from_filename(filename, (rec.get("SOURCE_LOCATION", "") or "deepseek").lower())
        text = read_source(model, filename) if filename else "__NO_FILENAME__"
        frag = rec["RAW_TEXT"]
        if text.startswith("__"):
            pos, how = -1, "MISSING"
        else:
            pos, how = locate(text, frag)
        utype, win = utterance_type(model, text, pos, frag)
        win_red = redact(win)[:2600] if win else ""

        target = rec["NEW_PROJECT"] or rec["NEW_DOMAIN"]
        rec_info = idx.get((model, filename.lower()), {})
        links = register_links(frag + "\n" + win_red, id_index) if win else []
        for L in links:
            L["shared_terms"] = []
        sup_live = [L for L in links if L["register"] == "SUPERSESSION_REGISTER" and L["live"]]
        con_live = [L for L in links if L["register"] == "CONTRADICTION_REGISTER" and L["live"]]
        repo_ev = repo_evidence(rec["NEW_PROJECT"], target) if rec["NEW_PROJECT"] else {"note": "DOMAIN_ONLY"}
        siblings = [s for s in rec_info.get("requirements", [])
                    if len(content_tokens(s.get("text", "")) & content_tokens(frag)) >= 2]
        tie = "tie" in rec.get("CLASSIFICATION_REASONING", "").lower()

        ev_for, ev_against, strong = [], [], False
        base = rec["CLASSIFICATION_CONFIDENCE"]
        # Positive evidence.
        disp = [a for a in PROJECT_DISPLAY.get(target, [])]
        if any(a in win.lower() for a in disp if len(a.strip()) > 3) and utype == "OWNER_PROMPT":
            ev_for.append("+0.30 explicit project routing in owner prompt"); base += 0.30; strong = True
        elif any(a in win.lower() for a in disp if len(a.strip()) > 3):
            ev_for.append("+0.10 project named in context"); base += 0.10
        if OWNER_VERBS.search(win) and any(a in win.lower() for a in disp):
            ev_for.append("+0.30 owner routing verb"); base += 0.30; strong = True
        if len(siblings) >= 2:
            ev_for.append(f"+0.15 {len(siblings)} same-topic sibling requirements"); base += 0.15
        if isinstance(repo_ev.get("hits"), int) and repo_ev["hits"] >= 3:
            ev_for.append(f"+0.15 architecture match ({repo_ev['hits']} repo files)"); base += 0.15
        active_links = [L for L in links if L["register"] == "DECISION_LEDGER" and L["live"]]
        if active_links:
            ev_for.append(f"+0.10 ACTIVE decision link {active_links[0]['id']}"); base += 0.10; strong = True
        if utype == "OWNER_PROMPT":
            ev_for.append("+0.10 fragment in owner prompt position"); base += 0.10
        # Negative evidence.
        if utype == "ASSISTANT_REASONING":
            ev_against.append("-0.30 assistant-reasoning provenance"); base -= 0.30
        if tie:
            ev_against.append("-0.20 multiple plausible projects (Pass-1 tie)"); base -= 0.20
        if PRONOUN_RE.search(frag) and not any(a in frag.lower() for a in disp):
            if not any(a in win.lower() for a in disp if len(a.strip()) > 3):
                ev_against.append("-0.20 pronoun/core-noun unresolved"); base -= 0.20
        if INTERROG_RE.search(frag.strip()) and not rec_info.get("decisions"):
            ev_against.append("-0.15 interrogative without record of approval"); base -= 0.15
        if utype in ("ASSISTANT_REASONING", "ASSISTANT_ANSWER") and not rec_info.get("decisions"):
            ev_against.append("-0.15 AI-only, no owner decision in record"); base -= 0.15
        if sup_live or con_live:
            ev_against.append("-0.25 live register conflict/supersession signal"); base -= 0.25
        conf = round(max(0.05, min(0.95, base)), 3)

        # Acceptance state. Resolved/historical register hits are informational only.
        if sup_live:
            state = "SUPERSEDED"
        elif utype == "ASSISTANT_REASONING" and not strong and not active_links:
            state = "NON_ACTIONABLE"
        elif con_live or (tie and conf < 0.8):
            state = "CONFLICTED" if con_live else "AMBIGUOUS"
        elif conf >= 0.90 and strong:
            state = "AUTO_VERIFIED"
        elif conf >= 0.80:
            state = "HIGH_CONFIDENCE_STAGED"
        elif conf >= 0.50 or utype == "OWNER_PROMPT":
            state = "AMBIGUOUS"
        else:
            state = "NON_ACTIONABLE" if utype.startswith("ASSISTANT") else "AMBIGUOUS"

        out = dict(rec)
        out.update({"PASS": "PASS_2_CONTEXT_ENRICHMENT",
                    "RESOLVED_REQUIREMENT": frag,
                    "RESOLUTION_EVIDENCE": {"utterance_type": utype,
                                            "record_category": rec_info.get("owner_statement_category", ""),
                                            "record_doc_type": rec_info.get("doc_type", ""),
                                            "record_topics": rec_info.get("key_topics", []),
                                            "record_decisions": len(rec_info.get("decisions", [])),
                                            "sibling_support": len(siblings),
                                            "window_chars": len(win_red),
                                            "fragment_located": pos >= 0,
                                            "locate_method": how,
                                            "model_source": "FILENAME_PREFIX"},
                    "CONTEXT_WINDOW": win_red,
                    "EVIDENCE_FOR": ev_for, "EVIDENCE_AGAINST": ev_against,
                    "PASS1_CONFIDENCE": rec["CLASSIFICATION_CONFIDENCE"],
                    "ENRICHED_CONFIDENCE": conf,
                    "STRONG_EVIDENCE": strong,
                    "REGISTER_LINKS": links,
                    "REPO_EVIDENCE": repo_ev,
                    "ACCEPTANCE_STATE": state,
                    "OWNER_REVIEW_REQUIRED_P2": state in ("CONFLICTED",) or (state == "AMBIGUOUS" and conf >= 0.80),
                    "ENRICHED_DATE": NOW})
        enriched.append(out)
        for L in links:
            dec_links_all.append({"capability": rec["SHA256_ID"], "project": target, **L})

    by_state = Counter(e["ACCEPTANCE_STATE"] for e in enriched)
    (OUT / "PASS_2_LOG.json").write_text(
        json.dumps({"generated_at": NOW, "queue": queue, "count": len(enriched),
                    "records": enriched}, indent=1, ensure_ascii=False), encoding="utf-8")
    for state in ["AUTO_VERIFIED", "HIGH_CONFIDENCE_STAGED", "AMBIGUOUS", "CONFLICTED",
                  "SUPERSEDED", "NON_ACTIONABLE"]:
        sel = [e for e in enriched if e["ACCEPTANCE_STATE"] == state]
        (OUT / f"PASS_2_{state}.json").write_text(
            json.dumps({"generated_at": NOW, "count": len(sel), "records": sel},
                       indent=1, ensure_ascii=False), encoding="utf-8")
    owner_q = [e for e in enriched if e["OWNER_REVIEW_REQUIRED_P2"]]
    (OUT / "PASS_2_OWNER_REVIEW.json").write_text(
        json.dumps({"generated_at": NOW, "count": len(owner_q), "records": owner_q},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "DECISION_REQUIREMENT_LINKS.json").write_text(
        json.dumps({"generated_at": NOW, "count": len(dec_links_all), "links": dec_links_all},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    rep = ["# PASS 2 Context-Enrichment Report", "", f"Generated: {NOW}",
           f"Queue: {queue} (n={len(enriched)})", "",
           "## Acceptance states"]
    for s, c in by_state.most_common():
        rep.append(f"- {s}: {c}")
    rep += ["",
            f"OWNER_REVIEW_REQUIRED (exception-based): {len(owner_q)}",
            f"Register links found: {len(dec_links_all)}",
            "## Method",
            "Base = Pass-1 fragment confidence; additive explainable evidenceModel:",
            "owner routing mention +0.30, owner verb +0.30, siblings +0.15, repo match +0.15,",
            "ACTIVE decision +0.10, owner-prompt position +0.10; assistant-reasoning -0.30,",
            "tie -0.20, unresolved pronoun -0.20, unapproved interrogative -0.15,",
            "AI-only -0.15, register conflict -0.25. AUTO_VERIFIED requires >=0.90 AND",
            "strong evidence (owner routing, owner verb, or ACTIVE decision link).",
            "Raw text never altered; credentials redacted from stored windows."]
    (OUT / "PASS_2_REPORT.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    print("states:", dict(by_state), "owner_review:", len(owner_q), "links:", len(dec_links_all))


if __name__ == "__main__":
    main()
