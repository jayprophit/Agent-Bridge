"""AI-conversation ingestion audit (Phase 1.1, Part B).

Proves WHICH files were read and HOW WELL — not just counts. For every
discovered conversation/export source records: paths, provider, type,
size, SHA256, parser, parse status, entries extracted, conversation
heuristics, timestamps, project mappings, errors, warnings, privacy and
ingestion status.

Honesty rules enforced here:
- The normalizer (knowledge_ingestion.py) splits on blank lines and
  truncates chunks at 2000 chars with no role/timestamp segmentation.
  Such files are PARTIALLY_PARSED, never FULLY_PARSED.
- FULLY_PARSED requires: every byte represented in the normalized output
  (no truncation) AND roles/timestamps preserved where present.
- Anything else gets UNSUPPORTED / CORRUPT / EMPTY / DUPLICATE /
  NOT_A_CONVERSATION / REQUIRES_REVIEW as appropriate.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(r"E:\OpenCode-Data\Knowledge")
CONVERSATIONS_ROOT = Path(r"E:\external drive\ai chat conversations")
NORMALIZED_PATH = KNOWLEDGE_DIR / "ai_conversations.json"
AUDIT_JSON = KNOWLEDGE_DIR / "AI-CONVERSATION-INGESTION-AUDIT.json"
AUDIT_MD = KNOWLEDGE_DIR / "AI-CONVERSATION-INGESTION-AUDIT.md"

PARSER_NAME = "knowledge_ingestion.py:process_conversation_file"
PARSER_KNOWN_LIMITS = [
    "splits on blank lines only; no message/role segmentation",
    "chunk content truncated at 2000 chars",
    "no timestamp extraction",
    "no code-block / attachment / link extraction",
    "no conversation boundary detection",
]

PROVIDER_BY_DIR = {
    "chatgpt": "ChatGPT", "claude": "Claude", "deepseek": "DeepSeek",
    "co-pilot": "Copilot", "grok": "Grok", "manus": "Manus",
    "other": "Other",
    "ai studio googls vibe coding": "AI Studio (Google)",
}

ROLE_MARKERS = ("user:", "human:", "you:", "assistant:", "ai:", "claude:",
                "chatgpt:", "model:", "\nhuman ", "\nassistant ")
TIMESTAMP_RES = (
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"),
    re.compile(r"\b\d{1,2}:\d{2}\s*(AM|PM)\b", re.IGNORECASE),
)
CHAT_INDICATORS = (
    "chatgpt", "claude", "gemini", "deepseek", "manus", "grok", "copilot",
    "perplexity", "opencode", "conversation", "assistant:", "human:",
    "prompt:", "claude.ai", "chat.openai",
)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def conversation_heuristic(text: str) -> int:
    """Rough turn-pair count from role markers. 0 = no detectable dialogue."""
    low = text.lower()
    hits = sum(low.count(m.strip()) for m in ROLE_MARKERS)
    return hits // 2


def timestamps_heuristic(text: str) -> dict[str, Any]:
    found: list[str] = []
    for rx in TIMESTAMP_RES:
        found.extend(m.group(0) for m in rx.finditer(text[:20000]))
    uniq = sorted(set(found))[:10]
    return {"count": len(uniq), "sample": uniq}


def looks_like_conversation(path: Path, head: str) -> bool:
    name = path.name.lower()
    if any(k in name for k in CHAT_INDICATORS):
        return True
    low = head.lower()
    return any(k in low for k in CHAT_INDICATORS)


def audit() -> dict[str, Any]:
    normalized: list[dict[str, Any]] = []
    if NORMALIZED_PATH.exists():
        normalized = json.loads(NORMALIZED_PATH.read_text(encoding="utf-8"))
    per_file: dict[str, list[dict[str, Any]]] = {}
    for e in normalized:
        per_file.setdefault(str(e.get("source_file", "")), []).append(e)

    records: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}
    counters: Counter = Counter()

    files = sorted(CONVERSATIONS_ROOT.rglob("*")) if CONVERSATIONS_ROOT.exists() else []
    for path in files:
        if not path.is_file():
            continue
        size = path.stat().st_size
        digest = sha256_of(path)
        rel_parent = path.parent.name
        provider = PROVIDER_BY_DIR.get(rel_parent,
                                       PROVIDER_BY_DIR.get(path.parent.parent.name, "Unknown"))
        file_type = path.suffix.lower() or "no-extension"
        entries = per_file.get(str(path), [])
        errors: list[str] = []
        warnings = list(PARSER_KNOWN_LIMITS)
        status = ""
        ingestion = ""

        if size == 0:
            status, ingestion = "EMPTY", "EMPTY"
        elif digest in seen_hashes:
            status = "DUPLICATE"
            ingestion = f"DUPLICATE of {seen_hashes[digest]}"
        else:
            seen_hashes[digest] = str(path)
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (OSError, ValueError) as exc:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    warnings.append(f"non-UTF8 bytes replaced: {exc}")
                except OSError as exc2:
                    errors.append(str(exc2))
                    text = ""
                    status, ingestion = "CORRUPT", "CORRUPT"
            if not status:
                if not text.strip():
                    status, ingestion = "EMPTY", "EMPTY"
                elif file_type not in (".txt", ".md"):
                    from models.knowledge_ingestion import JSON_PARSER
                    json_entries = [e for e in entries
                                    if e.get("parser") == JSON_PARSER]
                    if json_entries and \
                            path.name == "conversations.json" and \
                            "aetherius-data" in str(path):
                        if all(not e.get("truncated") for e in json_entries):
                            status = "FULLY_PARSED"
                            ingestion = (
                                f"{len(json_entries)} per-message entries; "
                                "roles+timestamps preserved, no truncation")
                        else:
                            status = "PARTIALLY_PARSED"
                            ingestion = (
                                f"{len(json_entries)} per-message entries; "
                                "roles+timestamps preserved, "
                                "long messages truncated at 2000 chars")
                    else:
                        status = "UNSUPPORTED"
                        ingestion = f"UNSUPPORTED format {file_type}"
                        if entries:
                            warnings.append(
                                "entries exist despite unsupported format")
                elif not looks_like_conversation(path, text[:4000]):
                    status = "NOT_A_CONVERSATION"
                    ingestion = ("parsed as text but no conversation indicators; "
                                 f"{len(entries)} entries extracted")
                elif not entries:
                    status = "REQUIRES_REVIEW"
                    ingestion = "no entries extracted; requires review"
                else:
                    truncated = size > 2000 and any(
                        len(str(e.get("content", ""))) >= 2000 for e in entries)
                    if truncated:
                        warnings.append("chunk truncation occurred (>2000 chars)")
                    status = "PARTIALLY_PARSED"
                    ingestion = (f"{len(entries)} entries via blank-line splitter; "
                                 "roles/timestamps not segmented")

        conv_count = conversation_heuristic(text) if "text" in dir() and text else 0
        ts = timestamps_heuristic(text) if "text" in dir() and text else {"count": 0, "sample": []}
        projects = sorted({p for e in entries for p in (e.get("project_relevance") or [])})
        cats = Counter()
        for e in entries:
            for c in str(e.get("category", "")).split(", "):
                if c:
                    cats[c] += 1

        records.append({
            "original_path": str(path),
            "current_path": str(path),  # chats were read in place; never moved to git
            "provider": provider,
            "filename": path.name,
            "file_type": file_type,
            "size": size,
            "sha256": digest,
            "parser": PARSER_NAME,
            "parse_status": status,
            "entries_extracted": len(entries),
            "conversation_count": conv_count,
            "first_timestamp": ts["sample"][0] if ts["sample"] else None,
            "last_timestamp": ts["sample"][-1] if ts["sample"] else None,
            "project_mappings": projects,
            "category_counts": dict(cats),
            "errors": errors,
            "warnings": warnings,
            "privacy_status": "PRIVATE - raw chat stays on E:, never in git",
            "ingestion_status": ingestion,
        })
        counters[status] += 1

    # Normalized entries whose source file no longer exists (moved/deleted).
    known = {r["original_path"] for r in records}
    orphaned = [s for s in per_file if s not in known]
    summary = {
        "parser": PARSER_NAME,
        "parser_known_limits": PARSER_KNOWN_LIMITS,
        "files_discovered": len(records),
        "status_counts": dict(counters),
        "normalized_entries_total": len(normalized),
        "orphaned_sources": orphaned,
        "fully_parsed": counters.get("FULLY_PARSED", 0),
    }
    AUDIT_JSON.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps({"summary": summary, "records": records},
                                     indent=1), encoding="utf-8")
    _write_md(summary, records)
    print(f"Audited {len(records)} files; statuses={dict(counters)}; "
          f"orphaned={len(orphaned)}")
    return {"summary": summary, "records": records}


def _write_md(summary: dict[str, Any], records: list[dict[str, Any]]) -> None:
    lines = ["# AI Conversation Ingestion Audit", "",
             f"Parser: `{summary['parser']}`", "",
             "## Parser known limits (honesty statement)", ""]
    lines += [f"- {lim}" for lim in summary["parser_known_limits"]]
    lines += ["", "## Summary", "",
              f"- files discovered: {summary['files_discovered']}",
              f"- normalized entries: {summary['normalized_entries_total']}",
              f"- FULLY_PARSED: {summary['fully_parsed']} (expected 0 — "
              "the splitter cannot fully parse)", ""]
    lines += ["| status | count |", "|---|---|"]
    for k, v in sorted(summary["status_counts"].items()):
        lines.append(f"| {k} | {v} |")
    lines += ["", f"Orphaned sources: {len(summary['orphaned_sources'])}"]
    for o in summary["orphaned_sources"][:20]:
        lines.append(f"- {o}")
    lines += ["", "## Per-file records (see JSON for full detail)", ""]
    lines += ["| file | provider | size | sha256⋯ | status | entries | projects |",
              "|---|---|---|---|---|---|---|"]
    for r in records:
        lines.append(
            f"| {r['filename']} | {r['provider']} | {r['size']} | "
            f"{r['sha256'][:12]}⋯ | {r['parse_status']} | "
            f"{r['entries_extracted']} | {','.join(r['project_mappings'])} |")
    AUDIT_MD.write_text("\n".join(lines), encoding="utf-8")


def sweep_missed_sources(roots: list[Path] | None = None,
                         max_depth: int = 3,
                         max_hits: int = 200) -> dict[str, Any]:
    """Bounded sweep for AI-export candidates outside the audited tree.

    Searches folder names, extensions and content indicators only in the
    given roots (defaults to authorised E: knowledge/resource locations).
    Never crawls unrelated personal areas.
    """
    if roots is None:
        roots = [Path(r"E:\external drive"), Path(r"E:\OpenCode-Data")]
    audited = set()
    if AUDIT_JSON.exists():
        try:
            data = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
            audited = {r["original_path"] for r in data.get("records", [])}
        except ValueError:
            pass
    hits: list[dict[str, Any]] = []
    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        base_depth = len(root.parts)
        for path in sorted(root.rglob("*")):
            if len(path.parts) - base_depth > max_depth:
                continue
            if not path.is_file():
                continue
            scanned += 1
            if str(path) in audited:
                continue
            name = path.name.lower()
            if path.suffix.lower() not in (".txt", ".md", ".json", ".html"):
                continue
            if "ai chat conversations" in str(path).lower():
                continue  # audited tree
            try:
                if path.stat().st_size > 5_000_000:
                    continue
                head = path.read_text(encoding="utf-8",
                                      errors="ignore")[:4000].lower()
            except OSError:
                continue
            if any(k in name for k in CHAT_INDICATORS) or \
                    sum(head.count(k) for k in CHAT_INDICATORS) >= 3:
                hits.append({"path": str(path), "size": path.stat().st_size,
                             "reason": "name/content indicators"})
                if len(hits) >= max_hits:
                    break
    return {"roots": [str(r) for r in roots], "max_depth": max_depth,
            "files_scanned": scanned, "candidates": hits}


if __name__ == "__main__":
    audit()
