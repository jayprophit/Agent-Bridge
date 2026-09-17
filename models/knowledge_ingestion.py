"""AI Conversation Knowledge Ingestion System.

Reads AI conversation exports from E:\\external drive\\ai chat conversations\\
and extracts structured knowledge: OWNER_CORRECTION, ARCHITECTURE_DECISION,
FEATURE_REQUIREMENT, AMENDMENT, TODO, IMPLEMENTED, VERIFIED, BUG,
REJECTED_DESIGN, FUTURE_IDEA, MIGRATION_SOURCE, ACCEPTANCE_GATE.

Maps extracted knowledge to current projects.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeEntry:
    """A single extracted knowledge item from AI conversations."""
    entry_id: str = field(default_factory=lambda: "kn-" + uuid.uuid4().hex[:10])
    source_file: str = ""
    source_provider: str = ""  # chatgpt, claude, deepseek, etc.
    timestamp: str = ""
    category: str = ""  # OWNER_CORRECTION, ARCHITECTURE_DECISION, etc.
    content: str = ""
    project_relevance: list[str] = field(default_factory=list)  # genesis, aetherious, poietek, universal-bridge, mat, agent-bridge
    extracted_tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    actionable: bool = False
    suggested_task: str = ""
    parser: str = ""  # which parser produced this entry
    role: str = ""  # speaker role where the parser preserves it
    truncated: bool = False  # True if source text exceeded storage cap


SPLITTER_PARSER = "blank-line splitter (no roles/timestamps, 2000-char cap)"
JSON_PARSER = "json_export_parser (roles+timestamps preserved)"


# Pattern to identify knowledge categories
CATEGORY_PATTERNS = {
    "OWNER_CORRECTION": [
        r"owner correction", r"correction:", r"you are wrong", r"that's incorrect",
        r"actually,", r"correction:", r"please note:", r"important correction",
    ],
    "ARCHITECTURE_DECISION": [
        r"architecture decision", r"architectural decision", r"design decision",
        r"we will use", r"chosen approach", r"decided to", r"approach:",
        r"architecture:", r"system design",
    ],
    "FEATURE_REQUIREMENT": [
        r"feature request", r"requirement:", r"must have", r"should implement",
        r"need to add", r"feature:", r"requirement", r"specification:",
    ],
    "AMENDMENT": [
        r"amendment", r"update:", r"revised:", r"changed my mind",
        r"actually, let me", r"correction to previous",
    ],
    "TODO": [
        r"todo:", r"to do:", r"need to implement", r"should do",
        r"next step", r"action item", r"follow up",
    ],
    "IMPLEMENTED": [
        r"implemented", r"completed", r"done:", r"finished",
        r"working now", r"verified working",
    ],
    "VERIFIED": [
        r"verified", r"tested and working", r"confirmed working",
        r"passes tests", r"validation complete",
    ],
    "BUG": [
        r"bug:", r"issue:", r"problem:", r"error:", r"fails",
        r"doesn't work", r"broken",
    ],
    "REJECTED_DESIGN": [
        r"rejected", r"not viable", r"won't work", r"discard",
        r"abandon", r"not feasible",
    ],
    "FUTURE_IDEA": [
        r"future:", r"someday", r"eventually", r"later we could",
        r"idea for later", r"potential future",
    ],
    "MIGRATION_SOURCE": [
        r"migrate from", r"port from", r"move from", r"legacy",
        r"old version", r"previous implementation",
    ],
    "ACCEPTANCE_GATE": [
        r"acceptance criteria", r"gate:", r"must pass", r"definition of done",
        r"acceptance test", r"verification criteria",
    ],
}


# Project relevance keywords
PROJECT_KEYWORDS = {
    "genesis": ["genesis", "ai digital twin", "nanobrain", "wbe", "identity", "spiritual body", "processor", "shell", "avatar"],
    "aetherious": ["aetherious", "aetherius", "quantum os", "holographic os", "kernel", "operating system", "boot", "filesystem"],
    "poietek": ["poietek", "daw", "audio", "mixer", "timeline", "recording", "midi", "plugin", "studio", "sds"],
    "universal-bridge": ["universal bridge", "mpc", "akai", "midi device", "hardware bridge", "device communication", "stem transfer"],
    "mat": ["mat", "materials atlas", "periodic table", "elements", "chemistry", "isotopes"],
    "agent-bridge": ["agent bridge", "model routing", "delegation", "worker model", "bridge", "orchestration"],
}


def classify_category(text: str) -> list[str]:
    """Classify text into knowledge categories."""
    text_lower = text.lower()
    matches = []
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_lower):
                matches.append(category)
                break
    return matches if matches else ["UNCLASSIFIED"]


def detect_project_relevance(text: str) -> list[str]:
    """Detect which projects the text is relevant to."""
    text_lower = text.lower()
    projects = []
    for project, keywords in PROJECT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text_lower:
                projects.append(project)
                break
    return projects


def extract_tags(text: str) -> list[str]:
    """Extract relevant tags from text."""
    tags = []
    # Technical tags
    tech_patterns = [
        (r"\b(python|rust|typescript|javascript|go|c\+\+|c#)\b", "language"),
        (r"\b(react|vue|svelte|angular)\b", "frontend"),
        (r"\b(docker|kubernetes|k8s)\b", "containerization"),
        (r"\b(ollama|llama|gpt|claude|gemini)\b", "llm"),
        (r"\b(midi|audio|daw|vst)\b", "audio"),
        (r"\b(usb|midi|cc|nrpn|sysex)\b", "hardware"),
        (r"\b(git|github|ci/cd|pipeline)\b", "devops"),
        (r"\b(test|benchmark|benchmarking)\b", "testing"),
        (r"\b(security|encryption|auth)\b", "security"),
    ]
    text_lower = text.lower()
    for pattern, tag in tech_patterns:
        if re.search(pattern, text_lower):
            tags.append(tag)
    return tags


def process_conversation_file(file_path: Path, provider: str) -> list[KnowledgeEntry]:
    """Process a single conversation file and extract knowledge entries."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    if not content.strip():
        return []
    
    # Split into chunks (by double newline or significant breaks)
    chunks = re.split(r'\n\s*\n', content)
    
    entries = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if len(chunk) < 50:  # Skip very short chunks
            continue
        
        categories = classify_category(chunk)
        projects = detect_project_relevance(chunk)
        tags = extract_tags(chunk)
        
        # Calculate confidence based on category strength and project relevance
        confidence = 0.0
        if "UNCLASSIFIED" not in categories:
            confidence += 0.5
        if projects:
            confidence += 0.3
        if tags:
            confidence += 0.2
        
        # Determine if actionable
        actionable = any(c in categories for c in [
            "OWNER_CORRECTION", "FEATURE_REQUIREMENT", "TODO", "BUG",
            "ARCHITECTURE_DECISION", "AMENDMENT"
        ])
        
        # Generate suggested task for actionable items
        suggested_task = ""
        if actionable:
            if "FEATURE_REQUIREMENT" in categories:
                suggested_task = f"Implement feature: {chunk[:100]}..."
            elif "BUG" in categories:
                suggested_task = f"Fix bug: {chunk[:100]}..."
            elif "TODO" in categories:
                suggested_task = f"Complete todo: {chunk[:100]}..."
            elif "OWNER_CORRECTION" in categories:
                suggested_task = f"Address owner correction: {chunk[:100]}..."
            elif "ARCHITECTURE_DECISION" in categories:
                suggested_task = f"Implement architecture decision: {chunk[:100]}..."
        
        entry = KnowledgeEntry(
            source_file=str(file_path),
            source_provider=provider,
            category=", ".join(categories),
            content=chunk[:2000],  # Truncate for storage
            project_relevance=projects,
            extracted_tags=tags,
            confidence=confidence,
            actionable=actionable,
            suggested_task=suggested_task,
            parser=SPLITTER_PARSER,
            truncated=len(chunk) > 2000,
        )
        entries.append(entry)
    
    return entries


def ingest_ai_conversations(
    base_path: Path = Path(r"E:\external drive\ai chat conversations"),
    output_path: Path = Path(r"E:\OpenCode-Data\Knowledge\ai_conversations.json"),
) -> dict[str, Any]:
    """Ingest all AI conversation files and produce structured knowledge base."""
    providers = [
        "chatgpt", "claude", "deepseek", "co-pilot", "grok", 
        "manus", "other", "ai studio googls vibe coding"
    ]
    
    all_entries = []
    stats = {"files_processed": 0, "entries_extracted": 0, "by_provider": {}, "by_category": {}, "by_project": {}}
    
    for provider in providers:
        provider_path = base_path / provider
        if not provider_path.exists():
            continue
        
        provider_entries = 0
        provider_categories = {}
        provider_projects = {}
        
        for file_path in provider_path.rglob("*.txt"):
            try:
                entries = process_conversation_file(file_path, provider)
                all_entries.extend(entries)
                provider_entries += len(entries)
                stats["entries_extracted"] += len(entries)
                
                for entry in entries:
                    for cat in entry.category.split(", "):
                        provider_categories[cat] = provider_categories.get(cat, 0) + 1
                        stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
                    for proj in entry.project_relevance:
                        provider_projects[proj] = provider_projects.get(proj, 0) + 1
                        stats["by_project"][proj] = stats["by_project"].get(proj, 0) + 1
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
        
        stats["by_provider"][provider] = {
            "files": len(list(provider_path.rglob("*.txt"))),
            "entries": provider_entries,
            "categories": provider_categories,
            "projects": provider_projects,
        }
        stats["files_processed"] += len(list(provider_path.rglob("*.txt")))
    
    # Also process loose txt files in root
    for file_path in base_path.glob("*.txt"):
        try:
            entries = process_conversation_file(file_path, "root")
            all_entries.extend(entries)
            stats["entries_extracted"] += len(entries)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")

    # Structured JSON conversation exports (missed by the txt splitter).
    try:
        json_entries = parse_conversation_json_exports(base_path)
        all_entries.extend(json_entries)
        stats["entries_extracted"] += len(json_entries)
        stats["json_export_entries"] = len(json_entries)
        stats["json_export_files"] = 2
    except Exception as e:
        print(f"Error processing JSON exports: {e}")
        stats["json_export_entries"] = 0

    # Save knowledge base
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([asdict(e) for e in all_entries], indent=2, default=str),
        encoding="utf-8"
    )
    
    # Save stats
    stats_path = output_path.parent / "ingestion_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2, default=str), encoding="utf-8")
    
    # Generate actionable tasks
    actionable = [e for e in all_entries if e.actionable]
    tasks_path = output_path.parent / "actionable_tasks.json"
    tasks_path.write_text(
        json.dumps([asdict(e) for e in actionable], indent=2, default=str),
        encoding="utf-8"
    )
    
    print(f"Ingestion complete:")
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Entries extracted: {stats['entries_extracted']}")
    print(f"  Actionable tasks: {len(actionable)}")
    print(f"  Knowledge base saved to: {output_path}")
    print(f"  Stats saved to: {stats_path}")
    print(f"  Actionable tasks saved to: {tasks_path}")
    
    return {"entries": all_entries, "stats": stats}


def _make_message_entry(source_file: str, provider: str, role: str,
                          timestamp: str, text: str) -> KnowledgeEntry | None:
    """Build one entry per message. Returns None for empty messages."""
    text = (text or "").strip()
    if not text:
        return None
    categories = classify_category(text)
    projects = detect_project_relevance(text)
    tags = extract_tags(text)
    confidence = 0.0
    if "UNCLASSIFIED" not in categories:
        confidence += 0.5
    if projects:
        confidence += 0.3
    if tags:
        confidence += 0.2
    if role:
        confidence = min(1.0, confidence + 0.1)  # role preserved = evidence
    actionable = any(c in categories for c in [
        "OWNER_CORRECTION", "FEATURE_REQUIREMENT", "TODO", "BUG",
        "ARCHITECTURE_DECISION", "AMENDMENT"])
    return KnowledgeEntry(
        source_file=source_file, source_provider=provider, timestamp=timestamp,
        category=", ".join(categories), content=text[:2000],
        project_relevance=projects, extracted_tags=tags, confidence=confidence,
        actionable=actionable,
        suggested_task=(f"{categories[0]}: {text[:100]}..."
                        if actionable and categories else ""),
        parser=JSON_PARSER, role=role, truncated=len(text) > 2000)


CONVERSATIONS_BASE = Path(r"E:\external drive\ai chat conversations")


def parse_conversation_json_exports(
        base: Path = CONVERSATIONS_BASE) -> list[KnowledgeEntry]:
    """Parse structured JSON conversation exports missed by the splitter.

    Format A: [{uuid, name, created_at, chat_messages: [{sender, text,
      content, created_at, attachments, files}]}] (aetherius-data batch).
    Format B: [{id, title, inserted_at, mapping: {node: {message: {model,
      inserted_at, fragments: [{type, content}]}}}}] (DeepSeek export).
    Account-record files (users.json) are SKIPPED: PII, not conversations.
    """
    entries: list[KnowledgeEntry] = []
    batch = (base / "other" / "aetherius-data" /
             "data-2025-12-15-13-18-16-batch-0000" / "conversations.json")
    if batch.exists():
        try:
            convos = json.loads(batch.read_text(encoding="utf-8"))
        except ValueError:
            convos = []
        for convo in convos:
            for msg in convo.get("chat_messages") or []:
                text = msg.get("text") or msg.get("content") or ""
                e = _make_message_entry(
                    str(batch), "Other (aetherius batch export)",
                    str(msg.get("sender", "")), str(msg.get("created_at", "")),
                    str(text))
                if e:
                    entries.append(e)
    deepseek = (base / "other" / "aetherius-data" /
                "deepseek_data" / "conversations.json")
    if deepseek.exists():
        try:
            convos = json.loads(deepseek.read_text(encoding="utf-8"))
        except ValueError:
            convos = []
        for convo in convos:
            mapping = convo.get("mapping") or {}
            for node in mapping.values():
                msg = (node or {}).get("message") or {}
                frags = msg.get("fragments") or []
                text = "\n".join(str(f.get("content", ""))
                                 for f in frags if f.get("content"))
                role = "assistant" if any(
                    f.get("type") == "RESPONSE" for f in frags) else "user"
                e = _make_message_entry(
                    str(deepseek), "DeepSeek", role,
                    str(msg.get("inserted_at", "")), text)
                if e:
                    entries.append(e)
    return entries


if __name__ == "__main__":
    result = ingest_ai_conversations()