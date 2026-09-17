"""F↔E migration-map readiness (Phase 1.1, Part C).

Builds F-E-MIGRATION-MAP.json from evidence ONLY. F: is never touched
(F_DRIVE_CHECK stays DEFERRED). No record of original F: paths exists in
any manifest, so original_F_path is honestly `null` with status
PENDING_F_VERIFICATION — the map captures what CAN be known now:
current locations, move history, classification, project, sizes, and
hashes for small files. Content-hash comparison happens at future
verification time, when F: is read conservatively.

A moved E: path must never cause a false MISSING later: every record
carries its move_history chain for path-independent matching.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

KNOWLEDGE_DIR = Path(r"E:\OpenCode-Data\Knowledge")
MAP_PATH = KNOWLEDGE_DIR / "F-E-MIGRATION-MAP.json"

E_DATA = Path(r"E:\OpenCode-Data")
E_EXT = Path(r"E:\external drive")

SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".git",
             "node_modules.incomplete-20260811"}
MAX_FILES = 8000
HASH_UNDER_BYTES = 2_000_000


def _sha_small(path: Path) -> str | None:
    try:
        if path.stat().st_size > HASH_UNDER_BYTES:
            return None
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


# Verified migration events from session evidence (reports on E:).
# original_F_path is unknown: no F: manifest exists. Recorded honestly.
MIGRATION_EVENTS: list[dict[str, Any]] = [
    {"event": "genesis aux-folder merge",
     "evidence": "DESKTOP-CONSOLIDATION-VERIFICATION.md",
     "initial_E_copy_path": r"E:\external drive\Downloads\New folder (historical Genesis material)",
     "current_location": r"C:\Users\jpowe\Desktop\Genesis\integration-archive",
     "classification": "MIGRATION_SOURCE", "project": "genesis",
     "move_history": ["E:Downloads staging", "Desktop Genesis/integration-archive"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "MAT aux-folder merge",
     "evidence": "DESKTOP-CONSOLIDATION-VERIFICATION.md",
     "initial_E_copy_path": r"E:\external drive\Downloads (historical MAT material)",
     "current_location": r"C:\Users\jpowe\Desktop\Materials-Atlas-Table-Codex---MAT\integration-archive",
     "classification": "MIGRATION_SOURCE", "project": "mat",
     "move_history": ["E:Downloads staging", "Desktop MAT/integration-archive"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "Poietek native-build merge",
     "evidence": "DESKTOP-CONSOLIDATION-VERIFICATION.md",
     "initial_E_copy_path": r"E:\external drive\Downloads (Poietek native material)",
     "current_location": r"C:\Users\jpowe\Desktop\Poietek\native-build",
     "classification": "MIGRATION_SOURCE", "project": "poietek",
     "move_history": ["E:Downloads staging", "Desktop Poietek/native-build"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "Universal-Bridge output merge",
     "evidence": "DESKTOP-CONSOLIDATION-VERIFICATION.md",
     "initial_E_copy_path": r"E:\external drive\Downloads (UB output material)",
     "current_location": r"C:\Users\jpowe\Desktop\Universal-Bridge\output",
     "classification": "MIGRATION_SOURCE", "project": "universal-bridge",
     "move_history": ["E:Downloads staging", "Desktop Universal-Bridge/output"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "UBRIDGE-CERT-001 certification asset placement",
     "evidence": "DESKTOP-CONSOLIDATION-VERIFICATION.md",
     "initial_E_copy_path": r"C:\Users\jpowe\Desktop\UBRIDGE-CERT-001 (loose)",
     "current_location": r"E:\OpenCode-Data\Universal-Bridge\Test-Data\UBRIDGE-CERT-001",
     "classification": "DEVICE_DATA", "project": "universal-bridge",
     "move_history": ["Desktop loose", "E:OpenCode-Data Test-Data",
                      "repo manifest at Universal-Bridge/output/UBRIDGE-CERT-001"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "Aetherius-OS incorrect relocation + restore",
     "evidence": "session ledger (owner correction)",
     "initial_E_copy_path": r"C:\Users\jpowe\Desktop\Aetherius-OS (canonical, must stay)",
     "current_location": r"C:\Users\jpowe\Desktop\Aetherius-OS",
     "classification": "RESTRICTED_EVENT",
     "project": "aetherious",
     "move_history": ["Desktop canonical", "E:OpenCode-Data (INVALID DIRECTION, corrected)",
                      "restored to Desktop canonical"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "E:Downloads bulk reorganisation",
     "evidence": "E-DOWNLOADS-REORGANISATION-REPORT.md",
     "initial_E_copy_path": r"E:\external drive\Downloads",
     "current_location": r"E:\OpenCode-Data (Archives/Project-Resources/Installers/Private) + Desktop projects",
     "classification": "MIXED", "project": "multiple",
     "move_history": ["E:Downloads staging", "classified destinations per report"],
     "verification_status": "PENDING_F_VERIFICATION"},
    {"event": "AI conversation knowledge ingestion (read-only)",
     "evidence": "AI-CONVERSATION-INGESTION-AUDIT.json",
     "initial_E_copy_path": r"E:\external drive\ai chat conversations",
     "current_location": r"E:\external drive\ai chat conversations (read in place) + E:\OpenCode-Data\Knowledge (normalized)",
     "classification": "KNOWLEDGE", "project": "multiple",
     "move_history": ["read in place; raw chats never moved to git"],
     "verification_status": "PENDING_F_VERIFICATION"},
]


def walk_holdings(root: Path, cap: int) -> tuple[list[dict[str, Any]], bool]:
    holdings: list[dict[str, Any]] = []
    capped = False
    if not root.exists():
        return holdings, capped
    for path in sorted(root.rglob("*")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        holdings.append({
            "current_location": str(path),
            "current_name": path.name,
            "size": st.st_size,
            "mtime": st.st_mtime,
            "current_hash": _sha_small(path),
            "hash_note": "sha256 recorded" if st.st_size <= HASH_UNDER_BYTES
                         else "hash at verification time",
        })
        if len(holdings) >= cap:
            capped = True
            break
    return holdings, capped


def build() -> dict[str, Any]:
    events = []
    for ev in MIGRATION_EVENTS:
        events.append({
            "original_F_path": None,
            "original_F_note": "no F: manifest exists; unknown until F: is read",
            "original_relative_path": None,
            "original_name": None,
            "original_size": None,
            "original_hash": None,
            **ev,
        })
    e_data, capped_data = walk_holdings(E_DATA, MAX_FILES)
    e_ext, capped_ext = walk_holdings(E_EXT, MAX_FILES)
    doc = {
        "generated_at": time.time(),
        "f_drive_check": "DEFERRED — F: never touched by this builder",
        "matching_rule": ("content hash + size + manifest history + provenance "
                          "first; pathname never decides alone"),
        "migration_events": events,
        "holdings": {
            r"E:\OpenCode-Data": {"files": len(e_data), "capped": capped_data,
                                  "items": e_data},
            r"E:\external drive": {"files": len(e_ext), "capped": capped_ext,
                                   "items": e_ext},
        },
        "format_readiness": "NOT_READY — readiness requires F: source manifest; "
                            "no item may be reported SAFE_TO_FORMAT_BY_OWNER",
    }
    MAP_PATH.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    print(f"Wrote {MAP_PATH}: {len(events)} events, "
          f"{len(e_data)}+{len(e_ext)} holdings")
    return doc


if __name__ == "__main__":
    build()
