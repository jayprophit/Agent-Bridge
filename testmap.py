"""Lightweight test-to-file mapping (v0.5 foundation).

For Python, infers changed-file <-> test relations via imports, module
names, test references and the runtime command context. Reports confidence;
never overclaims coverage.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def _test_refs(test_path: Path) -> set[str]:
    refs: set[str] = set()
    try:
        src = test_path.read_text(encoding="utf-8")
    except OSError:
        return refs
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return refs
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            refs.add(node.module.split(".")[0])
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\.\s*\w+\s*\(", src):
        refs.add(m.group(1))
    return refs


def map_tests(changed: list[str], test_files: list[str],
              workspace: Path) -> dict[str, Any]:
    """Return {mapping: {source: [{test, confidence, why}]}, unmapped, weak}."""
    mapping: dict[str, list[dict[str, Any]]] = {}
    unmapped: list[str] = []
    for src in changed:
        stem = Path(src).stem
        hits = []
        for tf in test_files:
            refs = _test_refs(workspace / tf)
            conf, why = 0.0, ""
            if stem and stem in refs:
                conf, why = 0.8, f"test imports/references module {stem!r}"
            elif Path(tf).stem.replace("test_", "").replace("_test", "") == stem:
                conf, why = 0.6, "name correspondence"
            if conf:
                hits.append({"test": tf, "confidence": conf, "why": why})
        if hits:
            mapping[src] = hits
        else:
            unmapped.append(src)
    weak = [s for s in changed if s not in mapping]
    return {"mapping": mapping, "unmapped": unmapped,
            "weak_sources": weak,
            "note": "heuristic mapping only; not coverage proof"}
