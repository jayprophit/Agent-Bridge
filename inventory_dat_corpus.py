#!/usr/bin/env python3
"""Read-only inventory of ChatGPT DAT corpus. No writes to source."""
import hashlib
import json
import os

SRC = r"C:\Users\jpowe\Downloads\chatgpt files"
OUT = (r"E:\OpenCode-Data\conversation-analysis"
       r"\CHATGPT_DAT_CORPUS_MANIFEST.json")

SIGS = [
    (b"\x53\x51\x4c\x69\x74\x65\x20\x66\x6f\x72\x6d\x61\x74\x20\x33\x00",
     "SQLITE"),
    (b"PK\x03\x04", "ZIP"),
    (b"%PDF", "PDF"),
    (b"\x89PNG", "PNG"),
    (b"\xff\xd8\xff", "JPEG"),
    (b"GIF8", "GIF"),
    (b"\x1f\x8b", "GZIP"),
    (b"BM", "BMP"),
    (b"II*\x00", "TIFF"), (b"MM\x00*", "TIFF"),
]


def sniff(head):
    for sig, name in SIGS:
        if head.startswith(sig):
            return name
    s = head.lstrip(b"\xef\xbb\xbf \t\r\n")
    if not s:
        return "EMPTY"
    if s[:1] == b"{" or s[:1] == b"[":
        try:
            json.loads(head.decode("utf-8-sig")[:200000])
            return "JSON?"
        except Exception:
            return "BRACE_LEAD_NOT_JSON"
    if s[:5].lower() == b"<?xml" or s[:5].lower() == b"<html" \
            or s[:9].lower() == b"<!doctype":
        return "MARKUP?"
    if b"\x00" in head[:8000]:
        # check utf-16
        try:
            head.decode("utf-16")
            return "UTF16?"
        except Exception:
            return "BINARY?"
    try:
        head.decode("utf-8")
        # markdown-ish?
        t = head.decode("utf-8")[:2000]
        if t.lstrip().startswith("#") or "```" in t:
            return "TEXT_MD?"
        return "TEXT?"
    except Exception:
        return "BINARY?"


def main():
    files = []
    for root, _dirs, names in os.walk(SRC):
        for n in sorted(names):
            files.append(os.path.join(root, n))
    recs = []
    for p in files:
        st = os.stat(p)
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while True:
                b = f.read(1048576)
                if not b:
                    break
                h.update(b)
        with open(p, "rb") as f:
            head = f.read(65536)
        recs.append({
            "source_path": p,
            "relative_path": os.path.relpath(p, SRC),
            "filename": os.path.basename(p),
            "extension": os.path.splitext(p)[1],
            "size": st.st_size,
            "mtime": st.st_mtime,
            "sha256": h.hexdigest(),
            "detected": sniff(head),
            "head_len": len(head),
        })
    by_type = {}
    for r in recs:
        by_type[r["detected"]] = by_type.get(r["detected"], 0) + 1
    man = {"source": SRC,
           "total_files": len(recs),
           "total_bytes": sum(r["size"] for r in recs),
           "by_detected": by_type,
           "files": recs}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    print("total_files:", len(recs))
    print("total_bytes:", man["total_bytes"])
    for k, v in sorted(by_type.items(), key=lambda x: -x[1]):
        print("  %-22s %d" % (k, v))


if __name__ == "__main__":
    main()
