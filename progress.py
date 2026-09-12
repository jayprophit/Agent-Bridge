"""Semantic progress detection + error-signature tracking (v0.5).

ProgressTracker watches file-state hashes, test outcomes, error
signatures, review-issue resolution and genuinely new outputs.
Activity (rewrites, reruns) without state advancement accumulates
no-progress strikes; at threshold it reports NO_PROGRESS_DETECTED so the
bridge stops before burning max_steps.

ErrorSignature normalizes recurring failures (type/file/line/command/exit/
stderr-shape) so "model claims a fix but the same error reappears" is
visible and can be fed back concisely.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


def file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return "missing"


def normalize_error(text: str) -> str:
    """Reduce an error to a stable signature.

    Generalized: numeric instance data, absolute paths, line numbers.
    Preserved (structurally meaningful): error type, filename, exit code.
    """
    t = text or ""
    m = re.search(r"(\w*(Error|Exception|Failure|error))\s*:?\s*([^\n]{0,120})", t)
    etype = m.group(1) if m else "error"
    detail = re.sub(r"\d+", "N", m.group(3).strip() if m else t[:120])
    detail = re.sub(r"[A-Za-z]:[\\/][\w\-\\.\\/ ]+", "<path>", detail)
    m2 = re.search(r'File "([^"]+)"', t)
    loc = Path(m2.group(1)).name if m2 else ""
    m3 = re.search(r"exit[_\s]*code\s*[:=]?\s*(\d+)", t, re.I)
    code = m3.group(1) if m3 else ""
    sig = f"{etype}: {detail}"
    if loc:
        sig += f" @ {loc}"
    if code:
        sig += f" [{code}]"
    sig = re.sub(r"0x[0-9a-fA-F]+", "0xN", sig)
    return sig[:200]


class ErrorSignatureTracker:
    def __init__(self):
        self.seen: dict[str, int] = {}
        self.last: str = ""

    def note(self, raw: str) -> tuple[str, int]:
        sig = normalize_error(raw)
        self.seen[sig] = self.seen.get(sig, 0) + 1
        self.last = sig
        return sig, self.seen[sig]

    def recurring(self, raw: str, threshold: int = 2) -> bool:
        sig, n = self.note(raw)
        return n >= threshold


class ProgressTracker:
    """State-advancement ledger. Callers report observations; priced_check()
    decides whether to keep going."""

    def __init__(self, no_progress_limit: int = 4):
        self.limit = no_progress_limit
        self.hashes: dict[str, str] = {}
        self.hash_history: dict[str, list[str]] = {}
        self.test_states: dict[str, bool] = {}
        self.error_sigs: dict[str, int] = {}
        self.issues_open: set[str] = set()
        self.outputs_seen: set[str] = set()
        self.strikes = 0
        self.events: list[str] = []

    # -- observations -----------------------------------------------------
    def note_file(self, workspace: Path, rel: str) -> bool:
        """True if file content is materially new vs last sighting."""
        h = file_hash(workspace / rel)
        old = self.hashes.get(rel)
        self.hashes[rel] = h
        self.hash_history.setdefault(rel, []).append(h)
        self.hash_history[rel] = self.hash_history[rel][-8:]
        if old is None or old != h:
            self.events.append(f"file {rel} advanced ({old} -> {h})")
            return True
        return False

    def file_oscillating(self, rel: str) -> bool:
        """True if the file cycles between states (A->B->A->B)."""
        hist = self.hash_history.get(rel, [])
        if len(hist) < 4:
            return False
        a, b = hist[-4], hist[-3]
        if a == b:
            return False
        return hist[-4:] == [a, b, a, b]

    def note_test(self, command: str, passed: bool) -> bool:
        """True if this test outcome is new progress (new pass / fixed)."""
        old = self.test_states.get(command)
        self.test_states[command] = passed
        if passed and old is not True:
            self.events.append(f"test newly passing: {command[:80]}")
            return True
        return False

    def note_error(self, raw: str) -> bool:
        """True if this error signature is new (i.e. situation changed)."""
        sig = normalize_error(raw)
        n = self.error_sigs.get(sig, 0) + 1
        self.error_sigs[sig] = n
        return n == 1

    def note_issue_resolved(self, issue: str) -> None:
        self.issues_open.discard(issue)
        self.events.append(f"issue resolved: {issue[:80]}")

    def note_output(self, text: str) -> bool:
        """True if this stdout was never produced before."""
        h = hashlib.sha256(text.encode()).hexdigest()[:16]
        if h in self.outputs_seen:
            return False
        self.outputs_seen.add(h)
        return True

    # -- verdict ------------------------------------------------------------
    def priced_check(self, progressed: bool) -> str | None:
        """Call once per step with whether ANY observation was progress.
        Returns NO_PROGRESS_DETECTED reason or None."""
        if progressed:
            self.strikes = 0
            return None
        self.strikes += 1
        if self.strikes >= self.limit:
            return (f"NO_PROGRESS_DETECTED: {self.strikes} steps without file, "
                    f"test, error-signature, output or issue progress")
        return None

    def summary(self) -> dict[str, Any]:
        return {"strikes": self.strikes, "limit": self.limit,
                "files_tracked": len(self.hashes),
                "tests_tracked": len(self.test_states),
                "error_signatures": len(self.error_sigs),
                "recent": self.events[-10:]}
