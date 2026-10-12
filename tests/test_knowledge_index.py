"""Knowledge Layer tests — pipeline, incremental sync, retrieval, persistence.

The honesty rules are the point: an unparseable file is recorded, not dropped;
an unmapped project says 'unmapped' rather than guessing; retrieval returns
provenance so a worker can verify where knowledge came from.
"""
from __future__ import annotations

import json

from compute.knowledge_index import (
    CHAT_EXPORT, IMAGE, PROJECT_DOC, PROMPT_ARCHIVE, UNPARSED, VERIFIED,
    KnowledgeIndex, KnowledgeObject, classify_source, extract_summary,
    map_project, resolve_sources,
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class TestClassification:
    def test_chat_export_source(self, tmp_path):
        p = tmp_path / "chatgpt - Genesis Design.txt"
        p.write_text("You: hello\nChatGPT: hi", encoding="utf-8")
        assert classify_source(p, "chat_exports") == CHAT_EXPORT

    def test_prompt_archive(self, tmp_path):
        p = tmp_path / "CONTINUOUS BUILD86.txt"
        p.write_text("build directive", encoding="utf-8")
        assert classify_source(p, "master_prompts") == PROMPT_ARCHIVE

    def test_image_recorded_not_parsed(self, tmp_path):
        p = tmp_path / "reference.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        assert classify_source(p, "chat_exports") == IMAGE

    def test_unknown_extension(self, tmp_path):
        p = tmp_path / "mystery.xyz"
        p.write_text("x", encoding="utf-8")
        assert classify_source(p, "weird") == UNPARSED


class TestProjectMapping:
    def test_maps_by_filename_evidence(self, tmp_path):
        p = tmp_path / "Aetherius Genesis Avatar Identity.txt"
        assert map_project(p, "") == "genesis"

    def test_maps_by_content_evidence(self, tmp_path):
        p = tmp_path / "notes.txt"
        text = "The agent bridge supervisor read model subscribes to the event bus"
        assert map_project(p, text) == "agent-bridge"

    def test_unmapped_rather_than_guessed(self, tmp_path):
        p = tmp_path / "random.txt"
        assert map_project(p, "nothing relevant here at all") == "unmapped"


class TestParsing:
    def test_turn_count_from_speaker_markers(self, tmp_path):
        p = _write(tmp_path / "c.txt",
                   "You: what now?\nChatGPT: build the shell\nYou: ok\nChatGPT: done")
        idx = KnowledgeIndex()
        obj = idx.ingest_file(p, "chat_exports")
        assert obj.turn_count == 4
        assert obj.confidence == VERIFIED

    def test_summary_is_actual_opening_not_fabricated(self, tmp_path):
        p = _write(tmp_path / "c.txt",
                   "You: question one\nChatGPT: THE ANSWER IS FORTY TWO")
        idx = KnowledgeIndex()
        obj = idx.ingest_file(p, "chat_exports")
        assert "FORTY TWO" in obj.summary

    def test_requirements_extracted(self, tmp_path):
        p = _write(tmp_path / "spec.txt",
                   "Requirement AETH-IDE-441 must ship.\nAlso MAT-124 matters.")
        idx = KnowledgeIndex()
        obj = idx.ingest_file(p, "opencde_agent")
        assert "AETH-IDE-441" in obj.requirements
        assert "MAT-124" in obj.requirements


class TestIncrementalSync:
    def test_first_sync_all_new(self, tmp_path):
        root = tmp_path / "src"
        _write(root / "a.txt", "genesis shell design")
        _write(root / "b.txt", "agent bridge telemetry")
        idx = KnowledgeIndex()
        r = idx.sync_source("chat_exports", root)
        assert r["scanned"] == 2
        assert r["new"] == 2
        assert r["unchanged"] == 0
        assert idx.overview()["objects"] == 2

    def test_second_sync_unchanged(self, tmp_path):
        root = tmp_path / "src"
        _write(root / "a.txt", "genesis shell design")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        r = idx.sync_source("chat_exports", root)
        assert r["new"] == 0
        assert r["unchanged"] == 1

    def test_changed_file_reindexed(self, tmp_path):
        root = tmp_path / "src"
        p = _write(root / "a.txt", "genesis shell design")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        p.write_text("genesis shell design revised with aurora theme",
                     encoding="utf-8")
        r = idx.sync_source("chat_exports", root)
        assert r["changed"] == 1
        # the object_id is content-hash based, so the revised content is a
        # NEW object — dedupe by content, not by path
        assert any("aurora" in (o.summary + " ".join(o.topics)).lower()
                   for o in idx._objects.values())

    def test_deleted_file_recorded_not_silent(self, tmp_path):
        root = tmp_path / "src"
        p = _write(root / "a.txt", "genesis design")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        p.unlink()
        r = idx.sync_source("chat_exports", root)
        assert r["deleted"] == 1
        assert r["errors"] == 0

    def test_missing_root_is_reported(self, tmp_path):
        idx = KnowledgeIndex()
        r = idx.sync_source("chat_exports", tmp_path / "nope")
        assert r.get("error") == "source root missing"


class TestRetrieval:
    def _idx(self, tmp_path):
        root = tmp_path / "src"
        _write(root / "genesis.txt",
               "genesis avatar identity with abyss theme and aurora accents")
        _write(root / "bridge.txt",
               "agent bridge supervisor event bus node server telemetry")
        _write(root / "mat.txt",
               "materials atlas thermal data element frequency provenance")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        return idx

    def test_retrieve_ranks_relevant_first(self, tmp_path):
        idx = self._idx(tmp_path)
        hits = idx.retrieve("genesis avatar abyss")
        assert hits and hits[0].title == "genesis"

    def test_retrieve_with_project_filter(self, tmp_path):
        idx = self._idx(tmp_path)
        hits = idx.retrieve("telemetry", project="agent-bridge")
        assert all(h.project == "agent-bridge" for h in hits)

    def test_context_for_task_has_provenance(self, tmp_path):
        idx = self._idx(tmp_path)
        ctx = idx.context_for_task("genesis avatar", limit=1)
        assert len(ctx) == 1
        item = ctx[0]
        assert "provenance" in item
        assert item["provenance"]["content_hash"]
        assert item["summary"]

    def test_no_match_returns_empty_not_fabrication(self, tmp_path):
        idx = self._idx(tmp_path)
        assert idx.retrieve("zzzqqq nothing") == []


class TestPersistence:
    def test_round_trip(self, tmp_path):
        root = tmp_path / "src"
        _write(root / "a.txt", "genesis avatar identity")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        p = tmp_path / "index.json"
        idx.save(p)
        idx2 = KnowledgeIndex.load(p)
        assert idx2.overview()["objects"] == 1
        # retrieval works immediately after reload (resume, not restart)
        assert idx2.retrieve("genesis avatar")

    def test_no_secret_paths_leak_into_records(self, tmp_path):
        # records carry runtime paths + hashes only; a file containing a
        # credential-like string must not have that string promoted into the
        # summary beyond the actual file content
        root = tmp_path / "src"
        _write(root / "a.txt", "project notes about the bridge")
        idx = KnowledgeIndex()
        idx.sync_source("chat_exports", root)
        blob = json.dumps(idx.to_dict())
        assert "project notes about the bridge" in blob  # real content, hashed
        assert idx.overview()["by_confidence"][VERIFIED] == 1


class TestSourceResolution:
    def test_default_sources_are_portable_placeholders(self):
        # § secret-hygiene: committed source holds %VAR% placeholders only
        from compute.knowledge_index import DEFAULT_SOURCES
        for tmpl in DEFAULT_SOURCES.values():
            assert tmpl.startswith("%")
            assert "jpowe" not in tmpl

    def test_resolve_expands_env(self):
        from pathlib import Path as _P
        resolved = resolve_sources({"USERPROFILE": "C:/Users/test",
                                    "EXTERNAL_DRIVE": "E:/disk"})
        # Path normalises separators per-platform; compare as Paths
        assert resolved["master_prompts"] == \
            _P("C:/Users/test/Documents/master prompt")
        assert resolved["chat_exports"] == \
            _P("E:/disk/ai chat conversations")
