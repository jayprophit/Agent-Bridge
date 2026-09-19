#!/usr/bin/env python3
"""Bounded delta extraction from DAT text corpus. Read-only source.

Role rule: owner-authored docs (packets/reports/libraries) -> OWNER-adjacent
(owner uploaded them as working state); chat exports starting with assistant
voice ("Sure,", "Here") -> ASSISTANT. Never mine assistant reasoning as reqs.
"""
import json
import os
import re

def _input_path(env_name):
    """Machine-specific input paths are configured, never hardcoded."""
    value = os.environ.get(env_name, "")
    if not value:
        raise SystemExit(
            f"Set {env_name} to the input path "
            "(machine-specific paths are not hardcoded).")
    return value


SRC = _input_path("AGENT_BRIDGE_CHATGPT_CORPUS_DIR")
MANIFEST = (r"E:\OpenCode-Data\conversation-analysis"
            r"\CHATGPT_DAT_CORPUS_MANIFEST.json")
OUT = (r"E:\OpenCode-Data\conversation-analysis"
       r"\CHATGPT_DAT_DELTAS.json")

TODO_PAT = re.compile(
    r"(?im)^.*\b(todo|to do|fixme|phase\s*2|stage\s*2|missing|broken|"
    r"needs (building|implementing)|follow up|not finished|"
    r"needs? (to be )?built|still required|\u274c|\U0001f7e1)\b.*$")
DEC_PAT = re.compile(
    r"(?im)^.*\b(decision|decided|canonical|supersedes?|approved|"
    r"rejected|authoritative|single source of truth)\b.*$")
ASSISTANT_OPEN = re.compile(
    r"^(sure,|here'?s|great|absolutely|of course|you'?re right|"
    r"i('ve| have) |let me |i can |as an ai)", re.I)


def main():
    man = json.load(open(MANIFEST, encoding="utf-8"))
    deltas = {"requirements": [], "decisions": [], "todos": [],
              "files_seen": 0, "assistant_voice": [], "owner_docs": []}
    for r in man["files"]:
        if r["detected"] not in ("TEXT?", "TEXT_MD?"):
            continue
        deltas["files_seen"] += 1
        with open(r["source_path"], encoding="utf-8-sig",
                  errors="replace") as f:
            t = f.read()
        head = t[:1500]
        if ASSISTANT_OPEN.match(head.strip()):
            role = "ASSISTANT"
            deltas["assistant_voice"].append(r["filename"])
        else:
            role = "OWNER_DOC"
            deltas["owner_docs"].append(r["filename"])
        # ATHENA alias normalisation note
        alias = "ATHEENA" in t
        for m in TODO_PAT.finditer(t):
            line = m.group(0).strip()
            if len(line) > 300:
                line = line[:300]
            deltas["todos"].append({
                "file": r["filename"], "sha256": r["sha256"][:16],
                "role": role, "line": line,
                "status": "STILL_REQUIRED?",
                "atheen_alias_present": alias})
        for m in DEC_PAT.finditer(t):
            line = m.group(0).strip()
            if len(line) > 300:
                line = line[:300]
            deltas["decisions"].append({
                "file": r["filename"], "sha256": r["sha256"][:16],
                "role": role, "line": line})
        # requirement-ish: markdown H1/H2 headers in owner docs
        if role == "OWNER_DOC":
            for h in re.finditer(r"(?m)^#{1,2}\s+(.+)$", t):
                title = h.group(1).strip()[:160]
                if len(title) > 12:
                    deltas["requirements"].append({
                        "file": r["filename"],
                        "sha256": r["sha256"][:16],
                        "title": title})
    # cap stored lines per file to avoid bloat
    for k in ("todos", "decisions"):
        by_file = {}
        for d in deltas[k]:
            by_file.setdefault(d["file"], []).append(d)
        capped = []
        for f, ds in by_file.items():
            capped.extend(ds[:25])
        deltas[k] = capped
    json.dump(deltas, open(OUT, "w", encoding="utf-8"), indent=1)
    print("files_seen:", deltas["files_seen"])
    print("owner_docs:", len(deltas["owner_docs"]),
          "assistant_voice:", len(deltas["assistant_voice"]))
    print("todo_markers:", len(deltas["todos"]),
          "decision_markers:", len(deltas["decisions"]),
          "req_headers:", len(deltas["requirements"]))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
