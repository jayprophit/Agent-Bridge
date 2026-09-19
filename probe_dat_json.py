#!/usr/bin/env python3
"""Probe JSON? DAT files for conversation-export structure. Read-only."""
import json
import os

def _input_path(env_name):
    """Machine-specific input paths are configured, never hardcoded."""
    value = os.environ.get(env_name, "")
    if not value:
        raise SystemExit(
            f"Set {env_name} to the input path "
            "(machine-specific paths are not hardcoded).")
    return value


SRC = _input_path("AGENT_BRIDGE_CHATGPT_CORPUS_DIR")

CONV_KEYS = {"mapping", "messages", "conversations", "conversation_id",
             "message_id", "parent_id", "author", "role", "content",
             "create_time", "update_time", "title", "model"}


def struct_summary(obj, depth=0, maxd=2):
    if depth > maxd:
        return "..."
    if isinstance(obj, dict):
        return {k: struct_summary(v, depth + 1, maxd)
                for k, v in list(obj.items())[:12]}
    if isinstance(obj, list):
        return ["len=%d" % len(obj)] + (
            [struct_summary(obj[0], depth + 1, maxd)] if obj else [])
    return type(obj).__name__


def main():
    found = []
    for root, _d, names in os.walk(SRC):
        for n in sorted(names):
            if n.endswith(".dat"):
                found.append(os.path.join(root, n))
    n_conv = 0
    for p in found:
        with open(p, "rb") as f:
            head = f.read(64)
        s = head.lstrip(b"\xef\xbb\xbf \t\r\n")
        if not (s[:1] == b"{" or s[:1] == b"["):
            continue
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                obj = json.load(f)
        except Exception as e:
            print("JSON_PARSE_FAIL", os.path.basename(p),
                  os.path.getsize(p), str(e)[:80])
            continue
        keys = set(obj.keys()) if isinstance(obj, dict) else set()
        hit = keys & CONV_KEYS
        tag = "CONV_CANDIDATE" if hit else "json-other"
        if hit:
            n_conv += 1
        print("%s %s size=%d keys=%s" % (
            tag, os.path.basename(p), os.path.getsize(p),
            sorted(keys)[:10]))
    print("conv_candidates:", n_conv)


if __name__ == "__main__":
    main()
