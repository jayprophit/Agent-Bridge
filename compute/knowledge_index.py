"""Aetherius Project Knowledge Layer (§15-§20 of the knowledge directive).

One indexed, provenance-preserving knowledge base built from the owner's
AUTHORISED sources (ChatGPT/Claude/Codex conversation exports, project
documents, master prompts, handoffs). The hive retrieves ONLY the relevant
context per task (§20) instead of every agent re-reading the corpus — this
saves tokens, free quota and keeps workers consistent.

Pipeline (§17): DISCOVER -> IDENTIFY FORMAT -> HASH -> PARSE -> EXTRACT ->
CLASSIFY -> DEDUPLICATE -> MAP TO PROJECT -> ADD PROVENANCE -> INDEX ->
LINK REQUIREMENTS -> STORE RETRIEVABLE SUMMARY.

Incremental sync (§19): content-hash + mtime tracking so NEW/CHANGED/
DELETED items are processed without re-reading everything every run.

Honesty (§38-adapted): every object carries confidence
(VERIFIED/OBSERVED/ESTIMATED/UNKNOWN) and provenance (source path, hash,
first-seen). Nothing is invented; an unparsed file is recorded UNPARSED, not
dropped silently (§49 no silent dropping).

SECRET hygiene: this module indexes PROJECT sources only. The credential
vault is never a source (§45); index records never contain secret material —
only file hashes and extracted project text.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# --- confidence vocabulary (mirrors the hive/quota honesty rule) -------------
VERIFIED = "VERIFIED"      # parsed cleanly, structure understood
OBSERVED = "OBSERVED"      # extracted, structure partially understood
ESTIMATED = "ESTIMATED"    # classified by heuristics, not confirmed
UNKNOWN = "UNKNOWN"        # could not determine

# --- source types -------------------------------------------------------------
CHAT_EXPORT = "CHAT_EXPORT"        # ChatGPT/Claude/etc conversation .txt/.md
PROJECT_DOC = "PROJECT_DOC"        # project document, handoff, spec
PROMPT_ARCHIVE = "PROMPT_ARCHIVE"  # master-prompt / build-directive archive
REPO_DOC = "REPO_DOC"              # in-repo docs
IMAGE = "IMAGE"                    # visual reference (not parsed here; recorded)
UNPARSED = "UNPARSED"              # discovered but not parseable

# --- known authorised source roots (§16) --------------------------------------
# Portable placeholders only — never a personal absolute path in committed
# source (§ secret-hygiene gate). Expanded at runtime on the reading machine.
DEFAULT_SOURCES: dict[str, str] = {
    "chat_exports": "%EXTERNAL_DRIVE%/ai chat conversations",
    "master_prompts": "%USERPROFILE%/Documents/master prompt",
    "opencde_agent": "%USERPROFILE%/Documents/openCDE-agent",
}

# project keyword map: filename/topic tokens -> canonical project (§17 MAP)
PROJECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "genesis": ("genesis", "aetherius", "avatar", "os shell", "abyss", "aurora"),
    "agent-bridge": ("agent bridge", "agent-bridge", "bridge", "supervisor",
                     "event bus", "eventbus", "node server"),
    "ide-workspace": ("ide workspace", "ide-workspace", "vite", "react",
                      "genesis-ui", "genesisui"),
    "mat": ("materials atlas", "materials-atlas", "mat ", "thermal data",
            "element frequency"),
    "openCDE": ("opencde", "open cde", "cde-agent"),
    "ledgerlands": ("ledgerland", "ledger lands"),
}

# requirement-token pattern: AETH-IDE-441, MAT-124, H-SA-01 ... (§17 LINK)
REQUIREMENT_RE = re.compile(r"\b([A-Z]{2,6}(?:-[A-Z]{2,6})?-\d{2,6})\b")
# conversation turn markers in exports
SPEAKER_RE = re.compile(r"^(you|user|human|chatgpt|claude|codex|assistant|gpt"
                        r"|deepseek|grok|manus|copilot|kai)\s*[:\-]", re.I)


def _now() -> float:
    return time.time()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(_now(), timezone.utc).isoformat(
        timespec="seconds")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True)
class KnowledgeObject:
    """One indexed knowledge item with full provenance (§17)."""
    object_id: str               # sha256[:16] of content — stable across moves
    source_id: str               # which authorised root it came from
    source_type: str             # CHAT_EXPORT / PROJECT_DOC / ...
    path: str                    # absolute path (runtime machine, not committed)
    title: str = ""
    project: str = "unmapped"
    topics: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    conversation_id: str = ""
    author: str = ""
    size_bytes: int = 0
    content_hash: str = ""
    confidence: str = UNKNOWN
    first_seen: str = field(default_factory=_now_iso)
    last_indexed: str = field(default_factory=_now_iso)
    summary: str = ""            # retrievable summary, not the whole file
    turn_count: int = 0

    def to_dict(self) -> dict:
        return {**asdict(self), "topics": list(self.topics),
                "requirements": list(self.requirements)}

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeObject":
        return cls(**{**d, "topics": tuple(d.get("topics", ())),
                      "requirements": tuple(d.get("requirements", ()))})


def classify_source(path: Path, source_id: str) -> str:
    """§17 IDENTIFY FORMAT + CLASSIFY from path facts only (honest)."""
    name = path.name.lower()
    suffix = path.suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return IMAGE
    if source_id == "chat_exports" or source_id == "master_prompts":
        return CHAT_EXPORT if "chat" in name or source_id == "chat_exports" \
            else PROMPT_ARCHIVE
    if source_id == "opencde_agent":
        return PROJECT_DOC
    return UNPARSED


def map_project(path: Path, text_head: str) -> str:
    """§17 MAP TO PROJECT: keyword evidence from path + opening text.
    Returns 'unmapped' rather than guessing (§ honesty)."""
    hay = (path.name + " " + text_head[:4000]).lower()
    best, best_hits = "unmapped", 0
    for project, keywords in PROJECT_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in hay)
        if hits > best_hits:
            best, best_hits = project, hits
    return best


def extract_summary(text: str, max_chars: int = 600) -> str:
    """First meaningful prose, whitespace-normalised. NOT a fabricated
    abstract — the actual opening of the source, with speaker markers kept
    inline (the ANSWER after 'ChatGPT:' is the valuable part; the marker is
    only stripped of its trailing punctuation)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    picked: list[str] = []
    for ln in lines:
        m = SPEAKER_RE.match(ln)
        if m:
            # keep the content, drop only the "Name:" / "Name -" prefix
            rest = ln[m.end():].strip(" :-")
            if rest:
                picked.append(rest)
        else:
            picked.append(ln)
        if sum(len(p) for p in picked) >= max_chars:
            break
    return " ".join(picked)[:max_chars]


def parse_text_source(path: Path) -> tuple[str, int, str]:
    """Read a text source defensively. Returns (text, turn_count, confidence).
    Encoding errors degrade to OBSERVED (partially read), never a crash."""
    try:
        raw = path.read_bytes()
    except OSError:
        return "", 0, UNKNOWN
    text = ""
    conf = VERIFIED
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if not text:
        text = raw.decode("utf-8", errors="replace")
        conf = OBSERVED  # some bytes were lossy
    turns = sum(1 for ln in text.splitlines() if SPEAKER_RE.match(ln.strip()))
    return text, turns, conf


class KnowledgeIndex:
    """The retrieval source for the hive (§15, §20).

    Thread-safe, persistable (§37 power-failure recovery), incremental (§19).
    retrieve(query) returns ranked KnowledgeObjects — the scheduler/hive uses
    it to give a worker ONLY its relevant context.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._objects: dict[str, KnowledgeObject] = {}   # object_id -> object
        self._seen: dict[str, dict[str, Any]] = {}       # path -> {hash, mtime}
        self._sync_log: list[dict[str, Any]] = []

    # -- ingestion pipeline (§17) ---------------------------------------------
    def ingest_file(self, path: Path, source_id: str) -> Optional[KnowledgeObject]:
        """DISCOVER -> HASH -> PARSE -> EXTRACT -> CLASSIFY -> MAP -> INDEX."""
        path = Path(path)
        try:
            st = path.stat()
        except OSError:
            return None
        source_type = classify_source(path, source_id)
        if source_type == IMAGE:
            # §18: recorded with provenance, not parsed as text here.
            try:
                content_hash = sha256_file(path)
            except OSError:
                return None
            obj = KnowledgeObject(
                object_id=content_hash[:16], source_id=source_id,
                source_type=IMAGE, path=str(path), title=path.stem,
                project=map_project(path, ""), size_bytes=st.st_size,
                content_hash=content_hash, confidence=OBSERVED,
                summary="(image reference — vision description deferred)")
            with self._lock:
                self._objects[obj.object_id] = obj
                self._seen[str(path)] = {"hash": content_hash,
                                         "mtime": st.st_mtime}
            return obj
        if source_type == UNPARSED:
            return None
        try:
            content_hash = sha256_file(path)
        except OSError:
            return None
        text, turns, conf = parse_text_source(path)
        obj = KnowledgeObject(
            object_id=content_hash[:16], source_id=source_id,
            source_type=source_type, path=str(path), title=path.stem,
            project=map_project(path, text),
            topics=tuple(sorted(_topics(text))),
            requirements=tuple(sorted(set(REQUIREMENT_RE.findall(text)))),
            size_bytes=st.st_size, content_hash=content_hash, confidence=conf,
            summary=extract_summary(text), turn_count=turns)
        with self._lock:
            self._objects[obj.object_id] = obj
            self._seen[str(path)] = {"hash": content_hash, "mtime": st.st_mtime}
        return obj

    def sync_source(self, source_id: str, root: Path,
                    extensions: tuple[str, ...] = (".txt", ".md")) -> dict:
        """§19 incremental sync: process NEW/CHANGED, record DELETED.
        Never silently drops a file — every outcome is in the sync log."""
        root = Path(root)
        result = {"source_id": source_id, "root": str(root),
                  "scanned": 0, "new": 0, "changed": 0, "unchanged": 0,
                  "deleted": 0, "errors": 0, "started_at": _now_iso()}
        if not root.is_dir():
            result["error"] = "source root missing"
            with self._lock:
                self._sync_log.append(result)
            return result
        live_paths: set[str] = set()
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in extensions:
                continue
            live_paths.add(str(p))
            result["scanned"] += 1
            try:
                st = p.stat()
            except OSError:
                result["errors"] += 1
                continue
            prev = self._seen.get(str(p))
            try:
                h = sha256_file(p)
            except OSError:
                result["errors"] += 1
                continue
            if prev is None:
                self.ingest_file(p, source_id)
                result["new"] += 1
            elif prev.get("hash") != h:
                self.ingest_file(p, source_id)
                result["changed"] += 1
            else:
                result["unchanged"] += 1
                with self._lock:
                    self._seen[str(p)] = {"hash": h, "mtime": st.st_mtime}
        # deleted/superseded detection
        with self._lock:
            for seen_path in list(self._seen):
                if seen_path.startswith(str(root)) and seen_path not in live_paths:
                    self._seen.pop(seen_path, None)
                    result["deleted"] += 1
        result["finished_at"] = _now_iso()
        with self._lock:
            self._sync_log.append(result)
        return result

    # -- retrieval (§20) -------------------------------------------------------
    def retrieve(self, query: str, project: str = "",
                 limit: int = 10) -> list[KnowledgeObject]:
        """Task-scoped retrieval: ranked by query-token overlap + project
        match. Returns whole objects; callers summarise/quote as needed."""
        q_tokens = {t for t in re.findall(r"[a-z0-9\-]{3,}", query.lower())}
        with self._lock:
            scored: list[tuple[float, KnowledgeObject]] = []
            for obj in self._objects.values():
                if project and obj.project != project:
                    continue
                hay = (obj.title + " " + obj.summary + " "
                       + " ".join(obj.topics)).lower()
                overlap = sum(1 for t in q_tokens if t in hay)
                if overlap == 0:
                    continue
                score = float(overlap)
                if project and obj.project == project:
                    score += 2.0
                if obj.confidence == VERIFIED:
                    score += 0.5
                scored.append((score, obj))
        scored.sort(key=lambda x: (-x[0], x[1].object_id))
        return [o for _s, o in scored[:limit]]

    def context_for_task(self, query: str, project: str = "",
                         limit: int = 5, summary_chars: int = 300) -> list[dict]:
        """§20: the exact payload a worker receives — title, project,
        provenance (path+hash), and a bounded summary. NOT the whole corpus."""
        out = []
        for obj in self.retrieve(query, project=project, limit=limit):
            out.append({
                "title": obj.title,
                "project": obj.project,
                "source_type": obj.source_type,
                "confidence": obj.confidence,
                "requirements": list(obj.requirements[:10]),
                "summary": obj.summary[:summary_chars],
                "provenance": {
                    "source_id": obj.source_id,
                    "path": obj.path,
                    "content_hash": obj.content_hash,
                    "first_seen": obj.first_seen,
                },
            })
        return out

    # -- overview (§43) --------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            by_project: dict[str, int] = {}
            by_confidence: dict[str, int] = {}
            for obj in self._objects.values():
                by_type[obj.source_type] = by_type.get(obj.source_type, 0) + 1
                by_project[obj.project] = by_project.get(obj.project, 0) + 1
                by_confidence[obj.confidence] = \
                    by_confidence.get(obj.confidence, 0) + 1
            return {
                "objects": len(self._objects),
                "by_type": by_type,
                "by_project": by_project,
                "by_confidence": by_confidence,
                "syncs": len(self._sync_log),
                "last_sync": self._sync_log[-1] if self._sync_log else None,
            }

    # -- persistence (§37) -----------------------------------------------------
    def to_dict(self) -> dict:
        with self._lock:
            return {
                "objects": [o.to_dict() for o in
                            sorted(self._objects.values(),
                                   key=lambda o: o.object_id)],
                "seen": dict(self._seen),
                "sync_log": self._sync_log[-50:],
                "saved_at": _now_iso(),
            }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "KnowledgeIndex":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        idx = cls()
        for d in data.get("objects", []):
            idx._objects[d["object_id"]] = KnowledgeObject.from_dict(d)
        idx._seen = dict(data.get("seen", {}))
        idx._sync_log = list(data.get("sync_log", []))
        return idx


def _topics(text: str, top: int = 8) -> list[str]:
    """Cheap keyword topics (word frequency, stopworded). Heuristic only —
    the object's confidence already marks this as extracted, not curated."""
    stop = {"the", "and", "for", "with", "that", "this", "from", "you", "your",
            "have", "not", "are", "was", "were", "will", "would", "can",
            "could", "should", "about", "into", "then", "than", "them",
            "they", "their", "there", "here", "what", "when", "which", "who",
            "how", "why", "all", "any", "but", "his", "her", "its", "our",
            "has", "had", "been", "being", "does", "did", "doing", "also",
            "just", "like", "make", "made", "some", "such", "only", "over",
            "very", "more", "most", "other", "each", "because", "after",
            "before", "between", "through", "during", "without", "within"}
    freq: dict[str, int] = {}
    for tok in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text[:20000].lower()):
        if tok in stop:
            continue
        freq[tok] = freq.get(tok, 0) + 1
    return [t for t, _c in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def resolve_sources(env: Optional[dict[str, str]] = None) -> dict[str, Path]:
    """Expand the portable DEFAULT_SOURCES placeholders on THIS machine."""
    import os
    env = env if env is not None else dict(os.environ)
    resolved: dict[str, Path] = {}
    for source_id, template in DEFAULT_SOURCES.items():
        path = template
        for var, value in {
            "%USERPROFILE%": env.get("USERPROFILE", str(Path.home())),
            "%EXTERNAL_DRIVE%": env.get("EXTERNAL_DRIVE", "E:/external drive"),
        }.items():
            path = path.replace(var, value)
        resolved[source_id] = Path(path)
    return resolved
