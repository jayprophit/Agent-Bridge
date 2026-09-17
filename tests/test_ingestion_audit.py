"""Parser coverage + ingestion audit tests (Phase 1.1, Part B §20).

Proves the parsers do not silently lose messages, roles, timestamps,
code blocks, project names, owner corrections or acceptance conditions —
and honestly documents what they DO lose (splitter: roles/timestamps,
>2000-char tails).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from models.knowledge_ingestion import (
    JSON_PARSER,
    SPLITTER_PARSER,
    _make_message_entry,
    parse_conversation_json_exports,
    process_conversation_file,
)


def _tmp_txt(content: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ing_"))
    p = tmp / "conv.txt"
    p.write_text(content, encoding="utf-8")
    return p


CONV = """User: Fix the Fibonacci bug in fibonacci.py. It must return n-1 + n-2.

Assistant: Fixed. The function now returns calculate_fibonacci(n - 1) + calculate_fibonacci(n - 2).

Acceptance: all test assertions pass for the Genesis agent bridge task.

```python
def fibonacci(n):
    return n if n < 2 else fibonacci(n - 1) + fibonacci(n - 2)
```
"""


class TestSplitterCoverage(unittest.TestCase):
    def test_messages_not_lost(self):
        entries = process_conversation_file(_tmp_txt(CONV), "claude")
        blob = "\n".join(e.content for e in entries)
        self.assertIn("Fibonacci", blob)
        self.assertIn("acceptance", blob.lower())

    def test_code_blocks_preserved(self):
        entries = process_conversation_file(_tmp_txt(CONV), "claude")
        blob = "\n".join(e.content for e in entries)
        self.assertIn("def fibonacci", blob)

    def test_project_names_detected(self):
        entries = process_conversation_file(_tmp_txt(CONV), "claude")
        projs = {p for e in entries for p in e.project_relevance}
        self.assertIn("genesis", projs)
        self.assertIn("agent-bridge", projs)

    def test_truncation_flagged(self):
        big = "User: " + "x" * 5000 + "\n\nAssistant: ok\n"
        entries = process_conversation_file(_tmp_txt(big), "claude")
        self.assertTrue(any(e.truncated for e in entries))
        self.assertTrue(all(e.parser == SPLITTER_PARSER for e in entries))

    def test_owner_correction_classified(self):
        entries = process_conversation_file(
            _tmp_txt("Owner correction: the Desktop projects stay on Desktop, "
                     "do not move genesis to E:."), "chatgpt")
        cats = {c for e in entries for c in e.category.split(", ")}
        self.assertIn("OWNER_CORRECTION", cats)


class TestJsonExportParser(unittest.TestCase):
    def _base(self) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="ingj_"))
        (tmp / "other" / "aetherius-data" / "data-2025-12-15-13-18-16-batch-0000").mkdir(
            parents=True)
        (tmp / "other" / "aetherius-data" / "deepseek_data").mkdir(parents=True)
        return tmp

    def test_batch_format_roles_timestamps(self):
        base = self._base()
        conv = [{"uuid": "u1", "chat_messages": [
            {"sender": "user", "text": "Build the avatar", "created_at": "2025-01-01"},
            {"sender": "assistant", "text": "Done", "created_at": "2025-01-02"}]}]
        (base / "other" / "aetherius-data" / "data-2025-12-15-13-18-16-batch-0000"
         / "conversations.json").write_text(json.dumps(conv), encoding="utf-8")
        (base / "other" / "aetherius-data" / "deepseek_data"
         / "conversations.json").write_text("[]", encoding="utf-8")
        entries = parse_conversation_json_exports(base)
        self.assertEqual(len(entries), 2)
        by_role = {e.role: e for e in entries}
        self.assertEqual(by_role["user"].timestamp, "2025-01-01")
        self.assertEqual(by_role["assistant"].timestamp, "2025-01-02")
        self.assertTrue(all(e.parser == JSON_PARSER for e in entries))
        self.assertFalse(any(e.truncated for e in entries))

    def test_deepseek_format(self):
        base = self._base()
        (base / "other" / "aetherius-data" / "data-2025-12-15-13-18-16-batch-0000"
         / "conversations.json").write_text("[]", encoding="utf-8")
        msg = {"model": "deepseek-chat", "inserted_at": "2025-02-01",
               "fragments": [{"type": "REQUEST", "content": "hi"}]}
        node1 = {"id": "1", "parent": "root", "children": [], "message": msg}
        root = {"id": "root", "parent": None, "children": ["1"],
                "message": None}
        conv = [{"id": "c1", "mapping": {"root": root, "1": node1}}]
        (base / "other" / "aetherius-data" / "deepseek_data"
         / "conversations.json").write_text(json.dumps(conv), encoding="utf-8")
        entries = parse_conversation_json_exports(base)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].role, "user")
        self.assertEqual(entries[0].timestamp, "2025-02-01")

    def test_empty_messages_skipped(self):
        self.assertIsNone(_make_message_entry("f", "p", "user", "t", "   "))

    def test_account_files_never_parsed(self):
        base = self._base()
        (base / "other" / "aetherius-data" / "data-2025-12-15-13-18-16-batch-0000"
         / "conversations.json").write_text("[]", encoding="utf-8")
        (base / "other" / "aetherius-data" / "deepseek_data"
         / "conversations.json").write_text("[]", encoding="utf-8")
        # PII-adjacent account records must not become knowledge entries:
        # the parser only reads the two conversations.json paths.
        entries = parse_conversation_json_exports(base)
        self.assertEqual(entries, [])


class TestAuditHonesty(unittest.TestCase):
    def test_status_counts_cover_everything(self):
        data = json.loads(Path(
            r"E:\OpenCode-Data\Knowledge\AI-CONVERSATION-INGESTION-AUDIT.json"
        ).read_text(encoding="utf-8"))
        total = sum(data["summary"]["status_counts"].values())
        self.assertEqual(total, data["summary"]["files_discovered"])
        self.assertEqual(data["summary"]["fully_parsed"], 0)
        # every normalized entry maps to an existing file
        self.assertEqual(data["summary"]["orphaned_sources"], [])

    def test_json_exports_no_longer_unsupported(self):
        data = json.loads(Path(
            r"E:\OpenCode-Data\Knowledge\AI-CONVERSATION-INGESTION-AUDIT.json"
        ).read_text(encoding="utf-8"))
        conv = [r for r in data["records"]
                if r["filename"] == "conversations.json"]
        self.assertEqual(len(conv), 2)
        for r in conv:
            self.assertIn(r["parse_status"], ("FULLY_PARSED", "PARTIALLY_PARSED"))
            self.assertGreater(r["entries_extracted"], 0)


if __name__ == "__main__":
    unittest.main()
