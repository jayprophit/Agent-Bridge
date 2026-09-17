#!/usr/bin/env python3
"""Extract TRUE gap IDs from master reequirements.txt.

File structure: repeated batches restart the leading number, but the
title carries the true gap family number, e.g.:
  '1. **161. Agentic commerce protocol stack**' -> true ID 161
  '80. **1040. Genesis/Aetherius scientific reasoning fabric**' -> true ID 1040
First batch has no inner number: '1. **Aetherius kernel ...**' -> true ID 1.
"""
import json
import re

SRC = r"C:\Users\jpowe\Documents\openCDE-agent\master reequirements.txt"

def main():
    with open(SRC, "r", encoding="utf-8-sig", errors="replace") as f:
        lines = f.read().split("\n")

    entries = []  # (line_no, outer_num, raw_title)
    for i, line in enumerate(lines):
        m = re.match(r"^(\d+)\.\s\*\*(.+?)\*\*\s*$", line.strip())
        if m:
            entries.append((i + 1, int(m.group(1)), m.group(2).strip()))

    print("raw heading matches:", len(entries))

    gaps = {}  # true_id -> {title, first_line, occurrences}
    for line_no, outer, raw in entries:
        m2 = re.match(r"^(\d+)\.\s+(.+)$", raw)
        if m2:
            true_id = int(m2.group(1))
            title = m2.group(2).strip()
        else:
            true_id = outer
            title = raw
        if true_id not in gaps:
            gaps[true_id] = {"title": title, "first_line": line_no,
                             "occurrences": 1}
        else:
            gaps[true_id]["occurrences"] += 1

    ids = sorted(gaps)
    print("distinct true gap IDs:", len(ids))
    print("id range:", min(ids), "-", max(ids))
    missing = [n for n in range(1, max(ids) + 1) if n not in gaps]
    print("missing IDs in 1..max:", missing[:20], "count:", len(missing))
    dups = {k: v["occurrences"] for k, v in gaps.items()
            if v["occurrences"] > 1}
    print("duplicate IDs:", len(dups))
    for k in sorted(dups)[:10]:
        print("  dup", k, "x" + str(dups[k]), gaps[k]["title"][:60])

    # show first/last few
    for k in ids[:5]:
        print(" ", k, gaps[k]["title"][:70])
    print("  ...")
    for k in ids[-5:]:
        print(" ", k, gaps[k]["title"][:70])

    out = {"total_distinct": len(ids),
           "id_min": min(ids), "id_max": max(ids),
           "missing": missing,
           "gaps": {str(k): gaps[k] for k in ids}}
    with open(r"C:\Users\jpowe\Desktop\Agent-Bridge\true_gap_index.json",
              "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print("wrote true_gap_index.json")

if __name__ == "__main__":
    main()
