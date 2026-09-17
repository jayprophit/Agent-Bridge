#!/usr/bin/env python3
"""UNKNOWN requirement reconciliation pipeline (INGEST -> REGISTER).

Reads the 4,066 UNKNOWN capabilities produced by route_requirements.py
(whose narrow PROJECT_KEYWORDS left them unclassified) and applies the
broader AUTO_CLASSIFICATION_KEYWORDS from UNKNOWN_REQUIREMENT_RECONCILIATION.json.

Stages: INGEST, AUTO_CLASSIFY, SEMANTIC_CLUSTER, PROJECT_ROUTE, DEDUPE,
SUPERSESSION, CONTRADICTION, OWNER_REVIEW, FINALIZE, REGISTER.

Safe by design: original registry files are never overwritten. All routing
output is staged under E:/OpenCode-Data/conversation-analysis/ for owner
review before any canonical merge.
"""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from output_locations import area as _area, assert_not_desktop as _guard

BASE = _area("CONVERSATION_ANALYSIS")
_guard(BASE)  # programme outputs must not target the Desktop
REGDIR = BASE / "requirement_registry"
UNKNOWN_PATH = REGDIR / "unknown" / "capabilities.json"
# Canonical project repos live on the Desktop per owner directive; resolve the
# Desktop from the home directory so no personal absolute path is hardcoded.
DESKTOP = Path.home() / "Desktop"
AGENT_BRIDGE_DIR = DESKTOP / "Agent-Bridge"

NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# --- Keyword model (from UNKNOWN_REQUIREMENT_RECONCILIATION.json) ---
AUTO_CLASSIFICATION_KEYWORDS = {
    "GENESIS": ["genesis", "cognition", "adapter", "contract", "avatar",
                "intelligence", "reasoning", "planning", "memory", "ledger"],
    "AGENT_BRIDGE": ["agent bridge", "execution", "orchestration", "task graph",
                     "merkle dag", "work proof", "problem memory"],
    "IDE_WORKSPACE": ["ide", "workspace", "react", "vite", "editor",
                      "development environment", "code editor"],
    "MAT": ["materials", "atlas", "table", "codex", "material property",
            "density", "elastic", "thermal", "corrosion"],
    "UNIVERSAL_BRIDGE": ["universal bridge", "interoperability", "device",
                         "hardware", "midi", "audio routing", "device profile"],
    "POIETEK": ["poietek", "daw", "audio engine", "plugin", "vst", "clap",
                "synthesizer", "sampler", "effect", "mixer", "timeline",
                "piano roll"],
    "ATHENA": ["athena", "atheena", "health", "fitness", "sport", "nutrition",
               "workout", "wearable", "biometric", "wellness"],
    "AETHERIUS_OS": ["aetherius os", "operating system", "kernel", "shell",
                     "system service", "file manager", "settings"],
    "OFFICE": ["word", "document", "spreadsheet", "presentation", "email",
               "calendar", "contact", "task", "note", "pdf", "form"],
    "CREATIVE": ["image", "vector", "raster", "paint", "photo", "draw",
                 "illustration", "desktop publishing", "layout", "typography"],
    "VIDEO": ["video", "edit", "timeline", "clip", "track", "transcode",
              "encode", "decode", "compositor", "vfx", "motion graphics"],
    "AUDIO": ["audio", "sound", "music", "podcast", "synthesis", "sampler",
              "effect", "mixer", "mastering", "stem"],
    "CAD": ["cad", "cam", "bim", "mechanical", "electrical", "pcb",
            "architecture", "civil", "parametric", "constraint", "assembly"],
    "ENGINEERING": ["engineering", "simulation", "fea", "cfd", "multiphysics",
                    "optimization", "generative", "digital twin"],
    "SIMULATION": ["simulation", "physics", "rigid body", "soft body", "fluid",
                   "thermal", "electromagnetic", "acoustic", "particle"],
    "DEVELOPER": ["developer", "ide", "git", "debugger", "profiler", "compiler",
                  "container", "api", "sdk", "regex", "json"],
    "COMMUNICATION": ["chat", "message", "email", "call", "video call",
                      "meeting", "conference", "screen share", "notification"],
    "SECURITY": ["security", "firewall", "permission", "credential", "password",
                 "encryption", "authenticator", "sandbox", "privacy"],
    "ACCESSIBILITY": ["accessibility", "screen reader", "magnifier", "speech",
                      "dictation", "tts", "stt", "caption", "contrast"],
    "AI": ["ai", "ml", "llm", "inference", "training", "embedding", "vector",
           "rag", "semantic", "genesis"],
    "DATA": ["data", "database", "storage", "sync", "backup", "search",
             "index", "query", "analytics", "visualization"],
    "CLOUD": ["cloud", "sync", "backup", "distributed", "provider", "conflict",
              "encryption", "content addressed"],
    "DEVICE": ["device", "driver", "usb", "bluetooth", "wifi", "display",
               "audio", "camera", "sensor", "controller"],
    "HEALTH": ["health", "fitness", "exercise", "sport", "nutrition",
               "training", "wearable", "biometric", "medical"],
    "GAMING": ["game", "gaming", "engine", "rendering", "physics", "animation",
               "network", "multiplayer", "vr", "ar", "xr"],
    "UTILITIES": ["calculator", "converter", "clock", "timer", "weather", "map",
                  "translate", "dictionary", "scanner", "recorder"],
}

EXISTING_PROJECTS = ["GENESIS", "AGENT_BRIDGE", "IDE_WORKSPACE", "MAT",
                     "UNIVERSAL_BRIDGE", "POIETEK", "ATHENA", "AETHERIUS_OS"]

# 24 shared components (SHARED_COMPONENT_REGISTRY.json, 14 verified + 10 foundation)
SHARED_COMPONENT_KEYWORDS = {
    "Aetherius Math": ["linear algebra", "calculus", "numeric", "mathematics", " math "],
    "Aetherius Units": ["unit conversion", "dimensional analysis", "measurement units"],
    "Aetherius Geometry": ["csg", "b-rep", "computational geometry", "geometry kernel"],
    "Aetherius Mesh": ["meshing", "tetrahedral", "hexahedral", "mesh refinement"],
    "Aetherius Materials": ["material property", "materials database"],
    "Aetherius Rendering": ["renderer", "rendering engine", "ray tracing", "shader"],
    "Aetherius Colour": ["colour", "color management", "color grading"],
    "Aetherius Audio": ["audio engine", "audio routing"],
    "Aetherius Video": ["video engine", "video codec"],
    "Aetherius Media": ["media framework", "media pipeline"],
    "Aetherius Timeline": ["timeline editor", "multitrack timeline"],
    "Aetherius Animation": ["skeletal animation", "keyframe animation"],
    "Aetherius Physics": ["rigid body", "soft body", "physics engine"],
    "Aetherius Simulation": ["digital twin", "multiphysics simulation"],
    "Aetherius Database": ["embedded database", "database engine"],
    "Aetherius Storage": ["content addressed storage", "distributed storage"],
    "Aetherius Sync": ["file sync", "sync engine", "conflict resolution"],
    "Aetherius Identity": ["single sign-on", "sso", "identity provider"],
    "Aetherius Permissions": ["permission model", "access control list"],
    "Aetherius Workflow": ["workflow automation", "workflow engine"],
    "Aetherius Telemetry": ["telemetry", "usage analytics", "crash reporting"],
    "Aetherius Plugin SDK": ["plugin sdk", "plugin api", "extension api"],
    "Aetherius Project Model": ["project file format", "project model"],
    "Aetherius Asset Engine": ["asset pipeline", "asset management"],
}

CODEBASE_INDICATORS = {
    "GENESIS": ["cognition", "plan", "execution", "contract", "ledger", "memory"],
    "AGENT_BRIDGE": ["agent", "coding", "deployment", "workflow", "IDE"],
    "IDE_WORKSPACE": ["interface", "UI", "display", "render", "graphics"],
    "MAT": ["modular", "task", "workflow", "graph", "dependency"],
    "POIETEK": ["audio", "daw", "plugin", "effect", "instrument"],
    "UNIVERSAL_BRIDGE": ["bridge", "integration", "connect", "bind"],
    "ATHENA": ["autonomous", "reasoning", "planning"],
    "AETHERIUS_OS": ["operating system", "kernel", "shell", "file manager", "settings"],
}

IMPLEMENTATION_HINTS = {
    "GENESIS": "Agent-Bridge/genesis_bridge.py, genesis_avatar.py; Genesis C++ core",
    "AGENT_BRIDGE": "Agent-Bridge/bridge.py, execution_contract.py, task_dag.py",
    "IDE_WORKSPACE": "Agent-Bridge/ide_bridge.py; IDE-Workspace/ repo",
    "MAT": "Materials-Atlas-Table-Codex---MAT/ repo (schema registries)",
    "UNIVERSAL_BRIDGE": "Universal-Bridge/ repo (Safe Implementation Scope v0.4)",
    "POIETEK": "Poietek/ repo (requirements.jsonl, src-tauri/)",
    "ATHENA": "No local repo yet - proposal only (canonical ATHENA; historical alias ATHEENA)",
    "AETHERIUS_OS": "Aetherius-OS/ repo",
}

LOCAL_PROJECT_DIRS = {
    "GENESIS": DESKTOP / "Genesis",
    "AGENT_BRIDGE": AGENT_BRIDGE_DIR,
    "IDE_WORKSPACE": DESKTOP / "IDE-Workspace",
    "MAT": DESKTOP / "Materials-Atlas-Table-Codex---MAT",
    "UNIVERSAL_BRIDGE": DESKTOP / "Universal-Bridge",
    "POIETEK": DESKTOP / "Poietek",
    "ATHENA": None,
    "AETHERIUS_OS": DESKTOP / "Aetherius-OS",
}

QUESTION_RE = re.compile(r"\?\s*$|^(what|how|why|when|which|who|where|can|should|is|are|do)\b.*\?\s*$", re.I)
RESEARCH_RE = re.compile(r"\b(research|study|survey|benchmark|dataset|analysis|compare|evaluation|literature)\b", re.I)
BUSINESS_RE = re.compile(r"\b(pricing|revenue|business model|market|monetiz|subscription|enterprise sales)\b", re.I)
POLICY_RE = re.compile(r"\b(policy|compliance|regulation|gdpr|license|licensing|terms of service|privacy policy)\b", re.I)
SUPERSESSION_RE = re.compile(r"\b(replaces?|instead of|supersedes?|obsolete|deprecated|updated version|\bv2\b|\bv1\b)\b", re.I)
COMPONENT_TYPE_RES = [
    ("APPLICATION", re.compile(r"\b(app|application|editor|browser|client|studio|suite)\b", re.I)),
    ("ENGINE", re.compile(r"\bengine\b", re.I)),
    ("LIBRARY", re.compile(r"\blibrary|libraries\b", re.I)),
    ("PLUGIN", re.compile(r"\bplug-?in\b", re.I)),
    ("EXTENSION", re.compile(r"\bextension\b", re.I)),
    ("SERVICE", re.compile(r"\bservice\b", re.I)),
    ("ADAPTER", re.compile(r"\badapter\b", re.I)),
    ("DRIVER", re.compile(r"\bdriver\b", re.I)),
]
CONCRETE_COMPONENT_RE = re.compile(
    r"\b(video editor|audio editor|image editor|daw|browser|file manager|media player|"
    r"game engine|physics engine|rendering engine|synthesizer|sampler|plugin host|"
    r"ide|code editor|terminal|calculator|calendar|email client)\b", re.I)

CONTRADICTION_TOPICS = [
    # (con_id, [patterns], min_hits): flag when >= min_hits patterns match.
    ("CON-000001", [r"shared component", r"\b14\b.*\b24\b|\b24\b.*\b14\b"], 1),
    ("CON-ATHENA-NAMING", [r"atheena", r"athena"], 1),
    ("CON-F-DRIVE", [r"f drive", r"f: drive", r"\bpartition\b"], 1),
    ("CON-REPO-VISIBILITY", [r"public release", r"repo.*visib", r"visib.*repo"], 1),
    ("CON-MONOREPO", [r"monorepo", r"monolithic repo"], 1),
]
CONTRADICTION_RES = [(cid, [re.compile(p) for p in pats], need)
                     for cid, pats, need in CONTRADICTION_TOPICS]


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compile_kw_matcher(kw):
    """Tiered matcher: phrases substring; len<=2 exact word; else word-start.

    Prevents infix false positives ('ai' in 'said'/'training', 'ar' in
    'search', 'media' in 'immediately', 'form' in 'information').
    """
    k = kw.lower().strip()
    if " " in k or "-" in k:
        pat = re.compile(re.escape(k))
    elif len(k) <= 2 or k in ("ide", "tts", "stt", "rag", "data", "fea"):
        # Exact word: 'data' is a prefix of 'database', 'fea' of 'feature'/'fear'.
        pat = re.compile(r"\b" + re.escape(k) + r"\b")
    else:
        pat = re.compile(r"\b" + re.escape(k))
    return pat


KW_MATCHERS = {t: [(kw, compile_kw_matcher(kw)) for kw in kws]
               for t, kws in AUTO_CLASSIFICATION_KEYWORDS.items()}
SHARED_MATCHERS = {n: [(kw, compile_kw_matcher(kw.strip())) for kw in kws]
                   for n, kws in SHARED_COMPONENT_KEYWORDS.items()}


def score_targets(text_low):
    """Return {target: (weighted_score, matched_keywords)}."""
    scores = {}
    for target, matchers in KW_MATCHERS.items():
        weighted = 0
        matched = []
        for kw, pat in matchers:
            if pat.search(text_low):
                w = 2 if " " in kw.strip() else 1
                weighted += w
                matched.append(kw)
        if weighted:
            scores[target] = (weighted, matched)
    return scores


def pick_target(scores):
    if not scores:
        return None, 0, [], False
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1][0], kv[0]))
    best, (w, matched) = ranked[0]
    tie = len(ranked) > 1 and ranked[1][1][0] == w
    if tie:
        # Prefer existing projects over domains on equal score.
        tied = [t for t, (tw, _) in ranked if tw == w]
        proj_tied = [t for t in tied if t in EXISTING_PROJECTS]
        if proj_tied:
            best = sorted(proj_tied)[0]
            w, matched = scores[best]
    return best, w, matched, tie


def compute_confidence(weighted, text_len, tie, exact_bonus):
    w = min(weighted, 4)
    conf = 0.35 + 0.14 * w + (0.05 if exact_bonus else 0.0)
    if tie:
        conf -= 0.10
    if text_len < 40:
        conf -= 0.15
    return round(max(0.05, min(0.95, conf)), 3)


def detect_shared(text_low):
    found = []
    for name, matchers in SHARED_MATCHERS.items():
        for _, pat in matchers:
            if pat.search(text_low):
                found.append(name)
                break
    return found[:2]


def detect_component_type(text):
    for ctype, rx in COMPONENT_TYPE_RES:
        if rx.search(text):
            return ctype
    return ""


def cross_reference(text_low):
    matched = []
    for proj, indicators in CODEBASE_INDICATORS.items():
        for ind in indicators:
            if ind.lower() in text_low:
                matched.append(f"{proj}:{ind}")
    matched = sorted(set(matched))
    return matched, round(min(len(matched) / 2.0, 1.0), 3)


def main():
    print("STAGE INGEST: loading UNKNOWN capabilities...")
    unknowns = json.loads(UNKNOWN_PATH.read_text(encoding="utf-8"))
    print(f"  loaded {len(unknowns)} UNKNOWN capabilities")

    # Existing routed capabilities for cross-duplicate detection.
    existing_norm = {}
    for proj_dir in REGDIR.iterdir():
        if not proj_dir.is_dir() or proj_dir.name == "unknown":
            continue
        cap_file = proj_dir / "capabilities.json"
        if not cap_file.exists():
            continue
        try:
            items = json.loads(cap_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  WARN: cannot load {cap_file}: {e}")
            continue
        for it in items:
            t = it.get("requirement_text", "")
            if t:
                existing_norm.setdefault(normalize(t), (it.get("capability_id", ""), proj_dir.name.upper()))

    local_dir_evidence = {k: (v is not None and v.exists()) for k, v in LOCAL_PROJECT_DIRS.items()}

    log_records = []
    seen_norm = {}
    stats = defaultdict(int)
    by_project = defaultdict(int)
    by_domain = defaultdict(int)
    by_shared = defaultdict(int)

    print("STAGES AUTO_CLASSIFY/PROJECT_ROUTE/DEDUPE/SUPERSESSION/CONTRADICTION...")
    for item in unknowns:
        cap_id = item.get("capability_id", "")
        raw = item.get("requirement_text", "") or ""
        atomic = item.get("atomic_capability", "") or raw
        text_low = (raw + " " + atomic).lower()
        norm = normalize(raw)
        prov = item.get("provenance", {})

        rec = {
            "REQUIREMENT_ID": f"REQ-{cap_id[:8].upper()}" if cap_id else "REQ-UNKNOWN",
            "SHA256_ID": cap_id,
            "RAW_TEXT": raw,
            "NORMALIZED_REQUIREMENT": norm,
            "SOURCE_DOCUMENT": prov.get("source_file", ""),
            "SOURCE_LOCATION": prov.get("model", ""),
            "SOURCE_DATE": item.get("extracted_at", ""),
            "ORIGINAL_ROUTING": "UNKNOWN",
            "NEW_ROUTING": "",
            "NEW_PROJECT": "",
            "NEW_DOMAIN": "",
            "NEW_SHARED_COMPONENT": [],
            "NEW_COMPONENT_TYPE": "",
            "CLASSIFICATION": "",
            "CLASSIFICATION_CONFIDENCE": 0.0,
            "CLASSIFICATION_REASONING": "",
            "SUPERSEDES": [],
            "SUPERSEDED_BY": [],
            "DUPLICATE_OF": "",
            "CONTRADICTS": [],
            "RELATED_REQUIREMENTS": [],
            "REPOSITORY_ID": "",
            "TASK_ID": "",
            "IMPLEMENTATION_PATH": "",
            "PRIORITY": "P6_RESEARCH_FUTURE",
            "STATUS": "UNCLASSIFIED",
            "OWNER_REVIEW_REQUIRED": True,
            "REPOSITORY_CANDIDATE": False,
            "RECONCILED_BY": "AUTO",
            "RECONCILED_DATE": NOW,
            "PROVENANCE": {"ORIGINAL_SOURCE": "chat_corpus_analysis",
                           "ANALYSIS_DATE": item.get("extracted_at", ""),
                           "ROUTING_VERSION": "reconcile-v1"},
        }

        # DEDUPE within UNKNOWN set, then against already-routed registry.
        if norm and norm in seen_norm:
            rec["CLASSIFICATION"] = "DUPLICATE"
            rec["DUPLICATE_OF"] = seen_norm[norm]
            rec["CLASSIFICATION_CONFIDENCE"] = 0.95
            rec["CLASSIFICATION_REASONING"] = "Exact normalized-text duplicate within UNKNOWN set."
            rec["STATUS"] = "CLASSIFIED"
            rec["OWNER_REVIEW_REQUIRED"] = False
            stats["DUPLICATES_FOUND"] += 1
            log_records.append(rec)
            continue
        if norm:
            seen_norm[norm] = cap_id
        if norm and norm in existing_norm:
            dup_id, dup_proj = existing_norm[norm]
            rec["CLASSIFICATION"] = "DUPLICATE"
            rec["DUPLICATE_OF"] = dup_id
            rec["CLASSIFICATION_REASONING"] = f"Exact duplicate of already-routed {dup_proj} capability {dup_id}."
            rec["CLASSIFICATION_CONFIDENCE"] = 0.95
            rec["STATUS"] = "CLASSIFIED"
            rec["OWNER_REVIEW_REQUIRED"] = False
            stats["DUPLICATES_FOUND"] += 1
            log_records.append(rec)
            continue

        scores = score_targets(text_low)
        target, weighted, matched, tie = pick_target(scores)
        # Exact-name bonus uses word boundaries for single-word names so that
        # e.g. MAT does not bonus off "materials", AI off "training", DATA off "database".
        exact_bonus = False
        if target:
            _tname = target.replace("_", " ").lower()
            if " " in _tname:
                exact_bonus = _tname in text_low
            else:
                exact_bonus = bool(re.search(r"\b" + re.escape(_tname) + r"\b", text_low))
        conf = compute_confidence(weighted, len(raw), tie, exact_bonus) if target else 0.0
        shared = detect_shared(" " + text_low + " ")
        ctype = detect_component_type(raw)
        x_indicators, x_score = cross_reference(text_low)
        concrete = bool(CONCRETE_COMPONENT_RE.search(raw))

        # Non-routed categories first (keyword-independent).
        words = len(raw.split())
        if QUESTION_RE.search(raw.strip()) and not target:
            rec.update(CLASSIFICATION="QUESTION_ONLY", CLASSIFICATION_CONFIDENCE=0.3,
                       CLASSIFICATION_REASONING="Interrogative with no project/domain signal; owner question, not a requirement.",
                       PRIORITY="P6_RESEARCH_FUTURE", STATUS="CLASSIFIED",
                       OWNER_REVIEW_REQUIRED=False)
            stats["QUESTION_ONLY"] += 1
        elif words < 8 and not target:
            rec.update(CLASSIFICATION="CONTEXT_ONLY", CLASSIFICATION_CONFIDENCE=0.25,
                       CLASSIFICATION_REASONING="Short fragment with no actionable signal; context only.",
                       STATUS="CLASSIFIED", OWNER_REVIEW_REQUIRED=False)
            stats["CONTEXT_ONLY"] += 1
        elif not target and RESEARCH_RE.search(raw):
            rec.update(CLASSIFICATION="RESEARCH_REQUIREMENT", CLASSIFICATION_CONFIDENCE=0.35,
                       CLASSIFICATION_REASONING="Research-only language, no implementation target.",
                       STATUS="CLASSIFIED")
            stats["RESEARCH_ONLY"] += 1
        elif not target and BUSINESS_RE.search(raw):
            rec.update(CLASSIFICATION="BUSINESS_REQUIREMENT", CLASSIFICATION_CONFIDENCE=0.4,
                       CLASSIFICATION_REASONING="Business/commercial language, no technical target.",
                       STATUS="CLASSIFIED")
            stats["BUSINESS_REQUIREMENT"] += 1
        elif not target and POLICY_RE.search(raw):
            rec.update(CLASSIFICATION="POLICY_REQUIREMENT", CLASSIFICATION_CONFIDENCE=0.4,
                       CLASSIFICATION_REASONING="Policy/compliance language, no technical target.",
                       STATUS="CLASSIFIED")
            stats["POLICY_REQUIREMENT"] += 1
        elif not target:
            rec.update(CLASSIFICATION="GENUINELY_UNRESOLVED" if words < 5 else "AMBIGUOUS",
                       CLASSIFICATION_CONFIDENCE=0.1 if words < 5 else 0.2,
                       CLASSIFICATION_REASONING="No keyword signal; needs owner clarification.",
                       STATUS="UNCLASSIFIED")
            stats["GENUINELY_UNRESOLVED" if words < 5 else "AMBIGUOUS"] += 1
        elif target in EXISTING_PROJECTS:
            rec.update(CLASSIFICATION="EXISTING_PROJECT", NEW_ROUTING="NEW_PROJECT",
                       NEW_PROJECT=target, NEW_SHARED_COMPONENT=shared,
                       NEW_COMPONENT_TYPE=ctype, CLASSIFICATION_CONFIDENCE=conf,
                       CLASSIFICATION_REASONING=f"Keyword match ({weighted} weighted hits: {', '.join(matched[:5])})"
                       + ("; tie broken toward existing project." if tie else "")
                       + ("; exact project-name mention." if exact_bonus else ""),
                       PRIORITY="P4" if conf >= 0.9 else ("P5" if conf >= 0.7 else "P6_RESEARCH_FUTURE"))
            by_project[target] += 1
            for s in shared:
                by_shared[s] += 1
            stats["CLASSIFIED_TO_PROJECTS"] += 1
        else:
            rec.update(CLASSIFICATION="EXISTING_DOMAIN", NEW_ROUTING="NEW_DOMAIN",
                       NEW_DOMAIN=target, NEW_SHARED_COMPONENT=shared,
                       NEW_COMPONENT_TYPE=ctype, CLASSIFICATION_CONFIDENCE=conf,
                       CLASSIFICATION_REASONING=f"Domain keyword match ({weighted} weighted hits: {', '.join(matched[:5])})"
                       + ("; tie present." if tie else ""),
                       PRIORITY="P5" if conf >= 0.7 else "P6_RESEARCH_FUTURE")
            by_domain[target] += 1
            for s in shared:
                by_shared[s] += 1
            stats["CLASSIFIED_TO_DOMAINS"] += 1

        # Repository candidacy (threshold policy SUP-000007/010: only substantial,
        # independently maintainable components; owner decides, we only propose).
        if ctype and concrete and conf >= 0.7 and rec["CLASSIFICATION"] in ("EXISTING_PROJECT", "EXISTING_DOMAIN"):
            rec["REPOSITORY_CANDIDATE"] = True
            stats[f"NEW_{ctype}S"] += 1

        # SUPERSESSION watch (patterns only; chains need owner confirmation).
        if SUPERSESSION_RE.search(raw):
            rec["RELATED_REQUIREMENTS"].append("SUPERSESSION_WATCH")
            stats["SUPERSESSION_WATCH"] += 1

        # CONTRADICTION watch against the registered contradiction topics.
        for con_id, pats, need in CONTRADICTION_RES:
            if sum(1 for p in pats if p.search(text_low)) >= need:
                rec["CONTRADICTS"].append(con_id)
        if rec["CONTRADICTS"]:
            stats["CONTRADICTIONS_FLAGGED"] += 1

        # Cross-reference + implementation path + task id.
        rec["CODEBASE_CROSS_REFERENCE"] = {"matched_indicators": x_indicators, "relevance_score": x_score}
        proj = rec["NEW_PROJECT"]
        if proj and proj in IMPLEMENTATION_HINTS:
            rec["IMPLEMENTATION_PATH"] = IMPLEMENTATION_HINTS[proj]
            if proj != "ATHENA":
                rec["TASK_ID"] = f"TASK-{cap_id[:8].upper()}" if cap_id else ""

        # OWNER_REVIEW thresholds. Low-confidence routed items stay CLASSIFIED
        # (routing recorded, review required); only AMBIGUOUS/GENUINELY are UNCLASSIFIED.
        if rec["CLASSIFICATION"] in ("EXISTING_PROJECT", "EXISTING_DOMAIN"):
            if conf >= 0.9:
                rec["STATUS"] = "RECONCILED"
                rec["OWNER_REVIEW_REQUIRED"] = False
                stats["AUTO_CLASSIFIED"] += 1
            elif conf >= 0.7:
                rec["STATUS"] = "CLASSIFIED"
                stats["FLAGGED_REVIEW"] += 1
            else:
                rec["STATUS"] = "CLASSIFIED"
                stats["LOW_CONFIDENCE_ROUTED"] += 1
        elif rec["STATUS"] == "UNCLASSIFIED":
            stats["MANUAL_REQUIRED"] += 1

        log_records.append(rec)

    print(f"  processed {len(log_records)} records")

    # STAGE SEMANTIC_CLUSTER (blocking by routing + length; Jaccard >= 0.75 -> near-dup note).
    print("STAGE SEMANTIC_CLUSTER...")
    buckets = defaultdict(list)
    for rec in log_records:
        if rec["CLASSIFICATION"] == "DUPLICATE":
            continue
        toks = set(rec["NORMALIZED_REQUIREMENT"].split())
        if len(toks) < 4:
            continue
        key = (rec["NEW_PROJECT"] or rec["NEW_DOMAIN"] or rec["CLASSIFICATION"], len(toks) // 5)
        buckets[key].append((rec, toks))
    near_dup_groups = 0
    for members in buckets.values():
        if len(members) > 400:
            continue
        for i in range(len(members)):
            ri, ti = members[i]
            if len(ri["RELATED_REQUIREMENTS"]) > 3:
                continue
            for j in range(i + 1, len(members)):
                rj, tj = members[j]
                inter = len(ti & tj)
                union = len(ti | tj)
                if union and inter / union >= 0.75:
                    ri["RELATED_REQUIREMENTS"].append(f"NEAR_DUP:{rj['SHA256_ID'][:8]}")
                    rj["RELATED_REQUIREMENTS"].append(f"NEAR_DUP:{ri['SHA256_ID'][:8]}")
                    near_dup_groups += 1
                    break
    print(f"  near-duplicate pairs flagged: {near_dup_groups}")

    # STAGES FINALIZE / REGISTER: split outputs.
    reconciled = [r for r in log_records if r["STATUS"] in ("RECONCILED", "CLASSIFIED")]
    unresolved = [r for r in log_records if r["STATUS"] == "UNCLASSIFIED"]
    stats["RECONCILED"] = sum(1 for r in log_records if r["STATUS"] == "RECONCILED")
    stats["PENDING_REVIEW"] = sum(1 for r in log_records if r["STATUS"] == "CLASSIFIED" and r["OWNER_REVIEW_REQUIRED"])
    stats["TOTAL_UNKNOWN"] = len(log_records)

    (BASE / "UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json").write_text(
        json.dumps({"generated_at": NOW, "total": len(log_records), "records": log_records},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (BASE / "RECONCILED_REQUIREMENTS.json").write_text(
        json.dumps({"generated_at": NOW, "count": len(reconciled), "requirements": reconciled},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    (BASE / "UNRESOLVED_REQUIREMENTS.json").write_text(
        json.dumps({"generated_at": NOW, "count": len(unresolved), "requirements": unresolved},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    # Staged per-project routing (copies; originals untouched).
    staged_root = REGDIR / ".." / "requirement_registry_reconciled"
    for proj in EXISTING_PROJECTS:
        items = [r for r in reconciled if r["NEW_PROJECT"] == proj]
        if not items:
            continue
        d = staged_root / proj.lower()
        d.mkdir(parents=True, exist_ok=True)
        (d / "capabilities.json").write_text(
            json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")
    for dom in set(r["NEW_DOMAIN"] for r in reconciled if r["NEW_DOMAIN"]):
        items = [r for r in reconciled if r["NEW_DOMAIN"] == dom]
        d = staged_root / f"domain_{dom.lower()}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "capabilities.json").write_text(
            json.dumps(items, indent=1, ensure_ascii=False), encoding="utf-8")

    # Task-graph integration file (TaskRecord-compatible; import via task_dag.py).
    tasks = []
    for proj in EXISTING_PROJECTS:
        if any(r["NEW_PROJECT"] == proj for r in reconciled):
            tasks.append({"task_id": f"TASK-ROUTE-{proj}", "parent_task": "",
                          "objective": f"Implement reconciled {proj} requirements",
                          "requirements": [r["SHA256_ID"] for r in reconciled if r["NEW_PROJECT"] == proj],
                          "dependencies": [], "status": "PLANNED"})
    for r in reconciled:
        if r["TASK_ID"]:
            tasks.append({"task_id": r["TASK_ID"], "parent_task": f"TASK-ROUTE-{r['NEW_PROJECT']}",
                          "objective": r["RAW_TEXT"][:200], "requirements": [r["SHA256_ID"]],
                          "dependencies": [], "status": "PLANNED"})
    (BASE / "TASK_GRAPH_INTEGRATION.json").write_text(
        json.dumps({"generated_at": NOW, "task_count": len(tasks), "tasks": tasks},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    # Repository creation queue delta (proposals only; threshold policy applies).
    queue = [{"candidate_name": (r["NEW_DOMAIN"] or r["NEW_PROJECT"]).lower() + "-" + r["SHA256_ID"][:8],
              "component_type": r["NEW_COMPONENT_TYPE"],
              "domain": r["NEW_DOMAIN"] or r["NEW_PROJECT"],
              "source_capability": r["SHA256_ID"],
              "confidence": r["CLASSIFICATION_CONFIDENCE"],
              "status": "PROPOSED",
              "note": "Threshold policy SUP-000007/010: only substantial independently "
                      "maintainable components get repos; owner decides."}
             for r in reconciled if r["REPOSITORY_CANDIDATE"]]
    (BASE / "REPOSITORY_CREATION_QUEUE_DELTA.json").write_text(
        json.dumps({"generated_at": NOW, "count": len(queue), "candidates": queue},
                   indent=1, ensure_ascii=False), encoding="utf-8")

    # Updated registry snapshot (per OUTPUT_FILES spec path).
    updated = {"generated_at": NOW, "source": "reconciliation of 4066 UNKNOWN capabilities",
               "total_unknown": len(log_records),
               "reconciled_count": len(reconciled), "unresolved_count": len(unresolved),
               "by_project": dict(sorted(by_project.items(), key=lambda kv: -kv[1])),
               "by_domain": dict(sorted(by_domain.items(), key=lambda kv: -kv[1])),
               "by_shared_component": dict(sorted(by_shared.items(), key=lambda kv: -kv[1])),
               "counters": dict(sorted(stats.items())),
               "local_dir_evidence": local_dir_evidence}
    (BASE / "REQUIREMENT_REGISTRY_v3.json").write_text(
        json.dumps(updated, indent=1, ensure_ascii=False), encoding="utf-8")

    # Report.
    def pct(n):
        return f"{100.0 * n / len(log_records):.1f}%" if log_records else "0%"
    lines = ["# UNKNOWN Requirement Reconciliation Report", "", f"Generated: {NOW}",
             f"Input: requirement_registry/unknown/capabilities.json ({len(log_records)} records)", "",
             "## Method",              "Applied AUTO_CLASSIFICATION_KEYWORDS (24 targets) from",
             "UNKNOWN_REQUIREMENT_RECONCILIATION.json: multi-word phrase = weight 2,",
             "single word = weight 1; confidence = 0.35 + 0.14*min(weight,4) + 0.05",
             "exact-name bonus, -0.10 tie, -0.15 short text; thresholds AUTO>=0.9,",
             "REVIEW 0.7-0.9, MANUAL<0.7. Existing projects win ties over domains.",
             "Tiered matching (v2 fix): phrases substring; len<=2 keywords exact word",
             "(ai/ml/ar/vr no longer match said/training/search); data/fea exact word",
             "(database/feature/fear excluded); other keywords word-start anchored",
             "(media no longer matches immediately).",
             "Original registry files untouched; routing staged under",
             "requirement_registry_reconciled/ for owner review.", "",
             "## Results",
             f"- AUTO_ACCEPTED (RECONCILED): {stats['RECONCILED']} ({pct(stats['RECONCILED'])})",
             f"- FLAGGED_FOR_REVIEW (conf 0.7-0.9): {stats['FLAGGED_REVIEW']} ({pct(stats['FLAGGED_REVIEW'])})",
             f"- LOW_CONFIDENCE_ROUTED (routed, conf<0.7, needs review): {stats.get('LOW_CONFIDENCE_ROUTED', 0)}"
             f" ({pct(stats.get('LOW_CONFIDENCE_ROUTED', 0))})",
             f"- MANUAL_REQUIRED (UNCLASSIFIED): {stats['MANUAL_REQUIRED']} ({pct(stats['MANUAL_REQUIRED'])})",
             f"- Duplicates (within UNKNOWN + vs routed): {stats['DUPLICATES_FOUND']}",
             f"- Near-duplicate pairs (Jaccard>=0.75): {near_dup_groups}",
             f"- Supersession-watch: {stats.get('SUPERSESSION_WATCH', 0)}",
             f"- Contradiction-watch flags: {stats.get('CONTRADICTIONS_FLAGGED', 0)}", "",
             "## By project (EXISTING_PROJECT)"]
    for k, v in sorted(by_project.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## By domain (EXISTING_DOMAIN, top 15)")
    for k, v in sorted(by_domain.items(), key=lambda kv: -kv[1])[:15]:
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Other classifications")
    for k in ["RESEARCH_ONLY", "BUSINESS_REQUIREMENT", "POLICY_REQUIREMENT",
              "QUESTION_ONLY", "CONTEXT_ONLY", "AMBIGUOUS", "GENUINELY_UNRESOLVED"]:
        if stats.get(k):
            lines.append(f"- {k}: {stats[k]}")
    lines.append("")
    lines.append("## Repository proposals (NEW_* component types, confidence>=0.7)")
    for k in sorted(k for k in stats if k.startswith("NEW_")):
        lines.append(f"- {k}: {stats[k]}")
    lines.append("")
    lines.append("## Local implementation evidence")
    for k, v in local_dir_evidence.items():
        lines.append(f"- {k}: {'DIR_EXISTS' if v else 'NO_LOCAL_DIR'}")
    lines.append("")
    lines.append("## Integration points")
    lines.append("- TASK_GRAPH_INTEGRATION.json: parent TASK-ROUTE-<PROJECT> + child tasks (PLANNED).")
    lines.append("- REPOSITORY_CREATION_QUEUE_DELTA.json: PROPOSED candidates only.")
    lines.append("- Code cross-reference recomputed per capability (matched_indicators + relevance_score).")
    lines.append("- Next: owner review of FLAGGED/MANUAL queues, then merge staged routing into canonical registry.")
    (BASE / "UNKNOWN_REQUIREMENT_RECONCILIATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")

    print("REGISTERED outputs:")
    for p in ["UNKNOWN_REQUIREMENT_RECONCILIATION_LOG.json", "RECONCILED_REQUIREMENTS.json",
              "UNRESOLVED_REQUIREMENTS.json", "TASK_GRAPH_INTEGRATION.json",
              "REPOSITORY_CREATION_QUEUE_DELTA.json", "REQUIREMENT_REGISTRY_v3.json",
              "UNKNOWN_REQUIREMENT_RECONCILIATION_REPORT.md"]:
        print(f"  {p}")
    print(f"AUTO={stats['RECONCILED']} REVIEW={stats['FLAGGED_REVIEW']} "
          f"MANUAL={stats['MANUAL_REQUIRED']} DUP={stats['DUPLICATES_FOUND']}")


if __name__ == "__main__":
    main()
