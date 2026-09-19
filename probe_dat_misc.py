#!/usr/bin/env python3
"""Classify TEXT/MARKUP/ZIP/PDF DAT files. Read-only."""
import os
import re
import zipfile

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
import json as J
with open(MANIFEST, encoding="utf-8") as f:
    man = J.load(f)
byname = {r["filename"]: r for r in man["files"]}

text_kinds = {}
markup_titles = []
zips = []
pdfs = []
code_hits = 0
req_hits = 0
for r in man["files"]:
    p = r["source_path"]
    d = r["detected"]
    if d in ("TEXT?", "TEXT_MD?"):
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            t = f.read(6000)
        tl = t.lower()
        if re.search(r"\b(todo|fixme|phase\s*2|stage\s*2|missing|broken|"
                     r"needs (building|implementing)|follow up)\b", tl):
            req_hits += 1
            kind = "TODO_REQ_CANDIDATE"
        elif "```" in t or re.search(
                r"^(import |from |def |class |function |const |export )",
                t, re.M) or t.lstrip().startswith(("{", "[")):
            code_hits += 1
            kind = "CODE?"
        elif t.lstrip().startswith("#"):
            kind = "DOC_MD"
        else:
            kind = "TEXT_OTHER"
        text_kinds[kind] = text_kinds.get(kind, 0) + 1
        if kind == "TODO_REQ_CANDIDATE":
            print("REQ?", r["filename"], r["size"],
                  t.strip().replace("\n", " ")[:120])
    elif d == "MARKUP?":
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            t = f.read(4000)
        m = re.search(r"<title>(.*?)</title>", t, re.S | re.I)
        markup_titles.append((r["filename"], r["size"],
                              m.group(1).strip()[:80] if m else "?"))
    elif d == "ZIP":
        try:
            z = zipfile.ZipFile(p)
            names = z.namelist()
            zips.append((r["filename"], r["size"], len(names),
                         names[:6]))
        except Exception as e:
            zips.append((r["filename"], r["size"], "ERR", str(e)[:60]))
    elif d == "PDF":
        with open(p, "rb") as f:
            head = f.read(2000)
        m = re.search(rb"/Title\s*\((.*?)\)", head)
        pdfs.append((r["filename"], r["size"],
                     m.group(1)[:60] if m else b"?"))
print("TEXT kinds:", text_kinds)
print("REQ candidates:", req_hits, "CODE?:", code_hits)
print("MARKUP files:", len(markup_titles))
for n, s, t in markup_titles[:40]:
    print("  %s [%d] title=%s" % (n, s, t))
print("ZIPS:", len(zips))
for n, s, c, extra in zips:
    print("  %s [%d] entries=%s %s" % (n, s, c, extra))
print("PDFS:", len(pdfs))
for n, s, t in pdfs:
    print("  %s [%d] %s" % (n, s, t))
