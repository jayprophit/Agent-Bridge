"""Oracle-aware test-quality verification (v0.4 foundation).

Heuristics (static + cheap dynamic), stdlib only. Never claims proof.
Verdicts: GOOD | WEAK | SUSPICIOUS | UNKNOWN + reasons/evidence.
A build with tests_passed=true but quality SUSPICIOUS is NOT fully verified.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

GOOD = "GOOD"
WEAK = "WEAK"
SUSPICIOUS = "SUSPICIOUS"
UNKNOWN = "UNKNOWN"


def _changed_symbols(changed_files: list[str], diff_text: str) -> set[str]:
    syms: set[str] = set()
    for f in changed_files:
        stem = Path(f).stem
        if stem and stem != ".":
            syms.add(stem)
    # function defs added/changed in diff
    for m in re.finditer(r"^[+-]\s*def\s+(\w+)", diff_text, re.M):
        syms.add(m.group(1))
    return {s for s in syms if s}


UNITTEST_ASSERTS = frozenset({
    "assertEqual", "assertNotEqual", "assertTrue", "assertFalse",
    "assertIs", "assertIsNot", "assertIsNone", "assertIsNotNone",
    "assertIn", "assertNotIn", "assertIsInstance", "assertNotIsInstance",
    "assertRaises", "assertRaisesRegex", "assertWarns", "assertWarnsRegex",
    "assertLogs", "assertNoLogs", "assertAlmostEqual", "assertNotAlmostEqual",
    "assertGreater", "assertGreaterEqual", "assertLess", "assertLessEqual",
    "assertRegex", "assertNotRegex", "assertCountEqual", "assertMultiLineEqual",
    "assertSequenceEqual", "assertListEqual", "assertTupleEqual",
    "assertSetEqual", "assertDictEqual", "fail",
})


def _is_unittest_assert(node: ast.AST) -> str:
    """Return the assertion method name if node is a TestCase assert* call."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return ""
    func = node.value.func
    name = ""
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    if name in UNITTEST_ASSERTS or (name.startswith("assert") and len(name) > 6):
        return name
    return ""


def _parse_test_file(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return {"ok": False}
    imports: set[str] = set()
    asserts = 0
    methods: list[str] = []
    funcs = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = getattr(node, "names", [])
            for a in names:
                imports.add(a.name.split(".")[0] if hasattr(a, "name") else "")
            mod = getattr(node, "module", "") or ""
            if mod:
                imports.add(mod.split(".")[0])
        elif isinstance(node, ast.Assert):
            asserts += 1
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("test"):
            funcs += 1
        method = _is_unittest_assert(node)
        if method:
            asserts += 1
            methods.append(method)
    return {"ok": True, "imports": imports, "asserts": asserts,
            "assert_methods": sorted(set(methods)), "test_funcs": funcs}


def assess(changed_files: list[str], test_files: list[str], diff_text: str,
           test_results: list[dict[str, Any]], workspace: Path) -> dict[str, Any]:
    """Assess whether the tests meaningfully exercise the changes."""
    reasons: list[str] = []
    if not test_files:
        if test_results and all(t.get("passed") for t in test_results):
            return {"quality": WEAK,
                    "reasons": ["no test files; verification via shell runs only"],
                    "evidence": {"tests_run": len(test_results)},
                    "evidence_types": ["RUNTIME_OUTPUT_VERIFICATION"]}
        return {"quality": WEAK, "reasons": ["no test files found"],
                "evidence": {}, "evidence_types": []}
    syms = _changed_symbols(changed_files, diff_text)
    total_asserts = 0
    methods: set[str] = set()
    exercised: set[str] = set()
    unparsable: list[str] = []
    for tf in test_files:
        info = _parse_test_file(workspace / tf)
        if not info.get("ok"):
            unparsable.append(tf)
            continue
        total_asserts += info["asserts"]
        methods.update(info.get("assert_methods", []))
        exercised |= (info["imports"] & syms)
        # direct symbol mentions in test source
        try:
            src = (workspace / tf).read_text(encoding="utf-8")
        except OSError:
            src = ""
        for s in syms:
            if re.search(r"\b" + re.escape(s) + r"\b", src):
                exercised.add(s)
    evidence = {"changed_symbols": sorted(syms), "exercised": sorted(exercised),
                "asserts": total_asserts, "assert_methods": sorted(methods),
                "unparsable": unparsable,
                "tests_run": len(test_results),
                "tests_passed": sum(1 for t in test_results if t.get("passed"))}
    passed = [t for t in test_results if t.get("passed")]
    types = ["TEST_VERIFICATION"] if total_asserts else []
    if passed:
        types.append("RUNTIME_OUTPUT_VERIFICATION")
    if unparsable and total_asserts == 0:
        reasons.append(f"test files unparsable: {unparsable}")
        return {"quality": SUSPICIOUS, "reasons": reasons, "evidence": evidence,
                "evidence_types": types or ["STATIC_VERIFICATION"]}
    if total_asserts == 0:
        reasons.append("no assert statements in tests (performs no verification)")
        return {"quality": SUSPICIOUS, "reasons": reasons, "evidence": evidence,
                "evidence_types": types or ["STATIC_VERIFICATION"]}
    if syms and not exercised:
        reasons.append(f"tests never import/mention changed code: {sorted(syms)}")
        return {"quality": SUSPICIOUS, "reasons": reasons, "evidence": evidence,
                "evidence_types": types or ["STATIC_VERIFICATION"]}
    # changed functions with zero direct exercise
    func_syms = {m.group(1) for m in re.finditer(r"^[+-]\s*def\s+(\w+)", diff_text, re.M)}
    if func_syms and not (func_syms & exercised):
        reasons.append(f"changed functions receive zero exercise: {sorted(func_syms)}")
        return {"quality": WEAK, "reasons": reasons, "evidence": evidence,
                "evidence_types": types}
    if total_asserts < 2:
        reasons.append("only one assertion (thin verification)")
        return {"quality": WEAK, "reasons": reasons, "evidence": evidence,
                "evidence_types": types}
    reasons.append(f"tests exercise {sorted(exercised)} with {total_asserts} asserts")
    return {"quality": GOOD, "reasons": reasons, "evidence": evidence,
            "evidence_types": types + ["STATIC_VERIFICATION"]}
