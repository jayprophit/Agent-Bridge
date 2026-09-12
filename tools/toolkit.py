"""Capability negotiation (v0.7). Task -> bounded relevant-tool shortlist.

Small models never receive the whole registry: at most `limit` tool IDs
plus compact one-line schemas. tools.search covers the rest.
"""
from __future__ import annotations

INTENT_KEYWORDS: dict[str, list[str]] = {
    "filesystem": ["file", "read", "write", "folder", "directory", "path",
                   "save", "create file", "list files"],
    "shell": ["run", "command", "execute", "terminal", "script output"],
    "code": ["code", "function", "refactor", "debug", "lint", "compile"],
    "test": ["test", "pytest", "unittest", "coverage", "pass", "fail"],
    "browser": ["browser", "web page", "website", "click", "scroll", "title"],
    "http": ["fetch", "download", "url", "http", "webpage", "website"],
    "speech": ["speak", "say", "voice", "read aloud", "tts", "talk"],
    "predictive": ["complete", "suggest", "autocomplete", "predict", "continue"],
    "image": ["image", "picture", "generate art", "draw", "photo"],
    "data": ["json", "csv", "data", "convert", "parse", "spreadsheet"],
    "search": ["search", "find", "lookup", "query"],
    "git": ["git", "commit", "repo", "branch", "push"],
    "process": ["process", "launch", "app", "program", "pid"],
    "system": ["system", "cpu", "ram", "admin", "drives", "version"],
    "document": ["document", "pdf", "read doc", "manual"],
    "archive": ["zip", "archive", "extract", "compress"],
    "database": ["database", "sqlite", "sql", "query table"],
    "science": ["celsius", "fahrenheit", "units", "convert", "calculate"],
    "citation": ["cite", "citation", "reference", "source", "provenance"],
    "memory": ["remember", "recall", "memory"],
    "model": ["model", "which models", "available"],
}


def negotiate(task_text: str, registry, limit: int = 12,
              include_always: tuple[str, ...] = ("tools.list", "tools.search",
                                                 "tools.describe")) -> list[str]:
    """Task -> relevant capability shortlist. Bounded for small models."""
    text = (task_text or "").lower()
    scores: dict[str, int] = {}
    for tool_id in registry.ids():
        fam = tool_id.split(".")[0]
        rec = registry.get(tool_id)
        score = 0
        for kw in INTENT_KEYWORDS.get(fam, []):
            if kw in text:
                score += 2
        for tag in rec.capability_tags:
            if tag.lower() in text:
                score += 1
        if tool_id in include_always:
            score += 100
        if score:
            scores[tool_id] = score
    ranked = sorted(scores, key=lambda t: (-scores[t], t))
    return ranked[:limit]


def short_schemas(registry, tool_ids: list[str],
                  max_chars: int = 3000) -> str:
    """Compact schema text for small-model prompts (bounded)."""
    lines = []
    total = 0
    for tid in tool_ids:
        try:
            rec = registry.get(tid)
        except KeyError:
            continue
        args = ", ".join(sorted((rec.input_schema or {}).get("properties", {}).keys()))
        line = f"- {tid}({args}) [{rec.status}]"
        if total + len(line) > max_chars:
            lines.append(f"...[{len(tool_ids) - len(lines)} more via tools.search]")
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)
